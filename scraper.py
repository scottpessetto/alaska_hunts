#!/usr/bin/env python3
"""
ADFG Harvest Data Scraper

Scrapes hunting harvest data from the Alaska Department of Fish & Game website
using Selenium (the site blocks non-browser requests).

Two data sources:
  - harvest_lookup: Individual harvest records with Excel download
  - harvest_reports: Summary reports with success rates by hunt

Usage:
  python scraper.py --source lookup --species caribou,sheep --years 2010-2024
  python scraper.py --source reports --species all --years 1975-2024
  python scraper.py --source lookup --species all --years 2000-2024 --interactive
"""

import argparse
import csv
import glob as globmod
import os
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
)
from webdriver_manager.chrome import ChromeDriverManager

# All big game species available on ADFG
ALL_SPECIES = ["bison", "caribou", "elk", "goat", "moose", "muskox", "sheep"]

HARVEST_LOOKUP_URL = "https://secure.wildlife.alaska.gov/index.cfm?fuseaction=harvest.lookup"
HARVEST_REPORTS_URL = "https://secure.wildlife.alaska.gov/index.cfm?fuseaction=harvestreports.main"

DATA_DIR = Path(__file__).parent / "data"

POLITE_DELAY = 2.5  # seconds between requests

# --- Discovered element IDs/names from ADFG pages ---
# Harvest Lookup page (secure.wildlife.alaska.gov):
#   Dropdowns: id='year' name='YEAR', id='species' name='Species',
#              id='mtnRange' name='mtnherd', id='gmu_list' name='GMU',
#              id='hunt_list' name='HUNT'
#   Buttons:   value='Search', name='Action' value='Display Records',
#              name='Action' value='Create Excel File'
#
# Harvest Reports page (secure.wildlife.alaska.gov):
#   Dropdowns: name='YEAR' (no id), name='Species' (no id)
#   Buttons:   value='Search', name='Action' value='Get Reports'


def create_driver(interactive=False, download_dir=None):
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

    # Configure download directory for Excel files
    if download_dir:
        prefs = {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        }
        options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(10)
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
            print(f"  WARNING: Button with value='{value}' not found")
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

    # Get headers from first row
    header_cells = rows[0].find_elements(By.TAG_NAME, "th")
    if not header_cells:
        header_cells = rows[0].find_elements(By.TAG_NAME, "td")
    headers = [cell.text.strip().lower().replace(" ", "_").replace("#", "num") for cell in header_cells]

    if not headers:
        return []

    # Parse data rows
    data = []
    for row in rows[1:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) == len(headers):
            record = {headers[i]: cells[i].text.strip() for i in range(len(headers))}
            data.append(record)

    return data


def find_data_table(driver):
    """Find the main data table on the page, trying multiple strategies."""
    tables = driver.find_elements(By.TAG_NAME, "table")
    harvest_keywords = {"hunt", "year", "gmu", "harvest", "hunter", "permit", "success",
                        "killed", "hunted", "unit", "species", "num_permits", "num_hunters",
                        "num_harvested", "did_hunt", "reporting"}

    for i, table in enumerate(tables):
        header_row = table.find_elements(By.TAG_NAME, "tr")
        if not header_row:
            continue
        header_cells = header_row[0].find_elements(By.TAG_NAME, "th")
        if not header_cells:
            header_cells = header_row[0].find_elements(By.TAG_NAME, "td")
        header_text = {cell.text.strip().lower().replace(" ", "_") for cell in header_cells}
        if header_text & harvest_keywords:
            return parse_html_table(driver, i)

    # Fallback: parse largest table
    if tables:
        largest_idx = 0
        largest_rows = 0
        for i, table in enumerate(tables):
            row_count = len(table.find_elements(By.TAG_NAME, "tr"))
            if row_count > largest_rows:
                largest_rows = row_count
                largest_idx = i
        if largest_rows > 1:
            return parse_html_table(driver, largest_idx)

    return []


def wait_for_download(download_dir, timeout=30):
    """Wait for a file to appear in the download directory."""
    start = time.time()
    while time.time() - start < timeout:
        files = globmod.glob(os.path.join(download_dir, "*"))
        # Filter out partial downloads (.crdownload, .tmp)
        complete = [f for f in files if not f.endswith((".crdownload", ".tmp", ".part"))]
        if complete:
            return max(complete, key=os.path.getmtime)
        time.sleep(1)
    return None


