#!/usr/bin/env python3
"""
ADFG Harvest Data Scraper

Scrapes hunting harvest data from the Alaska Department of Fish & Game website
using Selenium (the site blocks non-browser requests).

Two data sources:
  - harvest_lookup: Individual harvest records via 'Display Records'
  - harvest_reports: Summary reports with success rates by hunt

Usage:
  python scraper.py --source reports --species caribou --years 2023-2024
  python scraper.py --source reports --species all --years 2010-2024
  python scraper.py --source both --species caribou,sheep --years 2015-2024
"""

import argparse
import csv
import glob as globmod
import os
import signal
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

# All big game species available on ADFG
ALL_SPECIES = ["bison", "caribou", "elk", "goat", "moose", "muskox", "sheep"]

HARVEST_LOOKUP_URL = "https://secure.wildlife.alaska.gov/index.cfm?fuseaction=harvest.lookup"
HARVEST_REPORTS_URL = "https://secure.wildlife.alaska.gov/index.cfm?fuseaction=harvestreports.main"

DATA_DIR = Path(__file__).parent / "data"

POLITE_DELAY = 2.0  # seconds between requests
PAGE_LOAD_TIMEOUT = 30  # max seconds to wait for a page/results to load
PER_ITERATION_TIMEOUT = 45  # max seconds per species+year iteration

# --- Discovered element IDs/names from ADFG pages ---
# Harvest Lookup page:
#   id='year' name='YEAR', id='species' name='Species'
#   id='gmu_list' name='GMU', id='hunt_list' name='HUNT'
#   Buttons: value='Display Records', value='Create Excel File'
#
# Harvest Reports page:
#   name='YEAR' (no id), name='Species' (no id)
#   Buttons: value='Get Reports'


class IterationTimeout(Exception):
    """Raised when a single scrape iteration takes too long."""
    pass


def _timeout_handler(signum, frame):
    raise IterationTimeout("Iteration timed out")


def create_driver(interactive=False):
    """Create a Selenium Chrome WebDriver."""
    options = Options()
    if not interactive:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(5)  # reduced from 10 to fail faster
    return driver


def select_by_id(driver, element_id, value):
    """Select a dropdown option by element ID and visible text."""
    try:
        select_el = Select(driver.find_element(By.ID, element_id))
        select_el.select_by_visible_text(value)
        return True
    except (NoSuchElementException, Exception) as e:
        print(f"  WARNING: Could not select '{value}' in #{element_id}: {e}")
        return False


def select_by_name(driver, name, value):
    """Select a dropdown option by element name and visible text."""
    try:
        select_el = Select(driver.find_element(By.NAME, name))
        select_el.select_by_visible_text(value)
        return True
    except (NoSuchElementException, Exception) as e:
        print(f"  WARNING: Could not select '{value}' in name='{name}': {e}")
        return False


def click_button(driver, value):
    """Click an input/button by its value attribute."""
    try:
        btn = driver.find_element(By.CSS_SELECTOR, f"input[value='{value}']")
        btn.click()
        return True
    except NoSuchElementException:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, f"button[value='{value}']")
            btn.click()
            return True
        except NoSuchElementException:
            print(f"  WARNING: Button '{value}' not found")
            return False


def wait_for_results(driver, timeout=15):
    """Wait for results to appear after form submission."""
    start = time.time()
    while time.time() - start < timeout:
        tables = driver.find_elements(By.TAG_NAME, "table")
        # Look for a table that appeared after the form (more than the initial form tables)
        for table in tables:
            rows = table.find_elements(By.TAG_NAME, "tr")
            if len(rows) > 2:  # has actual data rows
                header_cells = rows[0].find_elements(By.TAG_NAME, "th")
                if header_cells:
                    return True
        time.sleep(1)
    return False


