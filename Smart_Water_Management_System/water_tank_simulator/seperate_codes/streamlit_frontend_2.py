# streamlit_frontend.py
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import time

# -------------------------
# Configuration
# -------------------------
BACKEND_URL = "http://localhost:8000"
POLL_INTERVAL_SEC = 0.2  # fast but safe polling for incremental updates
MAX_HISTORY_LENGTH = 2000  # Limit per tank history
MAX_CHART_POINTS = 500     # Limit points plotted for performance

st.set_page_config(layout="wide", page_title="Tank Simulation Dashboard")
st.title("💧 Tank Simulation Dashboard")

print("[INIT] Streamlit dashboard initialized.")
print(f"[CONFIG] Backend URL: {BACKEND_URL}, Poll interval: {POLL_INTERVAL_SEC}s")

# Auto-refresh using st_autorefresh
st_autorefresh(interval=int(POLL_INTERVAL_SEC * 1000), key="refresh")
print("[INIT] Auto-refresh enabled.")

# -------------------------
# Controls
# -------------------------
col1, col2, col3 = st.columns([1, 1, 2])

with col1:
    if st.button("Start Backend Workers"):
        print("[ACTION] Start Backend Workers clicked.")
        try:
            resp = requests.post(
                f"{BACKEND_URL}/start",
                json={"delay_seconds": 1.0, "csv_paths": None},
                timeout=5
            )
            resp.raise_for_status()
            st.success("Started backend workers")
            print("[INFO] Backend workers started successfully.")
        except Exception as e:
            st.error(f"Error starting workers: {e}")
            print(f"[ERROR] Failed to start backend workers: {e}")

with col2:
    if st.button("Stop Backend Workers"):
        print("[ACTION] Stop Backend Workers clicked.")
        try:
            resp = requests.post(f"{BACKEND_URL}/stop", timeout=5)
            resp.raise_for_status()
            st.success("Stopped backend workers")
            print("[INFO] Backend workers stopped successfully.")
        except Exception as e:
            st.error(f"Error stopping workers: {e}")
            print(f"[ERROR] Failed to stop backend workers: {e}")

with col3:
    try:
        status = requests.get(f"{BACKEND_URL}/status", timeout=2).json()
        st.metric("Queue size", status.get("queue_size", 0))
        st.caption(f"Backend running: {status.get('running', False)}")
        print(f"[STATUS] Queue size: {status.get('queue_size', 0)}, Running: {status.get('running', False)}")
    except Exception as e:
        st.caption("Backend not reachable")
        print(f"[ERROR] Backend not reachable: {e}")

st.markdown("---")

# -------------------------
# Initialize session state
# -------------------------
if "history" not in st.session_state:
    st.session_state.history = {}
    st.session_state.chart_placeholders = {}
    print("[STATE] Initialized session state for history and chart placeholders.")

# -------------------------
# Fetch **one event at a time**
# -------------------------
try:
    ev_resp = requests.get(
        f"{BACKEND_URL}/events",
        params={"max_events": 1},  # only fetch 1 event per poll
        timeout=3
    )
    ev_resp.raise_for_status()
    events = ev_resp.json().get("events", [])
    print(f"[EVENTS] Fetched {len(events)} new event(s) from backend.")
except Exception as e:
    events = []
    print(f"[ERROR] Failed to fetch events: {e}")

# -------------------------
# Update session state history
# -------------------------
for ev in events:
    tid = ev.get("tank_id")
    ts = ev.get("timestamp")
    level = ev.get("level_m3", 0.0)
    print(f"[UPDATE] Tank: {tid}, Timestamp: {ts}, Level: {level:.3f} m³")

    if tid not in st.session_state.history:
        st.session_state.history[tid] = []
        print(f"[STATE] Created new history list for tank {tid}")

    st.session_state.history[tid].append((ts, level))

    # Cap history length
    if len(st.session_state.history[tid]) > MAX_HISTORY_LENGTH:
        st.session_state.history[tid] = st.session_state.history[tid][-MAX_HISTORY_LENGTH:]
        print(f"[STATE] Trimmed history for {tid} to {MAX_HISTORY_LENGTH} entries.")

