import sheep_app
import caribou_app
import streamlit as st

PAGES = {
    "Sheep" : sheep_app,
    "Caribou" : caribou_app
}

st.sidebar.title("Pick Animal")
selection = st.sidebar.radio("Go To", list(PAGES.keys()))
page=PAGES[selection]
page.app()