def parse_html_table(driver, table_index=0):
    """Parse an HTML table into a list of dicts using header row as keys."""
    tables = driver.find_elements(By.TAG_NAME, "table")
    if table_index >= len(tables):
        return []

    table = tables[table_index]
    rows = table.find_elements(By.TAG_NAME, "tr")
    if not rows:
        return []

    header_cells = rows[0].find_elements(By.TAG_NAME, "th")
    if not header_cells:
        header_cells = rows[0].find_elements(By.TAG_NAME, "td")
    headers = [cell.text.strip().lower().replace(" ", "_").replace("#", "num") for cell in header_cells]

    if not headers:
        return []

    data = []
    for row in rows[1:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) == len(headers):
            record = {headers[i]: cells[i].text.strip() for i in range(len(headers))}
            # Skip empty/total rows
            if any(v for v in record.values()):
                data.append(record)

    return data


def find_data_table(driver):
    """Find the main data table on the page."""
    tables = driver.find_elements(By.TAG_NAME, "table")
    harvest_keywords = {"hunt", "year", "gmu", "harvest", "hunter", "permit", "success",
                        "killed", "hunted", "unit", "species", "num_permits", "num_hunters",
                        "num_harvested", "did_hunt", "reporting"}

    for i, table in enumerate(tables):
        rows = table.find_elements(By.TAG_NAME, "tr")
        if not rows or len(rows) < 2:
            continue
        header_cells = rows[0].find_elements(By.TAG_NAME, "th")
        if not header_cells:
            header_cells = rows[0].find_elements(By.TAG_NAME, "td")
        header_text = {cell.text.strip().lower().replace(" ", "_") for cell in header_cells}
        if header_text & harvest_keywords:
            return parse_html_table(driver, i)

    # Fallback: largest table with > 2 rows
    if tables:
        largest_idx = -1
        largest_rows = 2
        for i, table in enumerate(tables):
            row_count = len(table.find_elements(By.TAG_NAME, "tr"))
            if row_count > largest_rows:
                largest_rows = row_count
                largest_idx = i
        if largest_idx >= 0:
            return parse_html_table(driver, largest_idx)

    return []


def discover_page_elements(driver, url):
    """Navigate to a URL and report all form elements found."""
    driver.get(url)
    time.sleep(3)

    print(f"\n{'='*60}")
    print(f"Page: {url}")
    print(f"Title: {driver.title}")
    print(f"{'='*60}")

    selects = driver.find_elements(By.TAG_NAME, "select")
    print(f"\nDropdowns ({len(selects)}):")
    for sel in selects:
        sel_id = sel.get_attribute("id") or "(no id)"
        sel_name = sel.get_attribute("name") or "(no name)"
        options = Select(sel).options
        option_texts = [o.text.strip() for o in options[:10]]
        suffix = f" ... (+{len(options)-10} more)" if len(options) > 10 else ""
        print(f"  id='{sel_id}' name='{sel_name}': {option_texts}{suffix}")

    buttons = driver.find_elements(By.CSS_SELECTOR,
        "input[type='submit'], button[type='submit'], input[type='button']")
    print(f"\nButtons ({len(buttons)}):")
    for btn in buttons:
        btn_id = btn.get_attribute("id") or "(no id)"
        btn_name = btn.get_attribute("name") or "(no name)"
        btn_val = btn.get_attribute("value") or btn.text or "(no label)"
        print(f"  id='{btn_id}' name='{btn_name}' value='{btn_val}'")

    links = driver.find_elements(By.TAG_NAME, "a")
    harvest_links = [l for l in links if any(
        kw in (l.text.lower() + (l.get_attribute("href") or "").lower())
        for kw in ["download", "export", "csv", "lookup", "report", "harvest"])]
    print(f"\nRelevant links ({len(harvest_links)}):")
    for link in harvest_links:
        href = link.get_attribute("href") or "(no href)"
        print(f"  '{link.text.strip()}' -> {href}")

    tables = driver.find_elements(By.TAG_NAME, "table")
    print(f"\nTables ({len(tables)}):")
    for i, table in enumerate(tables):
        rows = table.find_elements(By.TAG_NAME, "tr")
        print(f"  Table {i}: {len(rows)} rows")
        if rows:
            cells = (rows[0].find_elements(By.TAG_NAME, "th") or
                     rows[0].find_elements(By.TAG_NAME, "td"))
            headers = [c.text.strip()[:50] for c in cells]
            print(f"    Headers: {headers}")

    print()


