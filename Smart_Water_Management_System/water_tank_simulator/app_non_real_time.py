import streamlit as st
import threading
import time
import csv
from collections import deque
from typing import Dict, Any, List, Optional
import os
import sys
import random

# =================================================================
# 1. SHARED DATA QUEUE (The Communication Bridge)
# The queue is cached to be a Singleton object across the entire process.
# =================================================================

@st.cache_resource
def get_update_queue() -> deque:
    """Initializes the single, thread-safe queue for data transfer."""
    return deque()

# Get the single instance of the queue
UPDATE_QUEUE = get_update_queue()


# =================================================================
# HELPER FUNCTIONS FOR BATCH PROCESSING (CSV I/O)
# =================================================================

def load_and_normalize_data(csv_path: str) -> Optional[List[Dict[str, Any]]]:
    """
    Loads consumption data from CSV, computes min/max range, and returns
    normalized values (0 to 1) along with timestamps.

    Expects CSV headers: 'Timestamp' and 'Consumption'
    """
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found at {csv_path}", file=sys.stderr)
        return None

    times: List[str] = []
    values: List[float] = []

    try:
        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # defensive checks
                if "Timestamp" not in row or "Consumption" not in row:
                    print(f"ERROR: CSV missing required headers in {csv_path}", file=sys.stderr)
                    return None
                t = row["Timestamp"]
                try:
                    v = float(row["Consumption"])
                except ValueError:
                    # skip invalid rows but log
                    print(f"WARNING: Skipping row with non-numeric Consumption value: {row}", file=sys.stderr)
                    continue
                times.append(t)
                values.append(v)
    except Exception as e:
        print(f"ERROR reading {csv_path}: {e}", file=sys.stderr)
        return None

    if not values:
        return None

    # --- Scaling / Normalization Logic (Calculated per batch) ---
    min_val, max_val = min(values), max(values)
    val_range = max_val - min_val if max_val != min_val else 1.0

    data_points: List[Dict[str, Any]] = []
    for t_str, v in zip(times, values):
        # Normalized value between 0.0 and 1.0 based on the tank's historical data range
        normalized_value = (v - min_val) / val_range
        data_points.append({
            "timestamp": t_str,
            "normalized_value": normalized_value,
        })

    return data_points


# =================================================================
# 2. BACKEND WORKERS (Batch Processor - runs in separate threads)
# These functions do NOT call any 'st.' commands.
# =================================================================

def run_tank_simulation(tank_id: str, csv_path: str, delay_seconds: float):
    """
    Loads data from CSV, performs batch processing, and pushes updates to the queue.
    """

    # 1. Load and Normalize Data (Batch processing logic per thread)
    data_points = load_and_normalize_data(csv_path)

    if not data_points:
        UPDATE_QUEUE.append({"id": tank_id, "status": "Error", "message": f"CSV data failed to load for {tank_id} at {csv_path}"})
        return

    # 2. Initial Push: Send the total number of updates for the progress tracker
    UPDATE_QUEUE.append({"id": tank_id, "total_updates": len(data_points)})

    # 3. Batch Processing Loop (Pushes updates sequentially)
    for i, point in enumerate(data_points):
        # Scale the normalized value (0.0 to 1.0) up to the display max (10.0)
        current_level = point["normalized_value"] * 10.0

        # 4. Package the update
        update = {
            "id": tank_id,
            "level": round(current_level, 2),
            "timestamp": point["timestamp"],
            "progress_step": i + 1,
        }

        # 5. Push update into the thread-safe queue
        UPDATE_QUEUE.append(update)

        # 6. Wait (simulating the time interval between data points)
        time.sleep(max(0.0, float(delay_seconds)))

    # Mark tank as finished
    UPDATE_QUEUE.append({"id": tank_id, "status": "Finished"})


# =================================================================
# 3. STREAMLIT FRONTEND (UI, State Manager, and Polling)
# =================================================================

# --- Utility to dynamically generate configuration based on user input ---
def generate_tank_configs(num_tanks: int) -> Dict[str, Dict[str, Any]]:
    configs: Dict[str, Dict[str, Any]] = {}
    for i in range(1, num_tanks + 1):
        tank_name = f"Tank {i}"
        configs[tank_name] = {
            "initial_level": random.uniform(2.0, 9.0),  # Random initial level for stability
            "delay": random.uniform(0.3, 0.8),         # Random delay for staggered updates
            "csv_path": f"data_tank{i}.csv"
        }
    return configs

# --- State Initialization ---


def initialize_session_state(configs: Dict[str, Dict[str, Any]]):
    """Sets up initial state and worker thread list based on current configuration."""
    # Clean up old threads if necessary
    if st.session_state.get("simulation_running", False):
        st.session_state.simulation_running = False
        # small pause to allow running threads to see the flag (best-effort)
        time.sleep(0.5)

    # Reset state variables
    st.session_state.tank_states = {}
    for name, cfg in configs.items():
        st.session_state.tank_states[name] = {
            "level": cfg["initial_level"],
            "status": "Idle",
            "prev_level": cfg["initial_level"],
            "total_updates": 1,
            "current_step": 0,
            "csv_path": cfg["csv_path"]
        }
    st.session_state.simulation_running = False
    st.session_state.worker_threads = []


