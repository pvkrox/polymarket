import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone

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

# Parse volume and endDate
df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
df["endDate"] = pd.to_datetime(df["endDate"], errors="coerce", utc=True)

# Closing soon flag (within 7 days)
now = datetime.now(timezone.utc)
df["closing_soon"] = df["endDate"].apply(
    lambda x: x is not pd.NaT and (x - now).days <= 7 if pd.notna(x) else False
)

# --- Filters row ---
col1, col2, col3 = st.columns([3, 2, 2])

with col1:
    search = st.text_input("Search markets", placeholder="e.g. Trump, Bitcoin, India")

with col2:
    sort_by = st.selectbox("Sort by", ["Volume (High → Low)", "Closing Soon", "Closing Later"])

with col3:
    closing_filter = st.checkbox("🔴 Closing within 7 days only")

# Apply filters
if search:
    df = df[df["question"].str.contains(search, case=False, na=False)]

if closing_filter:
    df = df[df["closing_soon"] == True]

if sort_by == "Volume (High → Low)":
    df = df.sort_values("volume", ascending=False)
elif sort_by == "Closing Soon":
    df = df.sort_values("endDate", ascending=True)
elif sort_by == "Closing Later":
    df = df.sort_values("endDate", ascending=False)

st.write(f"Showing {len(df)} markets")

# Market cards
for i, row in df.iterrows():
    label = "🔴 CLOSING SOON — " + row["question"] if row["closing_soon"] else row["question"]
    with st.expander(label):
        try:
            outcomes = eval(row["outcomes"]) if isinstance(row["outcomes"], str) else row["outcomes"]
            prices = eval(row["outcomePrices"]) if isinstance(row["outcomePrices"], str) else row["outcomePrices"]
            for o, p in zip(outcomes, prices):
                prob = float(p) * 100
                st.progress(int(prob), text=f"{o}: {prob:.1f}%")
        except:
            st.write("Prices:", row.get("outcomePrices", "N/A"))

        st.metric("Volume", f"${float(row['volume']):,.0f}")
        end = row.get("endDate")
        if pd.notna(end):
            days_left = (end - now).days
            st.write(f"Ends: {end.strftime('%b %d, %Y')} ({days_left} days left)")