def scrape_harvest_lookup(driver, species_list, year_start, year_end):
    """
    Scrape the Harvest Lookup tool via 'Display Records'.

    Confirmed elements: id='year', id='species', button 'Display Records'
    """
    all_records = {}

    for species in species_list:
        species_cap = species.capitalize()
        print(f"\n--- Harvest Lookup: {species_cap} ---")
        records = []

        for year in range(year_start, year_end + 1):
            print(f"  {year}...", end=" ", flush=True)
            iter_start = time.time()

            try:
                driver.get(HARVEST_LOOKUP_URL)
                time.sleep(POLITE_DELAY)

                if not select_by_id(driver, "year", str(year)):
                    print("SKIP")
                    continue
                if not select_by_id(driver, "species", species_cap):
                    print("SKIP")
                    continue
                if not click_button(driver, "Display Records"):
                    print("SKIP")
                    continue

                # Wait for results with timeout
                if not wait_for_results(driver, timeout=15):
                    print("no results (timeout)")
                    continue

                table_data = find_data_table(driver)
                if table_data:
                    for row in table_data:
                        row["year"] = str(year)
                        row["species"] = species
                    records.extend(table_data)
                    print(f"{len(table_data)} records")
                else:
                    print("no data")

            except TimeoutException:
                print("TIMEOUT (page load)")
                continue
            except (StaleElementReferenceException, WebDriverException) as e:
                print(f"ERROR: {type(e).__name__}")
                continue

            elapsed = time.time() - iter_start
            if elapsed > PER_ITERATION_TIMEOUT:
                print(f"  (took {elapsed:.0f}s, continuing)")

        if records:
            all_records[species] = records
            # Save after each species so partial results aren't lost
            save_records({species: records})

    return all_records


def scrape_harvest_reports(driver, species_list, year_start, year_end):
    """
    Scrape the General Harvest Reports tool.

    Confirmed elements: name='YEAR', name='Species', button 'Get Reports'
    """
    all_records = {}

    for species in species_list:
        species_cap = species.capitalize()
        print(f"\n--- Harvest Reports: {species_cap} ---")
        records = []

        for year in range(year_start, year_end + 1):
            print(f"  {year}...", end=" ", flush=True)

            try:
                driver.get(HARVEST_REPORTS_URL)
                time.sleep(POLITE_DELAY)

                if not select_by_name(driver, "YEAR", str(year)):
                    print("SKIP")
                    continue
                if not select_by_name(driver, "Species", species_cap):
                    print("SKIP")
                    continue
                if not click_button(driver, "Get Reports"):
                    print("SKIP")
                    continue

                # Wait for results with timeout
                if not wait_for_results(driver, timeout=15):
                    print("no results (timeout)")
                    continue

                table_data = find_data_table(driver)
                if table_data:
                    for row in table_data:
                        row["year"] = str(year)
                        row["species"] = species
                    records.extend(table_data)
                    print(f"{len(table_data)} records")
                else:
                    print("no data")

            except TimeoutException:
                print("TIMEOUT (page load)")
                continue
            except (StaleElementReferenceException, WebDriverException) as e:
                print(f"ERROR: {type(e).__name__}")
                continue

        if records:
            all_records[species] = records
            # Save after each species so partial results aren't lost
            save_records({species: records})

    return all_records


def normalize_records(records):
    """Normalize scraped records into a consistent output format."""
    normalized = []

    col_map = {
        "hunt": ["hunt", "hunt_num", "hunt_no", "hunt_number", "hunt_code"],
        "gmu": ["gmu", "unit", "game_management_unit", "area"],
        "permits": ["permits", "permits_issued", "num_permits", "total_permits"],
        "hunters": ["hunters", "num_hunters", "total_hunters", "did_hunt", "hunted"],
        "harvest": ["harvest", "total_harvest", "num_harvested", "killed",
                     "animals_harvested", "harvested"],
        "success_rate": ["success_rate", "%_success", "success_%", "success",
                         "pct_success", "percent_success", "success_percent"],
    }

    for record in records:
        row = {"year": record.get("year", ""), "species": record.get("species", "")}

        for target, candidates in col_map.items():
            for candidate in candidates:
                if candidate in record:
                    row[target] = record[candidate]
                    break

        # Compute success_rate from hunters + harvest if missing
        if "success_rate" not in row and "hunters" in row and "harvest" in row:
            try:
                hunters = int(row["hunters"])
                harvest = int(row["harvest"])
                if hunters > 0:
                    row["success_rate"] = f"{harvest / hunters:.3f}"
            except (ValueError, ZeroDivisionError):
                pass

        normalized.append(row)

    return normalized


