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
# ABSOLUTE PATH OF THIS SCRIPT (for relative CSV loading)
# =================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =================================================================
# GLOBALS: queue and stop-events for threads
# =================================================================

UPDATE_QUEUE: deque = deque()
RUN_EVENTS: Dict[str, threading.Event] = {}

# =================================================================
# SHARED QUEUE SINGLETON
# =================================================================

@st.cache_resource
def get_update_queue() -> deque:
    return UPDATE_QUEUE

UPDATE_QUEUE = get_update_queue()

# =================================================================
# CREATE TANK CONFIGS (MISSING FUNCTION FIXED)
# =================================================================

def generate_tank_configs(csv_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    configs = {}
    for idx, p in enumerate(csv_paths, start=1):
        base = os.path.splitext(os.path.basename(p))[0]
        tank_name = base if base else f"Tank {idx}"
        if tank_name in configs:
            tank_name = f"{tank_name}_{idx}"
        configs[tank_name] = {
            "initial_level": 0.0,
            "csv_path": p
        }
    return configs

# =================================================================
# CSV PARSING HELPERS (robust header detection)
# =================================================================

def _try_parse_datetime(s: str) -> Optional[datetime]:
    if not s:
        return None

    s = s.strip()
    if not s:
        return None

    fmts = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
        "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
        "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y",
        "%H:%M:%S", "%H:%M"
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass

    # Try ISO-like format
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        pass

    # Try to strip timezone designators and parse basic
    try:
        s2 = re.sub(r"[TZ]", " ", s)
        return datetime.fromisoformat(s2.strip())
    except Exception:
        pass

    return None


def load_and_normalize_data(csv_path: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """
    Loads CSV, automatically detects timestamp and value columns using fuzzy matching,
    converts values to float and returns a list of normalized points (0..1).
    """

    if not os.path.exists(csv_path):
        return None, f"File not found: {csv_path}"

    timestamps: List[datetime] = []
    consumptions: List[float] = []

    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames or []

            # If no headers, return helpful error
            if not fieldnames:
                return None, "CSV has no header row."

            # Build a normalized key -> original header map
            norm_map: Dict[str, str] = {}
            for h in fieldnames:
                if h is None:
                    continue
                # Normalize: lowercase, remove spaces, underscores, slashes, parentheses, units
                k = h.lower()
                # remove common punctuation/units
                k = re.sub(r"[\s_()\-\[\]/:\\]", "", k)
                # remove units like liters, m3, etc
                k = re.sub(r"liters|liter|l|m3|m³|kg|g", "", k)
                norm_map[k] = h

            # 1) Preferred exact normalized names (already stripped)
            time_candidates = ["timestamp", "datetime", "date", "time", "datetimeutc", "dateutc", "ts"]
            value_candidates = ["consumption", "consum", "value", "level", "volume", "flow", "reading"]

            time_key = None
            value_key = None

            for cand in time_candidates:
                if cand in norm_map:
                    time_key = norm_map[cand]
                    break

            for cand in value_candidates:
                if cand in norm_map:
                    value_key = norm_map[cand]
                    break

            # 2) Fuzzy substring match if exact not found
            if not time_key:
                for nk, orig in norm_map.items():
                    if "time" in nk or "date" in nk or nk.endswith("ts") or nk.startswith("ts"):
                        time_key = orig
                        break

            if not value_key:
                for nk, orig in norm_map.items():
                    if "consum" in nk or "level" in nk or "volume" in nk or "flow" in nk or "read" in nk:
                        value_key = orig
                        break

            # 3) Try original header matching (case-insensitive) for some common verbose names
            if not time_key:
                for orig in fieldnames:
                    if re.search(r"date.?time|time.?stamp|time|date", orig, flags=re.I):
                        time_key = orig
                        break

            if not value_key:
                for orig in fieldnames:
                    if re.search(r"consum|consumption|level|volume|flow|reading|value", orig, flags=re.I):
                        value_key = orig
                        break

            # If still missing, return an error with helpful info
            if not time_key or not value_key:
                return None, f"Missing timestamp/value columns in {csv_path}. Available headers: {fieldnames}"

            # Now iterate rows and parse
            for row in reader:
                # Use .get to avoid KeyError if header spelled unexpectedly
                raw_time = row.get(time_key, "")
                parsed_ts = _try_parse_datetime(str(raw_time).strip())
                if parsed_ts is None:
                    # skip rows with invalid timestamp
                    continue

                raw_val = row.get(value_key, "")
                if raw_val is None:
                    continue
                raw_val_s = str(raw_val).strip()
                if raw_val_s == "":
                    continue

                # Remove thousands separators and currency/unit characters, keep minus and dot and digits
                cleaned = re.sub(r"[^\d\.\-eE]", "", raw_val_s)
                try:
                    v = float(cleaned)
                except Exception:
                    # try replacing comma decimal (e.g., "1,23")
                    s2 = raw_val_s.replace(",", ".")
                    try:
                        v = float(re.sub(r"[^\d\.\-eE]", "", s2))
                    except Exception:
                        continue

                timestamps.append(parsed_ts)
                consumptions.append(v)

    except Exception as e:
        return None, f"CSV read error: {e}"

    if not consumptions:
        return None, f"No valid numeric rows found in {os.path.basename(csv_path)} (checked headers: {fieldnames})"

    # Sort by timestamp
    combined = sorted(zip(timestamps, consumptions), key=lambda x: x[0])
    timestamps_sorted, consumptions_sorted = zip(*combined)

    # Normalize across whole CSV
    gmin, gmax = min(consumptions_sorted), max(consumptions_sorted)
    grange = gmax - gmin if gmax != gmin else 1.0

    data_points: List[Dict[str, Any]] = []
    for t, v in zip(timestamps_sorted, consumptions_sorted):
        data_points.append({
            "timestamp": t.strftime("%Y-%m-%d %H:%M:%S"),
            "normalized_value": (v - gmin) / grange
        })

    return data_points, ""

# =================================================================
# BACKGROUND THREAD WORKER
# =================================================================

def run_tank_simulation(tank_id: str, csv_path: str, delay_seconds: float, stop_event: threading.Event):

    data, err = load_and_normalize_data(csv_path)
    if not data:
        UPDATE_QUEUE.append({"id": tank_id, "status": "Error", "message": err})
        return

    UPDATE_QUEUE.append({"id": tank_id, "total_updates": len(data)})

    for i, d in enumerate(data, start=1):
        if stop_event.is_set():
            UPDATE_QUEUE.append({"id": tank_id, "status": "Error", "message": "Stopped by user"})
            return

        UPDATE_QUEUE.append({
            "id": tank_id,
            "level": round(d["normalized_value"] * 10.0, 2),
            "timestamp": d["timestamp"],
            "progress_step": i
        })

        time.sleep(delay_seconds)

    UPDATE_QUEUE.append({"id": tank_id, "status": "Finished"})

# =================================================================
# TANK VISUAL (HTML)
# =================================================================

def render_tank_visual(level: float, max_level: float = 10.0):

    pct = min(100, max(0, level / max_level * 100))
    h = int(pct / 100 * 150)

    html = f"""
    <div style="
        height:150px;width:120px;border:2px solid #555;border-radius:6px;
        background:#f0f2f6;position:relative;overflow:hidden;margin:auto;">
        <div style="
            position:absolute;bottom:0;width:100%;height:{h}px;
            background:#3B82F6;border-top:2px solid #1E40AF;
            transition:height .4s ease;">
        </div>
        <div style="position:absolute;top:50%;width:100%;text-align:center;
            font-weight:600;color:#111;transform:translateY(-50%);">
            {pct:.0f}%</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# =================================================================
# RELATIVE CSV FILES (update these relative paths if needed)
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
# SESSION INITIALIZER
# =================================================================

def initialize_session_state_wrapper(cfgs):

    for ev in RUN_EVENTS.values():
        ev.set()
    RUN_EVENTS.clear()

    st.session_state.tank_states = {
        name: {
            "level": cfg["initial_level"],
            "prev_level": cfg["initial_level"],
            "status": "Idle",
            "total_updates": 1,
            "current_step": 0,
            "csv_path": cfg["csv_path"]
        }
        for name, cfg in cfgs.items()
    }

    st.session_state.simulation_running = False
    st.session_state.worker_threads = []

if "tank_states" not in st.session_state:
    initialize_session_state_wrapper(TANK_CONFIGS)

# =================================================================
# STREAMLIT UI
# =================================================================

st.set_page_config(layout="wide", page_title="💧 Digital Twin Simulation")
st.title("💧 Dynamic Batch Water Tank Simulation")

with st.sidebar:
    st.header("Control Panel")
    st.markdown("---")
    global_delay = st.slider("Row Delay (s)", 0.0, 1.5, 0.5, 0.05)

    st.markdown("---")
    st.subheader("CSV Files Status")
    for f, p in zip(CSV_FILENAMES, CSV_PATHS):
        st.caption(f"✅ {f}" if os.path.exists(p) else f"❌ {f} (missing)")

    st.markdown("---")
    st.write("Base folder (script):", BASE_DIR)

# --- Start Simulation ---
if st.button("🚀 Start / Restart Simulation"):

    initialize_session_state_wrapper(TANK_CONFIGS)
    st.session_state.simulation_running = True

    # spawn worker threads
    for name, cfg in TANK_CONFIGS.items():
        ev = threading.Event()
        RUN_EVENTS[name] = ev
        st.session_state.tank_states[name]["status"] = "Loading"

        t = threading.Thread(
            target=run_tank_simulation,
            args=(name, cfg["csv_path"], float(global_delay), ev),
            daemon=True
        )
        st.session_state.worker_threads.append(t)
        t.start()

    st.rerun()

# --- Stop Simulation ---
if st.button("⏹ Stop Simulation"):
    for ev in RUN_EVENTS.values():
        ev.set()
    st.session_state.simulation_running = False
    time.sleep(0.2)
    st.rerun()

# =================================================================
# UPDATE QUEUE PROCESSING
# =================================================================

if st.session_state.get("simulation_running", False):
    while UPDATE_QUEUE:
        try:
            upd = UPDATE_QUEUE.popleft()
        except IndexError:
            break

        tid = upd.get("id")
        if not tid or tid not in st.session_state.tank_states:
            continue

        s = st.session_state.tank_states[tid]

        if "total_updates" in upd:
            s["total_updates"] = int(upd["total_updates"])
            s["status"] = "Processing"

        elif "level" in upd:
            s["prev_level"] = s.get("level", 0.0)
            s["level"] = float(upd["level"])
            s["timestamp"] = upd.get("timestamp", "")
            s["current_step"] = int(upd.get("progress_step", s.get("current_step", 0)))
            s["status"] = "Processing"

        elif upd.get("status") in ("Finished", "Error"):
            s["status"] = upd["status"]
            if "message" in upd:
                s["message"] = upd["message"]

# =================================================================
# DISPLAY
# =================================================================

st.subheader("Tank Status Overview")

ncols = min(4, max(1, len(st.session_state.tank_states)))
cols = st.columns(ncols)

for i, (name, data) in enumerate(st.session_state.tank_states.items()):
    with cols[i % ncols]:
        val = data.get("level", 0.0)
        prev = data.get("prev_level", val)
        delta = f"{val - prev:.2f} m³" if val != prev else None

        st.markdown(f"### {name}")
        st.metric("Current Level", f"{val:.2f} m³", delta)

        render_tank_visual(val)

        if data.get("status") in ("Processing", "Finished"):
            pct = data.get("current_step", 0) / max(1, data.get("total_updates", 1))
            st.progress(pct)
            st.caption(f"{data.get('current_step',0)} / {data.get('total_updates',1)}")

        status = data.get("status", "Idle")
        if status == "Finished":
            st.success("✅ Complete")
        elif status == "Error":
            st.error(f"❌ {data.get('message','Error')}")
        elif status == "Loading":
            st.info("Loading data...")
        elif status == "Processing":
            st.caption(f"⏱ Last Update: {data.get('timestamp','')}")
        else:
            st.info("Idle")

# =================================================================
# FINAL RUN COMPLETE DETECTION
# =================================================================

if st.session_state.get("simulation_running", False):
    all_done = all(s.get("status") in ("Finished", "Error") for s in st.session_state.tank_states.values())
    if all_done:
        for ev in RUN_EVENTS.values():
            ev.set()
        RUN_EVENTS.clear()
        st.session_state.simulation_running = False
        st.success("🎉 All simulations completed.")
        st.rerun()