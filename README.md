# Alaska Hunt Analyzer

Analyze Alaska Department of Fish & Game hunting success rates by GMU (Game Management Unit). Compare historical performance across hunts and find the best bets for future seasons.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app ships with a small example dataset. To load real data, use the scraper (see below).

## Scraping ADFG Data

The scraper pulls harvest data directly from the ADFG website using Selenium (the site blocks non-browser requests).

```bash
# Scrape all species, recent years
python scraper.py --species all --years 2010-2024

# Scrape specific species
python scraper.py --species caribou,sheep --years 2000-2024

# Use visible browser for debugging
python scraper.py --species caribou --years 2020-2024 --interactive

# Just inspect the page structure (no data collection)
python scraper.py --discover
```

Available species: bison, caribou, elk, goat, moose, muskox, sheep

Data sources:
- **Harvest Lookup** (`--source lookup`): Individual harvest records with data download
- **General Harvest Reports** (`--source reports`): Summary tables with success rates
- **Both** (`--source both`, default): Scrapes both sources and merges

Scraped data is saved to `data/{species}.csv`.

## Adding Animals

Drop a CSV file in the `data/` directory and restart the app. The filename becomes the display name (e.g., `moose.csv` shows as "Moose").

### CSV Format

The app supports two CSV formats:

**New format** (from scraper):
```
hunt,year,gmu,permits,hunters,harvest,success_rate
DC001,2020,Unit 20A,100,85,34,0.400
```

**Old format** (individual records):
```
hunt,year,hunted,killed
DC001,2020,Y,Y
DC001,2020,Y,N
```

## Features

- **GMU Analysis**: Success rate trends over time for selected GMUs with metric cards
- **Compare GMUs**: Side-by-side ranking of all GMUs by success rate, with sample sizes and trend indicators
- **Best Bets**: Scored recommendations combining historical success rate with recent trend direction

## Data Source

Data comes from the [Alaska Department of Fish & Game](https://www.adfg.alaska.gov/) harvest reporting system.

## License

MIT License - see LICENSE file