def save_records(records_by_species):
    """Save records to CSV files in the data directory, one file per species."""
    DATA_DIR.mkdir(exist_ok=True)

    for species, records in records_by_species.items():
        normalized = normalize_records(records)
        if not normalized:
            continue

        filepath = DATA_DIR / f"{species}.csv"

        # Collect all column names
        all_cols = set()
        for r in normalized:
            all_cols.update(r.keys())

        ordered_cols = []
        for col in ["hunt", "year", "gmu", "permits", "hunters", "harvest",
                     "success_rate", "species"]:
            if col in all_cols:
                ordered_cols.append(col)
                all_cols.discard(col)
        ordered_cols.extend(sorted(all_cols))

        # Merge with existing file
        existing = []
        if filepath.exists():
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                existing = list(reader)
                for col in reader.fieldnames or []:
                    if col not in ordered_cols:
                        ordered_cols.append(col)

        # Deduplicate by (hunt, year)
        seen = set()
        merged = []
        for r in normalized + existing:
            key = (r.get("hunt", ""), r.get("year", ""))
            if key not in seen:
                seen.add(key)
                merged.append(r)

        merged.sort(key=lambda r: (r.get("hunt", ""), r.get("year", "")))

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ordered_cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(merged)

        print(f"  -> Saved {len(merged)} records to {filepath}")


def parse_year_range(year_str):
    if "-" in year_str:
        parts = year_str.split("-")
        return int(parts[0]), int(parts[1])
    else:
        y = int(year_str)
        return y, y


def parse_species(species_str):
    if species_str.lower() == "all":
        return ALL_SPECIES
    return [s.strip().lower() for s in species_str.split(",")]


def main():
    parser = argparse.ArgumentParser(
        description="Scrape hunting harvest data from Alaska Dept of Fish & Game"
    )
    parser.add_argument("--source", choices=["lookup", "reports", "both"],
                        default="both")
    parser.add_argument("--species", default="all",
                        help=f"Comma-separated or 'all'. Available: {', '.join(ALL_SPECIES)}")
    parser.add_argument("--years", default="2010-2024",
                        help="Year range, e.g. '2010-2024'")
    parser.add_argument("--interactive", action="store_true",
                        help="Open visible browser for debugging")
    parser.add_argument("--discover", action="store_true",
                        help="Just print page elements (for debugging)")

    args = parser.parse_args()

    species_list = parse_species(args.species)
    year_start, year_end = parse_year_range(args.years)

    print(f"Species: {', '.join(species_list)}")
    print(f"Years: {year_start}-{year_end}")
    print(f"Source: {args.source}")
    print(f"Mode: {'interactive' if args.interactive else 'headless'}")
    print(f"Timeouts: page={PAGE_LOAD_TIMEOUT}s, wait={PER_ITERATION_TIMEOUT}s")
    print()

    driver = create_driver(interactive=args.interactive)

    try:
        if args.discover:
            discover_page_elements(driver, HARVEST_LOOKUP_URL)
            discover_page_elements(driver, HARVEST_REPORTS_URL)
            return

        all_records = {}

        if args.source in ("lookup", "both"):
            records = scrape_harvest_lookup(driver, species_list, year_start, year_end)
            for species, data in records.items():
                all_records.setdefault(species, []).extend(data)

        if args.source in ("reports", "both"):
            records = scrape_harvest_reports(driver, species_list, year_start, year_end)
            for species, data in records.items():
                all_records.setdefault(species, []).extend(data)

        if all_records:
            save_records(all_records)
            total = sum(len(v) for v in all_records.values())
            print(f"\nDone! {total} total records for: {', '.join(all_records.keys())}")
        else:
            print("\nNo data was collected.")
            print("Try --discover to inspect page structure.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
