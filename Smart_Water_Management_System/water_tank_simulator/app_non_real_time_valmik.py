import streamlit as st
import threading
import time
import csv
from collections import deque
from typing import Dict, Any, List, Optional
import os
import sys
import random
from datetime import datetime

# =================================================================
# 1. SHARED DATA QUEUE (Communication Bridge)
# =================================================================

@st.cache_resource
def get_update_queue() -> deque:
    """Initializes the single, thread-safe queue for data transfer."""
    return deque()

UPDATE_QUEUE = get_update_queue()

# =================================================================
# 2. CSV LOADER AND NORMALIZER
# =================================================================

def load_and_normalize_data(csv_path: str, batch_size: int = 10) -> Optional[List[List[Dict[str, Any]]]]:
    """
    Loads consumption data from CSV, computes global min/max of 'Consumption(Liters)',
    and returns a list of batches. Each batch contains data points with normalized values.
    """
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found at {csv_path}", file=sys.stderr)
        return None

    timestamps, consumptions = [], []

    try:
        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if "Date/Time" not in row or "Consumption(Liters)" not in row:
                    print(f"ERROR: Missing required headers in {csv_path}", file=sys.stderr)
                    return None
                try:
                    t = datetime.strptime(row["Date/Time"], "%Y-%m-%d %H:%M:%S")
                    v = float(row["Consumption(Liters)"])
                    timestamps.append(t)
                    consumptions.append(v)
                except Exception as e:
                    print(f"WARNING: Skipping invalid row: {row} ({e})", file=sys.stderr)
                    continue
    except Exception as e:
        print(f"ERROR reading {csv_path}: {e}", file=sys.stderr)
        return None

    if not consumptions:
        return None

    # Normalize
    global_min, global_max = min(consumptions), max(consumptions)
    global_range = global_max - global_min if global_max != global_min else 1.0

    data_points = [
        {
            "timestamp": t.strftime("%Y-%m-%d %H:%M:%S"),
            "normalized_value": (v - global_min) / global_range
        }
        for t, v in zip(timestamps, consumptions)
    ]

    # Batch split
    batches = [
        data_points[i:i + batch_size] for i in range(0, len(data_points), batch_size)
    ]
    return batches

# =================================================================
# 3. BACKEND WORKER THREAD
# =================================================================

def run_tank_simulation(tank_id: str, csv_path: str, delay_seconds: float):
    """Simulates tank updates from CSV in real-time batches."""
    batches = load_and_normalize_data(csv_path)
    if not batches:
        UPDATE_QUEUE.append({"id": tank_id, "status": "Error", "message": f"Failed to load {csv_path}"})
        return

    total_points = sum(len(batch) for batch in batches)
    UPDATE_QUEUE.append({"id": tank_id, "total_updates": total_points})

    processed_points = 0
    for batch in batches:
        for point in batch:
            current_level = point["normalized_value"] * 10.0
            update = {
                "id": tank_id,
                "level": round(current_level, 2),
                "timestamp": point["timestamp"],
                "progress_step": processed_points + 1,
            }
            UPDATE_QUEUE.append(update)
            processed_points += 1
            time.sleep(delay_seconds)  # Simulate real-time update
        time.sleep(0.2)

    UPDATE_QUEUE.append({"id": tank_id, "status": "Finished"})

# =================================================================
# 4. CONFIGURATION (Manual CSV Paths)
# =================================================================

# ✅ EDIT THIS LIST to match your CSV files
CSV_PATHS = [
    "datasets/tank_alpha.csv",
    "datasets/tank_beta.csv",
    "datasets/sensor_readings.csv"
]

# =================================================================
# 5. STATE MANAGEMENT & UI INITIALIZATION
# =================================================================

def generate_tank_configs(csv_paths: List[str]) -> Dict[str, Dict[str, Any]]:
    """Generates one tank config per CSV path."""
    configs = {}
    for i, path in enumerate(csv_paths, start=1):
        tank_name = f"Tank {i}"
        configs[tank_name] = {
            "initial_level": random.uniform(2.0, 9.0),
            "delay": random.uniform(0.5, 1.0),
            "csv_path": path
        }
    return configs

