import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
import json

st.set_page_config(page_title="Polymarket Browser", layout="wide")
st.title("Polymarket Market Browser")

# ── Session state init ──────────────────────────────────────────────
if "watchlist" not in st.session_state:
    st.session_state.watchlist = {}  # {id: market_row_dict}
if "price_history" not in st.session_state:
    st.session_state.price_history = {}  # {id: [{"time": ..., "prices": ...}]}

# ── Fetch ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_markets():
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": 100, "active": "true"}
    r = requests.get(url, params=params)
    return r.json()

def get_ai_summary(question, outcomes, prices):
    try:
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 1000,
            "messages": [{
                "role": "user",
                "content": f"""You are a prediction market analyst. Summarize this market in 3 bullet points:
- What is actually being bet on (plain English)
- What the current probabilities suggest
- What could flip the outcome

Market: {question}
Outcomes: {list(zip(outcomes, prices))}

Be concise, sharp, no fluff."""
            }]
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json=payload
        )
        data = r.json()
        return data["content"][0]["text"]
    except Exception as e:
        return f"Could not load summary: {e}"

# ── Data prep ───────────────────────────────────────────────────────
data = fetch_markets()
df = pd.DataFrame(data)

cols = ["id", "question", "outcomePrices", "outcomes", "volume", "endDate", "active"]
cols = [c for c in cols if c in df.columns]
df = df[cols]

df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
df["endDate"] = pd.to_datetime(df["endDate"], errors="coerce", utc=True)
now = datetime.now(timezone.utc)
df["closing_soon"] = df["endDate"].apply(
    lambda x: pd.notna(x) and 0 <= (x - now).days <= 7
)

# ── Sidebar: Watchlist (L4) ─────────────────────────────────────────
with st.sidebar:
    st.header("⭐ Watchlist")
    if st.session_state.watchlist:
        for wid, wrow in list(st.session_state.watchlist.items()):
            st.write(f"• {wrow['question'][:60]}...")
            if st.button("Remove", key=f"rm_{wid}"):
                del st.session_state.watchlist[wid]
                st.rerun()
    else:
        st.write("No markets saved yet.")

# ── Filters ─────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    search = st.text_input("Search markets", placeholder="e.g. Trump, Bitcoin, India")
with col2:
    sort_by = st.selectbox("Sort by", ["Volume (High → Low)", "Closing Soon", "Closing Later"])
with col3:
    closing_filter = st.checkbox("🔴 Closing within 7 days only")

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

# ── Market cards ─────────────────────────────────────────────────────
for i, row in df.iterrows():
    label = ("🔴 " if row["closing_soon"] else "") + row["question"]
    with st.expander(label):
        try:
            outcomes = eval(row["outcomes"]) if isinstance(row["outcomes"], str) else row["outcomes"]
            prices = eval(row["outcomePrices"]) if isinstance(row["outcomePrices"], str) else row["outcomePrices"]
            price_floats = [float(p) for p in prices]

            for o, p in zip(outcomes, price_floats):
                prob = p * 100
                st.progress(int(prob), text=f"{o}: {prob:.1f}%")

            # L5 — Price movement tracker
            mid = str(row.get("id", i))
            history = st.session_state.price_history.get(mid, [])
            if history:
                last_prices = history[-1]["prices"]
                st.write("**Price movement since last check:**")
                for o, p_now, p_last in zip(outcomes, price_floats, last_prices):
                    delta = (p_now - p_last) * 100
                    arrow = "🟢 +" if delta > 0 else ("🔴 " if delta < 0 else "⚪ ")
                    st.write(f"{o}: {arrow}{delta:+.1f}%")
            
            # Save snapshot to history
            st.session_state.price_history[mid] = history + [{
                "time": now.isoformat(),
                "prices": price_floats
            }]
            if len(st.session_state.price_history[mid]) > 10:
                st.session_state.price_history[mid] = st.session_state.price_history[mid][-10:]

        except:
            st.write("Prices:", row.get("outcomePrices", "N/A"))
            outcomes, prices = [], []

        st.metric("Volume", f"${float(row['volume']):,.0f}")
        end = row.get("endDate")
        if pd.notna(end):
            days_left = (end - now).days
            st.write(f"Ends: {end.strftime('%b %d, %Y')} ({days_left} days left)")

        # L4 — Watchlist button
        mid = str(row.get("id", i))
        if mid in st.session_state.watchlist:
            if st.button("⭐ Remove from Watchlist", key=f"w_{i}"):
                del st.session_state.watchlist[mid]
                st.rerun()
        else:
            if st.button("☆ Add to Watchlist", key=f"w_{i}"):
                st.session_state.watchlist[mid] = row.to_dict()
                st.rerun()

        # L6 — AI Summary
        if st.button("🤖 AI Summary", key=f"ai_{i}"):
            with st.spinner("Analyzing..."):
                try:
                    summary = get_ai_summary(row["question"], outcomes, prices)
                    st.markdown(summary)
                except:
                    st.write("Could not load summary.")
