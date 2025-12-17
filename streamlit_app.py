import streamlit as st
import pandas as pd
import requests
import os
from dotenv import load_dotenv
import plotly.express as px
from datetime import datetime, timedelta

# Load Config
load_dotenv()

# Try getting from Environment (Local .env) or Streamlit Secrets (Cloud)
def get_secret(key):
    # 1. Try os.getenv (Local .env or System Env)
    val = os.getenv(key)
    if val:
        return val
    # 2. Try st.secrets (Streamlit Cloud TOML)
    try:
        if key in st.secrets:
            return st.secrets[key]
    except FileNotFoundError:
        pass
    return None

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")
SHELLY_DEVICE_ID = get_secret("SHELLY_DEVICE_ID")

# Page Config
st.set_page_config(
    page_title="Smart Water Dashboard",
    page_icon="💧",
    layout="wide"
)

# Initialize Connection
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Missing Supabase configuration!")
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Data Fetching via REST
def get_latest_readings():
    try:
        # SELECT * FROM energy_readings ORDER BY created_at DESC LIMIT 2
        url = f"{SUPABASE_URL}/rest/v1/energy_readings?order=created_at.desc&limit=2"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return []

def get_history(days=1):
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    try:
        # SELECT * FROM energy_readings WHERE created_at >= start_date ORDER BY created_at ASC
        url = f"{SUPABASE_URL}/rest/v1/energy_readings?created_at=gte.{start_date}&order=created_at.asc"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return pd.DataFrame(response.json())
    except Exception as e:
        st.error(f"History fetch error: {e}")
        return pd.DataFrame()

# UI Layout
st.title("💧 Smart Water Dashboard")

# Refresh Button
if st.button("Refresh Data"):
    st.rerun()

# 1. LIVE STATUS
st.header("Live Status")
latest = get_latest_readings()

if latest:
    # Latest timestamp check
    last_time = pd.to_datetime(latest[0]['created_at'])
    minutes_ago = (datetime.utcnow() - last_time).total_seconds() / 60
    
    col_status, col_time = st.columns([3, 1])
    with col_status:
        if minutes_ago < 5:
            st.success("✅ System Online")
        else:
            st.warning(f"⚠️ System Offline? (Last Update: {int(minutes_ago)} min ago)")
    with col_time:
        st.caption(f"Last updated: {last_time.strftime('%H:%M:%S UTC')}")

    # Cards
    col1, col2 = st.columns(2)
    
    # Main Heater (Channel 0 usually)
    main = next((x for x in latest if x['channel'] == 0), None)
    # Second Heater (Channel 1 usually)
    second = next((x for x in latest if x['channel'] == 1), None)

    with col1:
        st.subheader("Main Heater")
        if main:
            st.metric("Power", f"{main['power_w']} W")
            st.metric("Voltage", f"{main['voltage']} V")
            st.metric("Total Energy", f"{main['energy_total_wh'] / 1000:.1f} kWh")
        else:
            st.info("No data for Main Heater")

    with col2:
        st.subheader("Second Heater")
        if second:
            st.metric("Power", f"{second['power_w']} W")
            st.metric("Voltage", f"{second['voltage']} V")
            st.metric("Total Energy", f"{second['energy_total_wh'] / 1000:.1f} kWh")
        else:
            st.info("No data for Second Heater")
else:
    st.info("No data available yet. Is the worker running?")


# 2. HISTORY & ANALYSIS
st.markdown("---")
st.header("History & Analysis")

days = st.slider("Select Period (Days)", 1, 30, 1)
df = get_history(days)

if not df.empty:
    df['created_at'] = pd.to_datetime(df['created_at'])
    df['Power (W)'] = df['power_w']
    
    # Power Graph
    fig = px.line(df, x='created_at', y='Power (W)', color='channel', title=f"Power Draw (Last {days} Days)")
    st.plotly_chart(fig, use_container_width=True)

    # Energy Consumption
    st.subheader("Energy Consumption")
    
    channels = df['channel'].unique()
    for ch in channels:
        ch_data = df[df['channel'] == ch]
        if not ch_data.empty:
            start_wh = ch_data.iloc[0]['energy_total_wh']
            end_wh = ch_data.iloc[-1]['energy_total_wh']
            consumed = (end_wh - start_wh) / 1000.0 # kWh
            st.write(f"**Channel {ch}**: {consumed:.2f} kWh consumed in selected period.")

else:
    st.write("No historical data found.")

# Sidebar Info
st.sidebar.title("About")
st.sidebar.info("This dashboard shows real-time data logged from Shelly Cloud to Supabase.")