def discover_page_elements(driver, url):
    """Navigate to a URL and report all form elements found. For debugging."""
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

    buttons = driver.find_elements(By.CSS_SELECTOR, "input[type='submit'], button[type='submit'], input[type='button']")
    print(f"\nButtons ({len(buttons)}):")
    for btn in buttons:
        btn_id = btn.get_attribute("id") or "(no id)"
        btn_name = btn.get_attribute("name") or "(no name)"
        btn_val = btn.get_attribute("value") or btn.text or "(no label)"
        print(f"  id='{btn_id}' name='{btn_name}' value='{btn_val}'")

    links = driver.find_elements(By.TAG_NAME, "a")
    harvest_links = [l for l in links if any(kw in (l.text.lower() + (l.get_attribute("href") or "").lower())
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
            cells = rows[0].find_elements(By.TAG_NAME, "th") or rows[0].find_elements(By.TAG_NAME, "td")
            headers = [c.text.strip() for c in cells]
            print(f"    Headers: {headers}")

    print()


def scrape_harvest_lookup(driver, species_list, year_start, year_end, download_dir=None):
    """
    Scrape the Harvest Lookup tool using the 'Create Excel File' button.

    Page elements (confirmed via discover):
      - id='year' name='YEAR': year dropdown
      - id='species' name='Species': species dropdown
      - value='Create Excel File': downloads Excel with all records
      - value='Display Records': shows results in browser
    """
    all_records = {}

    for species in species_list:
        species_cap = species.capitalize()
        print(f"\n--- Scraping Harvest Lookup: {species_cap} ---")
        records = []

        for year in range(year_start, year_end + 1):
            print(f"  Year {year}...", end=" ", flush=True)

            try:
                driver.get(HARVEST_LOOKUP_URL)
                time.sleep(POLITE_DELAY)

                # Select year (id='year')
                if not select_by_id(driver, "year", str(year)):
                    print("SKIP (year)")
                    continue

                # Select species (id='species')
                if not select_by_id(driver, "species", species_cap):
                    print("SKIP (species)")
                    continue

                # Click 'Display Records' to get results in browser
                if not click_button(driver, "Display Records"):
                    print("SKIP (no Display Records button)")
                    continue

                time.sleep(POLITE_DELAY + 2)  # extra wait for results to load

                # Parse the results table
                table_data = find_data_table(driver)
                if table_data:
                    for row in table_data:
                        row["year"] = str(year)
                        row["species"] = species
                    records.extend(table_data)
                    print(f"{len(table_data)} records")
                else:
                    print("no data")

            except (TimeoutException, StaleElementReferenceException) as e:
                print(f"ERROR: {e}")
                continue

        if records:
            all_records[species] = records

    return all_records


def scrape_harvest_reports(driver, species_list, year_start, year_end):
    """
    Scrape the General Harvest Reports tool.

    Page elements (confirmed via discover):
      - name='YEAR' (no id): year dropdown
      - name='Species' (no id): species dropdown
      - value='Get Reports': generates the report table
    """
    all_records = {}

    for species in species_list:
        species_cap = species.capitalize()
        print(f"\n--- Scraping Harvest Reports: {species_cap} ---")
        records = []

        for year in range(year_start, year_end + 1):
            print(f"  Year {year}...", end=" ", flush=True)

            try:
                driver.get(HARVEST_REPORTS_URL)
                time.sleep(POLITE_DELAY)

                # Select year (name='YEAR', no id)
                if not select_by_name(driver, "YEAR", str(year)):
                    print("SKIP (year)")
                    continue

                # Select species (name='Species', no id)
                if not select_by_name(driver, "Species", species_cap):
                    print("SKIP (species)")
                    continue

                # Click 'Get Reports'
                if not click_button(driver, "Get Reports"):
                    print("SKIP (no Get Reports button)")
                    continue

                time.sleep(POLITE_DELAY + 2)  # extra wait for report to generate

                # Parse the results table
                table_data = find_data_table(driver)
                if table_data:
                    for row in table_data:
                        row["year"] = str(year)
                        row["species"] = species
                    records.extend(table_data)
                    print(f"{len(table_data)} records")
                else:
                    print("no data")

            except (TimeoutException, StaleElementReferenceException) as e:
                print(f"ERROR: {e}")
                continue

        if records:
            all_records[species] = records

    return all_records


def normalize_records(records):
    """
    Normalize scraped records into a consistent format.

    Input records may have varying column names depending on the source page.
    Output columns: hunt, year, gmu, permits, hunters, harvest, success_rate
    """
    normalized = []

    # Column name mapping (ADFG pages use various naming conventions)
    col_map = {
        "hunt": ["hunt", "hunt_num", "hunt_no", "hunt_number", "hunt_code"],
        "gmu": ["gmu", "unit", "game_management_unit", "area"],
        "permits": ["permits", "permits_issued", "num_permits", "total_permits"],
        "hunters": ["hunters", "num_hunters", "total_hunters", "did_hunt", "hunted"],
        "harvest": ["harvest", "total_harvest", "num_harvested", "killed", "animals_harvested", "harvested"],
        "success_rate": ["success_rate", "%_success", "success_%", "success", "pct_success",
                         "percent_success", "success_percent"],
    }

    for record in records:
        row = {"year": record.get("year", ""), "species": record.get("species", "")}

        for target, candidates in col_map.items():
            for candidate in candidates:
                if candidate in record:
                    row[target] = record[candidate]
                    break

        # Compute success_rate if we have hunters and harvest but no success_rate
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
        # Preferred column order
        ordered_cols = []
        for col in ["hunt", "year", "gmu", "permits", "hunters", "harvest", "success_rate", "species"]:
            if col in all_cols:
                ordered_cols.append(col)
                all_cols.discard(col)
        ordered_cols.extend(sorted(all_cols))

        # If file exists, merge with existing data
        existing = []
        if filepath.exists():
            with open(filepath, "r") as f:
                reader = csv.DictReader(f)
                existing = list(reader)
                for col in reader.fieldnames or []:
                    if col not in ordered_cols:
                        ordered_cols.append(col)

        # Merge: use (hunt, year) as key to avoid duplicates
        seen = set()
        merged = []
        for r in normalized + existing:
            key = (r.get("hunt", ""), r.get("year", ""))
            if key not in seen:
                seen.add(key)
                merged.append(r)

        # Sort by hunt then year
        merged.sort(key=lambda r: (r.get("hunt", ""), r.get("year", "")))

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ordered_cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(merged)

        print(f"\nSaved {len(merged)} records to {filepath}")


def parse_year_range(year_str):
    """Parse a year range string like '2010-2024' into (start, end)."""
    if "-" in year_str:
        parts = year_str.split("-")
        return int(parts[0]), int(parts[1])
    else:
        y = int(year_str)
        return y, y


def parse_species(species_str):
    """Parse a species string like 'caribou,sheep' or 'all' into a list."""
    if species_str.lower() == "all":
        return ALL_SPECIES
    return [s.strip().lower() for s in species_str.split(",")]


def main():
    parser = argparse.ArgumentParser(
        description="Scrape hunting harvest data from Alaska Dept of Fish & Game"
    )
    parser.add_argument(
        "--source",
        choices=["lookup", "reports", "both"],
        default="both",
        help="Which ADFG data source to scrape (default: both)",
    )
    parser.add_argument(
        "--species",
        default="all",
        help="Comma-separated species or 'all' (default: all). "
             f"Available: {', '.join(ALL_SPECIES)}",
    )
    parser.add_argument(
        "--years",
        default="2010-2024",
        help="Year range to scrape, e.g., '2010-2024' (default: 2010-2024)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open a visible browser window for debugging (default: headless)",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Just discover page elements and print them (for debugging)",
    )

    args = parser.parse_args()

    species_list = parse_species(args.species)
    year_start, year_end = parse_year_range(args.years)

    print(f"Species: {', '.join(species_list)}")
    print(f"Years: {year_start}-{year_end}")
    print(f"Source: {args.source}")
    print(f"Mode: {'interactive' if args.interactive else 'headless'}")
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
            print(f"\nDone! Scraped data for: {', '.join(all_records.keys())}")
        else:
            print("\nNo data was collected.")
            print("Try running with --interactive --discover to inspect the page structure.")
            print("The ADFG site may have changed its layout since this scraper was written.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
