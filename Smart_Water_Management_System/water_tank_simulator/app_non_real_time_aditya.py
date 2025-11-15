import streamlit as st
import threading
import time
import csv
from collections import deque
from typing import Dict, Any, List, Optional, Tuple
import os
from datetime import datetime
import re

# =================================================================
# ABSOLUTE PATH OF THIS SCRIPT
# =================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =================================================================
# QUEUE + RUN EVENTS
# =================================================================

UPDATE_QUEUE: deque = deque()
RUN_EVENTS: Dict[str, threading.Event] = {}

@st.cache_resource
def get_update_queue() -> deque:
    return UPDATE_QUEUE

UPDATE_QUEUE = get_update_queue()

# =================================================================
# PRELOAD CSVs (raw values)
# Precompute only gmin, gmax, grange.
# Normalize each row ON THE FLY during simulation.
# =================================================================

def _try_parse_datetime(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    fmts = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y",
        "%H:%M:%S", "%H:%M",
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except:
        return None

def preload_csv(csv_path: str):
    """
    Reads entire CSV once.
    Returns: (timestamps[], values[], gmin, gmax, grange, error_message)
    """
    if not os.path.exists(csv_path):
        return None, None, None, None, None, f"File not found: {csv_path}"

    timestamps = []
    values = []

    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            if not headers:
                return None, None, None, None, None, "CSV has no header row."

            norm_map = {}
            for h in headers:
                if h:
                    k = re.sub(r"[\s_()\-\[\]/:\\]", "", h.lower())
                    k = re.sub(r"liters|liter|l|m3|m³|kg|g", "", k)
                    norm_map[k] = h

            time_key = None
            value_key = None

            for cand in ["timestamp", "datetime", "date", "time", "ts"]:
                if cand in norm_map:
                    time_key = norm_map[cand]
                    break

            for cand in ["value", "volume", "level", "consumption", "flow"]:
                if cand in norm_map:
                    value_key = norm_map[cand]
                    break

            if not time_key:
                for h in headers:
                    if re.search(r"date|time|timestamp", h, re.I):
                        time_key = h
                        break

            if not value_key:
                for h in headers:
                    if re.search(r"value|volume|level|consum|flow", h, re.I):
                        value_key = h
                        break

            if not time_key or not value_key:
                return None, None, None, None, None, f"Missing timestamp/value columns. Headers: {headers}"

            for row in reader:
                ts_raw = row.get(time_key, "").strip()
                v_raw = row.get(value_key, "").strip()

                ts = _try_parse_datetime(ts_raw)
                if not ts:
                    continue

                # Clean numeric
                cleaned = re.sub(r"[^\d\.\-eE]", "", v_raw)
                try:
                    v = float(cleaned)
                except:
                    continue

                timestamps.append(ts)
                values.append(v)

    except Exception as e:
        return None, None, None, None, None, f"CSV read error: {e}"

    if not values:
        return None, None, None, None, None, "No numeric rows found."

    # sort by timestamp
    combined = sorted(zip(timestamps, values), key=lambda x: x[0])
    timestamps_sorted, values_sorted = zip(*combined)

    gmin = min(values_sorted)
    gmax = max(values_sorted)
    grange = gmax - gmin if gmax != gmin else 1.0

    return list(timestamps_sorted), list(values_sorted), gmin, gmax, grange, ""

# =================================================================
# TANK CONFIG CREATION
# =================================================================

def generate_tank_configs(csv_paths):
    configs = {}
    for idx, p in enumerate(csv_paths, 1):
        name = os.path.splitext(os.path.basename(p))[0]
        if name in configs:
            name = f"{name}_{idx}"
        configs[name] = {
            "csv_path": p,
            "initial_level": 0.0,
        }
    return configs

# =================================================================
# WORKER THREAD: Continuous simulation loop
# =================================================================

def run_tank_continuous(
    tank_id: str,
    timestamps: List[datetime],
    values: List[float],
    gmin: float,
    grange: float,
    delay_seconds: float,
    stop_event: threading.Event,
):
    """
    Continuous infinite simulation:
    - Each row → update once per cycle
    - Normalize on the fly
    - Sleep 1 second per row (or UI slider value)
    - Loop forever until STOP
    """

    total = len(values)
    UPDATE_QUEUE.append({"id": tank_id, "total_updates": total})

    idx = 0
    while not stop_event.is_set():
        raw_val = values[idx]
        ts = timestamps[idx].strftime("%Y-%m-%d %H:%M:%S")

        normalized = (raw_val - gmin) / grange
        tank_level = normalized * 10.0

        UPDATE_QUEUE.append({
            "id": tank_id,
            "level": round(tank_level, 2),
            "timestamp": ts,
            "progress_step": idx + 1,
        })

        time.sleep(delay_seconds)

        idx += 1
        if idx >= total:
            idx = 0  # loop forever

    UPDATE_QUEUE.append({"id": tank_id, "status": "Finished"})

# =================================================================
# TANK VISUAL
# =================================================================

def render_tank_visual(level):
    pct = min(100, max(0, level / 10.0 * 100))
    h = int(pct * 1.5)
    html = f"""
    <div style="height:150px;width:120px;border:2px solid #555;border-radius:6px;
        position:relative;overflow:hidden;background:#f0f2f6;margin:auto;">
        <div style="position:absolute;bottom:0;width:100%;height:{h}px;
            background:#3B82F6;border-top:2px solid #1E40AF;"></div>
        <div style="position:absolute;top:50%;width:100%;text-align:center;
            font-weight:600;color:#111;transform:translateY(-50%);">{pct:.0f}%</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# =================================================================
# CSV LIST (RELATIVE)
# =================================================================

CSV_FILENAMES = [
    "data/Water_History_A1FD_2025-05-16_06-58.csv",
    "data/Water_History_A1FD_2025-05-16_07-00.csv",
    "data/Water_History_A1FF_2025-05-16_06-58.csv",
    "data/Water_History_A1MD_2025-05-16_06-59.csv",
    "data/Water_History_A1MD_2025-05-16_07-00.csv",
    "data/Water_History_A2MFF_2025-05-16_07-00.csv",
    "data/Water_History_BTTF_2025-05-16_07-01.csv",
]

CSV_PATHS = [os.path.join(BASE_DIR, f) for f in CSV_FILENAMES]
TANK_CONFIGS = generate_tank_configs(CSV_PATHS)

# =================================================================
# SESSION INITIALIZATION
# =================================================================

if "tank_states" not in st.session_state:
    st.session_state.tank_states = {
        name: {
            "status": "Idle",
            "level": 0.0,
            "prev_level": 0.0,
            "current_step": 0,
            "total_updates": 1,
            "timestamp": "",
            "csv_path": cfg["csv_path"],
        }
        for name, cfg in TANK_CONFIGS.items()
    }
    st.session_state.sim_running = False
    st.session_state.worker_threads = []

# =================================================================
# UI
# =================================================================

st.set_page_config(layout="wide")
st.title("💧 Continuous Digital Twin Simulation")

with st.sidebar:
    st.header("Controls")
    delay_seconds = st.slider("Simulation Speed (s per row)", 0.1, 2.0, 1.0, 0.1)

    st.subheader("CSV Status")
    for f, p in zip(CSV_FILENAMES, CSV_PATHS):
        st.caption(f"✅ {f}" if os.path.exists(p) else f"❌ {f}")

# =================================================================
# BUTTON: START
# =================================================================

if st.button("🚀 Start Simulation"):
    # stop any old threads
    for ev in RUN_EVENTS.values():
        ev.set()
    RUN_EVENTS.clear()

    st.session_state.sim_running = True
    st.session_state.worker_threads = []

    # preload ALL CSVs before starting any thread
    preloaded = {}
    for name, cfg in TANK_CONFIGS.items():
        ts, vals, gmin, gmax, grange, err = preload_csv(cfg["csv_path"])
        if err:
            st.session_state.tank_states[name]["status"] = "Error"
            st.session_state.tank_states[name]["message"] = err
        else:
            preloaded[name] = (ts, vals, gmin, grange)

    # start threads
    for name, cfg in TANK_CONFIGS.items():
        if name not in preloaded:
            continue

        timestamps, values, gmin, grange = preloaded[name]

        ev = threading.Event()
        RUN_EVENTS[name] = ev
        st.session_state.tank_states[name]["status"] = "Processing"

        t = threading.Thread(
            target=run_tank_continuous,
            args=(name, timestamps, values, gmin, grange, delay_seconds, ev),
            daemon=True,
        )
        st.session_state.worker_threads.append(t)
        t.start()

    st.rerun()

# =================================================================
# BUTTON: STOP
# =================================================================

if st.button("⏹ Stop"):
    for ev in RUN_EVENTS.values():
        ev.set()
    st.session_state.sim_running = False
    time.sleep(0.2)
    st.rerun()

# =================================================================
# QUEUE PROCESSING
# =================================================================

if st.session_state.sim_running:
    while UPDATE_QUEUE:
        upd = UPDATE_QUEUE.popleft()
        name = upd.get("id")
        if name not in st.session_state.tank_states:
            continue
        s = st.session_state.tank_states[name]

        if "total_updates" in upd:
            s["total_updates"] = upd["total_updates"]

        if "level" in upd:
            s["prev_level"] = s["level"]
            s["level"] = upd["level"]
            s["timestamp"] = upd["timestamp"]
            s["current_step"] = upd["progress_step"]
            s["status"] = "Processing"

        if upd.get("status") == "Finished":
            s["status"] = "Idle"

# =================================================================
# DISPLAY
# =================================================================

st.subheader("Tank Overview")

cols = st.columns(4)
for i, (name, data) in enumerate(st.session_state.tank_states.items()):
    with cols[i % 4]:
        st.markdown(f"### {name}")

        level = data.get("level", 0)
        prev = data.get("prev_level", level)
        delta = level - prev

        st.metric("Level (m³)", f"{level:.2f}", f"{delta:+.2f}")

        render_tank_visual(level)

        pct = data.get("current_step", 0) / max(1, data.get("total_updates", 1))
        st.progress(pct)
        st.caption(f"{data['current_step']} / {data['total_updates']}")

        status = data.get("status", "Idle")
        if status == "Processing":
            st.caption(f"⏱ {data.get('timestamp','')}")
        elif status == "Idle":
            st.info("Idle")
        elif status == "Error":
            st.error(data.get("message", "Error"))