"""
Alaska Hunt Success Rate Analyzer

Auto-discovers animal types from CSV files in the data/ directory.
To add a new animal, just drop a CSV file in data/ and restart.
"""

import os
import glob
import streamlit as st
from analysis import render_animal_page

st.set_page_config(
    page_title="Alaska Hunt Analyzer",
    layout="wide",
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Auto-discover animal types from CSV filenames
csv_files = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))
animals = {
    os.path.splitext(os.path.basename(f))[0].replace("_", " ").title(): f
    for f in csv_files
}

if not animals:
    st.title("Alaska Hunt Analyzer")
    st.error(
        "No CSV files found in the `data/` directory.\n\n"
        "To get started:\n"
        "1. Run the scraper: `python scraper.py --species all --years 2010-2024`\n"
        "2. Or place CSV files manually in the `data/` folder\n\n"
        "Expected CSV columns:\n"
        "- New format: `hunt, year, hunters, harvest, success_rate`\n"
        "- Old format: `hunt, year, hunted, killed`"
    )
    st.stop()

st.sidebar.title("Alaska Hunt Analyzer")
selected = st.sidebar.radio("Animal", list(animals.keys()))

render_animal_page(selected, animals[selected])