# -------------------------
# Fetch latest snapshot for live tanks
# -------------------------
latest = {}
try:
    latest_resp = requests.get(f"{BACKEND_URL}/latest", timeout=2).json()
    latest = latest_resp.get("latest", {})
    print(f"[FETCH] Latest snapshot fetched. Tanks: {list(latest.keys())}")
except Exception as e:
    st.warning("Failed to fetch latest snapshot")
    print(f"[ERROR] Failed to fetch latest snapshot: {e}")

# -------------------------
# Display live tanks
# -------------------------
st.subheader("Live Tanks")
if not latest:
    st.info("No tanks available. Ensure backend workers are started.")
    print("[INFO] No tanks available to display.")
else:
    ncols = min(4, max(1, len(latest)))
    cols = st.columns(ncols)
    print(f"[DISPLAY] Rendering {len(latest)} live tanks using {ncols} columns.")

    for i, (name, state) in enumerate(sorted(latest.items())):
        with cols[i % ncols]:
            st.markdown(f"### {name}")
            level = state.get("level", 0.0)
            ts = state.get("timestamp", "")
            step = int(state.get("progress_step", 0))
            total = int(state.get("total_updates", 1))
            print(f"[DISPLAY] Tank: {name}, Level: {level:.3f}, Step: {step}/{total}, Timestamp: {ts}")

            st.metric("Level (m³)", f"{level:.3f}")

            pct = min(100, max(0, level / 10.0 * 100))
            h = int(pct * 1.5)

            html = f'''
            <div style="height:150px;width:120px;border:2px solid #555;border-radius:6px;
                        position:relative;overflow:hidden;background:#f0f2f6;margin:auto;">
                <div style="position:absolute;bottom:0;width:100%;height:{h}px;
                            background:#3B82F6;border-top:2px solid #1E40AF;
                            transition: height 0.3s ease;"></div>
                <div style="position:absolute;top:50%;width:100%;text-align:center;
                            font-weight:600;color:#111;transform:translateY(-50%);">
                    {pct:.0f}%
                </div>
            </div>
            '''
            st.markdown(html, unsafe_allow_html=True)
            st.progress(step / max(1, total))
            st.caption(f"{step} / {total} • {ts}")

# -------------------------
# Plot charts per tank
# -------------------------
st.markdown("---")
st.subheader("Real-time Charts (per-tank)")

for name in sorted(st.session_state.history.keys()):
    hist = st.session_state.history[name]
    if name not in st.session_state.chart_placeholders:
        st.session_state.chart_placeholders[name] = st.empty()

    placeholder = st.session_state.chart_placeholders[name]

    if hist:
        df = pd.DataFrame(hist[-MAX_CHART_POINTS:], columns=["Timestamp", "Level"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["Level"], mode="lines+markers", name=name))
        fig.update_layout(title=name, xaxis_title="Timestamp", yaxis_title="Level (m³)", height=300)
        placeholder.plotly_chart(fig, width='stretch')
        print(f"[CHART] Rendered chart for tank {name} ({len(df)} points)")

# -------------------------
# Display recent tank levels
# -------------------------
st.markdown("---")
st.subheader("Recent Tank Levels")
for name, state in sorted(latest.items()):
    ts = state.get('timestamp', '')
    level = state.get('level', 0.0)
    st.write(f"**{name}** — {ts} — level {level:.3f} m³")
    print(f"[RECENT] Tank: {name}, Timestamp: {ts}, Level: {level:.3f} m³")

st.caption(f"Note: This Streamlit UI polls the backend every {POLL_INTERVAL_SEC} seconds and updates **one event at a time**.")
print("[INFO] Streamlit frontend update complete.\n")