import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Polymarket Browser", layout="wide")
st.title("Polymarket Market Browser")

@st.cache_data(ttl=300)
def fetch_markets():
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": 100, "active": "true"}
    response = requests.get(url, params=params)
    return response.json()

data = fetch_markets()
df = pd.DataFrame(data)

# Keep only useful columns
cols = ["question", "outcomePrices", "volume", "endDate", "active"]
cols = [c for c in cols if c in df.columns]
df = df[cols]

# Search filter
search = st.text_input("Search markets", placeholder="e.g. Trump, Bitcoin, India")
if search:
    df = df[df["question"].str.contains(search, case=False, na=False)]

st.write(f"Showing {len(df)} markets")
st.dataframe(df, use_container_width=True)