# --- Main Page Setup ---
st.set_page_config(layout="wide", page_title="Dynamic Batch Water Tank Digital Twin")
st.title("💧 Dynamic Batch Water Tank Digital Twin")

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("Configuration")
    num_tanks = st.number_input(
        "Number of Tanks (CSVs)",
        min_value=1,
        max_value=10,
        value=3,
        step=1,
        key="num_tanks"
    )
    st.info(f"The simulation expects {num_tanks} files named: `data_tank1.csv` to `data_tank{num_tanks}.csv`")

# Dynamically generate configurations
TANK_CONFIGS = generate_tank_configs(st.session_state.num_tanks)

# Initialize state if it doesn't exist, or if the number of tanks changed
if "tank_states" not in st.session_state or len(st.session_state.tank_states) != st.session_state.num_tanks:
    initialize_session_state(TANK_CONFIGS)


# --- Start Button Logic ---
if st.button("Start/Restart Batch Processing", type="primary"):

    # 1. Reset state with current config
    initialize_session_state(TANK_CONFIGS)

    # 2. Spawn and start new worker threads
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
    # trigger a rerun so UI picks up new threads immediately
    st.experimental_rerun()


# --- Polling and Display Logic (The Consumer) ---

def update_simulation_display():
    """
    Processes items in UPDATE_QUEUE and renders the dashboard UI.
    Call this function from the main script to display updates.
    """

    # 1. Process updates from the Queue
    if st.session_state.get("simulation_running", False):

        while UPDATE_QUEUE:
            try:
                update = UPDATE_QUEUE.popleft()
                tank_id = update.get("id")
                if tank_id is None:
                    continue

                tank_state = st.session_state.tank_states.get(tank_id)
                if not tank_state:
                    continue

                # Initial update for total size (comes first)
                if "total_updates" in update:
                    tank_state["total_updates"] = int(update["total_updates"])
                    tank_state["status"] = "Processing"

                # Update with new data point
                elif "level" in update:
                    tank_state["prev_level"] = tank_state.get("level", 0.0)
                    tank_state["level"] = float(update["level"])
                    tank_state["status"] = "Processing"
                    tank_state["timestamp"] = update.get("timestamp")
                    tank_state["current_step"] = int(update.get("progress_step", tank_state.get("current_step", 0)))

                # Final status update
                elif "status" in update and update["status"] == "Finished":
                    tank_state["status"] = "Finished"

                # Error status update
                elif "status" in update and update["status"] == "Error":
                    tank_state["status"] = "Error"
                    tank_state["message"] = update.get("message", "Check console")

            except IndexError:
                break
            except Exception as e:
                st.error(f"Error processing queue update: {e}")
                break

    # 2. Draw the Dashboard UI using columns
    st.subheader(f"Batch Status ({len(st.session_state.tank_states)} Tanks)")

    # Dynamically handle column layout (up to 4 columns max for neatness)
    num_tanks = len(st.session_state.tank_states)
    cols = st.columns(min(num_tanks, 4)) if num_tanks > 0 else [st.container()]

    # Iterate through the definitive source of truth: st.session_state.tank_states
    for i, (tank_name, data) in enumerate(st.session_state.tank_states.items()):

        # Use modulo to cycle through columns
        with cols[i % len(cols)]:
            # --- Metric Display ---
            current_level = float(data.get('level', 0.0))
            prev_level = float(data.get('prev_level', current_level))

            # Calculate delta
            delta = round(current_level - prev_level, 2)
            delta_str = f"{delta:.2f} m³"

            st.metric(
                label=f"{tank_name}",
                value=f"{current_level:.2f} m³",
                delta=delta_str if data.get('status') == "Processing" and delta != 0.0 else None,
            )

            # --- Progress Bar Display ---
            total_updates = int(data.get("total_updates", 1))
            if total_updates > 0 and data.get('status') not in ["Idle", "Error"]:
                step = int(data.get("current_step", 0))
                total = total_updates
                # safe progress percent guard
                progress_percent = 0.0
                if total > 0:
                    progress_percent = min(max(step / total, 0.0), 1.0)
                # st.progress expects 0..1 fraction
                st.progress(progress_percent)
                st.caption(f"Data Points: {step} / {total}")

            # --- Status Display ---
            if data.get('status') == "Finished":
                ts = data.get('timestamp', '')
                st.success(f"Complete ({ts})" if ts else "Complete")
            elif data.get('status') == "Error":
                st.error(f"Failed to process '{data.get('csv_path', '')}'")
            elif data.get('status') == "Processing":
                st.caption(f"Last Update: {data.get('timestamp', '')}")
            else:
                st.info(data.get('status', 'Idle'))


# Run the update / render function once per run.
# For periodic updates you can add st_autorefresh or use st.experimental_rerun appropriately.
update_simulation_display()

# Final status check for the bottom of the page
finished_count = sum(1 for data in st.session_state.tank_states.values() if data.get('status') == "Finished")

if st.session_state.get("simulation_running", False) and finished_count == len(st.session_state.tank_states):
    st.session_state.simulation_running = False
    st.success("All batch processing threads have concluded.")