def initialize_session_state(configs: Dict[str, Dict[str, Any]]):
    """Sets up Streamlit session state for tanks."""
    if st.session_state.get("simulation_running", False):
        st.session_state.simulation_running = False
        time.sleep(0.5)

    st.session_state.tank_states = {}
    for name, cfg in configs.items():
        st.session_state.tank_states[name] = {
            "level": cfg["initial_level"],
            "prev_level": cfg["initial_level"],
            "status": "Idle",
            "total_updates": 1,
            "current_step": 0,
            "csv_path": cfg["csv_path"]
        }
    st.session_state.simulation_running = False
    st.session_state.worker_threads = []

# =================================================================
# 6. STREAMLIT FRONTEND
# =================================================================

st.set_page_config(layout="wide", page_title="💧 Dynamic Batch Water Tank Digital Twin")
st.title("💧 Dynamic Batch Water Tank Digital Twin")

# Sidebar
with st.sidebar:
    st.header("Configuration")
    st.write("You have manually specified CSV files:")
    for i, path in enumerate(CSV_PATHS, start=1):
        st.caption(f"{i}. `{path}`")

TANK_CONFIGS = generate_tank_configs(CSV_PATHS)

if "tank_states" not in st.session_state:
    initialize_session_state(TANK_CONFIGS)

# Start button
if st.button("🚀 Start / Restart Simulation", type="primary"):
    initialize_session_state(TANK_CONFIGS)

    st.session_state.worker_threads = []
    for name, cfg in TANK_CONFIGS.items():
        st.session_state.tank_states[name]["status"] = "Loading"
        thread = threading.Thread(
            target=run_tank_simulation,
            args=(name, cfg["csv_path"], cfg["delay"]),
            daemon=True
        )
        st.session_state.worker_threads.append(thread)
        thread.start()

    st.session_state.simulation_running = True
    st.experimental_rerun()

# =================================================================
# 7. DISPLAY LOOP
# =================================================================

def update_simulation_display():
    """Polls queue and updates dashboard in real-time."""
    if st.session_state.get("simulation_running", False):
        while UPDATE_QUEUE:
            try:
                update = UPDATE_QUEUE.popleft()
                tank_id = update.get("id")
                if not tank_id:
                    continue

                tank_state = st.session_state.tank_states.get(tank_id)
                if not tank_state:
                    continue

                if "total_updates" in update:
                    tank_state["total_updates"] = int(update["total_updates"])
                    tank_state["status"] = "Processing"

                elif "level" in update:
                    tank_state["prev_level"] = tank_state["level"]
                    tank_state["level"] = float(update["level"])
                    tank_state["status"] = "Processing"
                    tank_state["timestamp"] = update.get("timestamp")
                    tank_state["current_step"] = int(update.get("progress_step", 0))

                elif "status" in update and update["status"] in ["Finished", "Error"]:
                    tank_state["status"] = update["status"]
                    if "message" in update:
                        tank_state["message"] = update["message"]

            except Exception as e:
                st.error(f"Error processing update: {e}")
                break

    st.subheader("Batch Status Overview")
    cols = st.columns(min(len(st.session_state.tank_states), 4))

    for i, (tank_name, data) in enumerate(st.session_state.tank_states.items()):
        with cols[i % len(cols)]:
            st.metric(
                label=tank_name,
                value=f"{data.get('level', 0.0):.2f} m³",
                delta=f"{(data.get('level', 0.0) - data.get('prev_level', 0.0)):.2f} m³"
                if data.get("status") == "Processing" else None,
            )

            if data.get("status") in ["Processing", "Finished"]:
                progress = min(max(data.get("current_step", 0) / data.get("total_updates", 1), 0.0), 1.0)
                st.progress(progress)
                st.caption(f"Data Points: {data.get('current_step', 0)} / {data.get('total_updates', 1)}")

            if data.get("status") == "Finished":
                st.success("✅ Complete")
            elif data.get("status") == "Error":
                st.error(f"❌ Error loading {data.get('csv_path')}")
            elif data.get("status") == "Processing":
                st.caption(f"⏱ Last Update: {data.get('timestamp', '')}")
            else:
                st.info("Idle")

update_simulation_display()

finished_count = sum(1 for t in st.session_state.tank_states.values() if t.get("status") == "Finished")
if st.session_state.get("simulation_running", False) and finished_count == len(st.session_state.tank_states):
    st.session_state.simulation_running = False
    st.success("🎉 All batch processing threads have concluded.")