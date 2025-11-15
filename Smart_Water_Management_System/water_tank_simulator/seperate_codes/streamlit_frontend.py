# streamlit_frontend.py
import streamlit as st
import requests
import time
import json
from typing import Dict, Any

# -------------------------
# Configuration
# -------------------------
BACKEND_URL = st.secrets.get("BACKEND_URL", "http://backend:8000")  # when running in Docker, backend service name
POLL_INTERVAL_SEC = 2.0  # poll interval (seconds)
MAX_EVENTS_PER_POLL = 300

st.set_page_config(layout="wide", page_title="Tank Simulation Dashboard (SSE/Redis enabled)")
st.title("💧 Tank Simulation Dashboard")

# Auto refresh by meta tag for safety (reliable)
st.markdown(f'<meta http-equiv="refresh" content="{POLL_INTERVAL_SEC}">', unsafe_allow_html=True)

# Controls area
col1, col2, col3 = st.columns([1,1,2])
with col1:
    if st.button("Start Backend Workers"):
        try:
            resp = requests.post(f"{BACKEND_URL}/start", json={"delay_seconds": 1.0, "csv_paths": None}, timeout=5)
            resp.raise_for_status()
            st.success("Started backend workers")
        except Exception as e:
            st.error(f"Error starting workers: {e}")

with col2:
    if st.button("Stop Backend Workers"):
        try:
            resp = requests.post(f"{BACKEND_URL}/stop", timeout=5)
            resp.raise_for_status()
            st.success("Stopped backend workers")
        except Exception as e:
            st.error(f"Error stopping workers: {e}")

with col3:
    try:
        st_status = requests.get(f"{BACKEND_URL}/status", timeout=2).json()
        st.metric("Queue size", st_status.get("queue_size", 0))
        st.caption(f"Backend running: {st_status.get('running', False)}")
    except Exception as e:
        st.caption("Backend not reachable")

st.markdown("---")

# Maintain event history in session state for charts
if "history" not in st.session_state:
    st.session_state.history = {}  # tank -> list of (timestamp_str, level_m3)

# Fetch latest snapshot and drain events
latest = {}
events = []
try:
    status_json = requests.get(f"{BACKEND_URL}/status", timeout=2).json()
    latest = status_json.get("latest", {})
except Exception:
    latest = {}

try:
    ev_resp = requests.get(f"{BACKEND_URL}/events", params={"max_events": MAX_EVENTS_PER_POLL}, timeout=4)
    ev_resp.raise_for_status()
    events = ev_resp.json().get("events", [])
except Exception:
    events = []

# Append events to history
for ev in events:
    tid = ev.get("tank_id")
    ts = ev.get("timestamp")
    level = ev.get("level_m3", 0.0)
    if tid not in st.session_state.history:
        st.session_state.history[tid] = []
    st.session_state.history[tid].append((ts, level))
    # cap history length to keep memory bounded
    if len(st.session_state.history[tid]) > 2000:
        st.session_state.history[tid] = st.session_state.history[tid][-2000:]

# Show live overview and charts
st.subheader("Live Tanks")
if not latest:
    st.info("No tanks available. Start backend workers.")
else:
    ncols = min(4, max(1, len(latest)))
    cols = st.columns(ncols)
    for i, (name, state) in enumerate(sorted(latest.items())):
        with cols[i % ncols]:
            st.markdown(f"### {name}")
            level = state.get("level", 0.0)
            ts = state.get("timestamp", "")
            step = int(state.get("progress_step", 0))
            total = int(state.get("total_updates", 1))
            st.metric("Level (m³)", f"{level:.3f}", delta=None)
            pct = min(100, max(0, level / 10.0 * 100))
            h = int(pct * 1.5)
            html = f'''
            <div style="height:150px;width:120px;border:2px solid #555;border-radius:6px;
                        position:relative;overflow:hidden;background:#f0f2f6;margin:auto;">
                <div style="position:absolute;bottom:0;width:100%;height:{h}px;
                            background:#3B82F6;border-top:2px solid #1E40AF;"></div>
                <div style="position:absolute;top:50%;width:100%;text-align:center;
                            font-weight:600;color:#111;transform:translateY(-50%);">{pct:.0f}%</div>
            </div>
            '''
            st.markdown(html, unsafe_allow_html=True)
            st.progress(step / max(1, total))
            st.caption(f"{step} / {total}  •  {ts}")

st.markdown("---")
st.subheader("Real-time Charts (per-tank)")

# Display a simple Plotly line chart per tank using history
import plotly.graph_objects as go
for name in sorted(st.session_state.history.keys()):
    hist = st.session_state.history[name]
    if not hist:
        continue
    times = [t for t, _ in hist]
    levels = [v for _, v in hist]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=levels, mode="lines+markers", name=name))
    fig.update_layout(title=name, xaxis_title="Timestamp", yaxis_title="Level (m³)", height=300)
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")
st.subheader("Recent Events (this poll)")
if not events:
    st.write("No new events")
else:
    for ev in events[::-1][:100]:
        st.write(f"**{ev.get('tank_id')}** — {ev.get('timestamp')} — level {ev.get('level_m3'):.3f} m³ (raw {ev.get('raw_value')})")

st.caption("Notes: This UI uses polling for compatibility. The backend also exposes SSE and WebSocket endpoints for push-based streaming (you can connect a custom JS/React client to /stream/sse or /stream/ws). If REDIS_URL is configured, the backend will publish events to Redis pub/sub and store latest state in Redis.")