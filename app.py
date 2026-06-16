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

cols = ["question", "outcomePrices", "outcomes", "volume", "endDate", "active"]
cols = [c for c in cols if c in df.columns]
df = df[cols]

# Search filter
search = st.text_input("Search markets", placeholder="e.g. Trump, Bitcoin, India")
if search:
    df = df[df["question"].str.contains(search, case=False, na=False)]

st.write(f"Showing {len(df)} markets")

# Clickable market list
for i, row in df.iterrows():
    with st.expander(row["question"]):
        try:
            outcomes = eval(row["outcomes"]) if isinstance(row["outcomes"], str) else row["outcomes"]
            prices = eval(row["outcomePrices"]) if isinstance(row["outcomePrices"], str) else row["outcomePrices"]
            for o, p in zip(outcomes, prices):
                prob = float(p) * 100
                st.progress(int(prob), text=f"{o}: {prob:.1f}%")
        except:
            st.write("Prices:", row.get("outcomePrices", "N/A"))
        
        vol = row.get("volume", 0)
        try:
            st.metric("Volume", f"${float(vol):,.0f}")
        except:
            st.metric("Volume", str(vol))
        
        st.write("Ends:", row.get("endDate", "N/A"))
