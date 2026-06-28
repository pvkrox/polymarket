import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
import json
from supabase import create_client

st.set_page_config(page_title="Polymarket Browser", layout="wide")
st.title("Polymarket Market Browser")

# ── Supabase client ─────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )

supabase = get_supabase()

# ── Persistent price history helpers ────────────────────────────────
def load_price_history(market_id):
    res = supabase.table("price_history") \
        .select("prices, time") \
        .eq("market_id", market_id) \
        .order("time", desc=False) \
        .limit(10) \
        .execute()
    return res.data  # list of {prices, time}

def save_price_snapshot(market_id, prices):
    supabase.table("price_history").insert({
        "market_id": market_id,
        "prices": prices,
        "time": datetime.now(timezone.utc).isoformat()
    }).execute()

# ── Session state init ──────────────────────────────────────────────
if "watchlist" not in st.session_state:
    st.session_state.watchlist = {}

# ── Fetch markets ───────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_markets():
    url = "https://gamma-api.polymarket.com/markets"
    params = {"limit": 100, "active": "true"}
    r = requests.get(url, params=params)
    return r.json()

def get_ai_summary(question, outcomes, prices):
    try:
        payload = {
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 500,
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
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {st.secrets['GROQ_API_KEY']}"
            },
            json=payload
        )
        return r.json()["choices"][0]["message"]["content"]
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

# ── Sidebar: Watchlist ──────────────────────────────────────────────
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

# ── Market cards ────────────────────────────────────────────────────
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

            # Price movement tracker — persistent via Supabase
            mid = str(row.get("id", i))
            history = load_price_history(mid)

            if history:
                last_entry = history[-1]
                last_prices = last_entry["prices"]
                last_time = last_entry["time"][:16].replace("T", " ")
                st.write(f"**Price movement since {last_time} UTC:**")
                for o, p_now, p_last in zip(outcomes, price_floats, last_prices):
                    delta = (p_now - p_last) * 100
                    arrow = "🟢 +" if delta > 0 else ("🔴 " if delta < 0 else "⚪ ")
                    st.write(f"{o}: {arrow}{delta:+.1f}%")

                # Only save if prices changed
                if last_prices != price_floats:
                    save_price_snapshot(mid, price_floats)
            else:
                st.caption("First visit — check back later to see price movement.")
                save_price_snapshot(mid, price_floats)

        except Exception as e:
            st.write("Prices:", row.get("outcomePrices", "N/A"))
            outcomes, price_floats = [], []

        st.metric("Volume", f"${float(row['volume']):,.0f}")
        end = row.get("endDate")
        if pd.notna(end):
            days_left = (end - now).days
            st.write(f"Ends: {end.strftime('%b %d, %Y')} ({days_left} days left)")

        # Watchlist
        mid = str(row.get("id", i))
        if mid in st.session_state.watchlist:
            if st.button("⭐ Remove from Watchlist", key=f"w_{i}"):
                del st.session_state.watchlist[mid]
                st.rerun()
        else:
            if st.button("☆ Add to Watchlist", key=f"w_{i}"):
                st.session_state.watchlist[mid] = row.to_dict()
                st.rerun()

        # AI Summary
        if st.button("🤖 AI Summary", key=f"ai_{i}"):
            with st.spinner("Analyzing..."):
                try:
                    summary = get_ai_summary(row["question"], outcomes, price_floats)
                    st.markdown(summary)
                except:
                    st.write("Could not load summary.")