import streamlit as st
import threading
import time
import random
from collections import deque
from datetime import datetime
from typing import Dict, Any

# =================================================================
# 1. SHARED DATA QUEUE (The Communication Bridge)
# The queue is cached to be a Singleton object across the entire process, 
# ensuring all threads and the main Streamlit script access the same queue.
# =================================================================

@st.cache_resource
def get_update_queue() -> deque:
    """Initializes the single, thread-safe queue for data transfer."""
    return deque()

# Get the single instance of the queue
UPDATE_QUEUE = get_update_queue()


# =================================================================
# 2. BACKEND WORKERS (The Push Simulators - run in separate threads)
# These functions do NOT call any 'st.' commands.
# =================================================================

def run_tank_simulation(tank_id: str, initial_level: float, delay_seconds: float):
    """
    Simulates water level changes for a single tank in a background thread.
    Pushes updates to the global queue.
    """
    current_level = initial_level
    
    # Simulate a run time limit for demonstration (e.g., 60 seconds)
    start_time = time.time()
    SIMULATION_DURATION = 60
    
    while time.time() - start_time < SIMULATION_DURATION:
        try:
            # 1. Simulate change (Consumption/Usage)
            # Random consumption/refill rate between -0.8 and +0.8
            consumption_rate = random.uniform(-0.8, 0.8) * delay_seconds 
            current_level = max(0.0, min(10.0, current_level + consumption_rate)) # Max level 10
            
            # 2. Package the update
            update = {
                "id": tank_id,
                "level": round(current_level, 2),
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }
            
            # 3. Push update into the thread-safe queue
            UPDATE_QUEUE.append(update)
            
            # 4. Wait for the next cycle (simulating real-time data push interval)
            time.sleep(delay_seconds)
            
        except Exception as e:
            print(f"Error in Tank {tank_id} simulation thread: {e}")
            break
    
    # Mark tank as finished
    UPDATE_QUEUE.append({"id": tank_id, "status": "Finished"})
    print(f"Thread for {tank_id} finished.")


# =================================================================
# 3. STREAMLIT FRONTEND (UI, State Manager, and Polling)
# =================================================================

# --- Configuration & Initial State ---
TANK_CONFIGS = {
    "Tank A (Industrial)": {"initial_level": 7.5, "delay": 0.5},
    "Tank B (Residential)": {"initial_level": 4.0, "delay": 0.3},
    "Tank C (Cooling Tower)": {"initial_level": 8.8, "delay": 0.8},
}

def initialize_session_state():
    """Sets up initial state and worker thread list."""
    if "tank_states" not in st.session_state:
        st.session_state.tank_states: Dict[str, Dict[str, Any]] = {}
        for name, cfg in TANK_CONFIGS.items():
            st.session_state.tank_states[name] = {
                "level": cfg["initial_level"],
                "status": "Idle",
                "prev_level": cfg["initial_level"] # For delta calculation
            }
        st.session_state.simulation_running = False
        st.session_state.worker_threads: List[threading.Thread] = []

initialize_session_state()

st.set_page_config(layout="wide", page_title="Real-Time Water Tank Digital Twin")
st.title("💧 Real-Time Water Tank Digital Twin")
st.caption("Parallel simulation and update using background threads and a cached queue.")

# --- Start Button Logic ---
if st.button("Start/Restart Simulation", type="primary"):
    # Clean up old threads if necessary
    if st.session_state.simulation_running:
        st.session_state.simulation_running = False
        time.sleep(1) # Give existing threads a moment to shut down gracefully
    
    # 1. Reset state
    initialize_session_state()
    
    # 2. Spawn and start new worker threads
    st.session_state.worker_threads = []
    for name, cfg in TANK_CONFIGS.items():
        st.session_state.tank_states[name]["status"] = "Running"
        thread = threading.Thread(
            target=run_tank_simulation,
            args=(name, cfg["initial_level"], cfg["delay"]),
            daemon=True
        )
        st.session_state.worker_threads.append(thread)
        thread.start()
        
    st.session_state.simulation_running = True
    st.rerun() # Force a rerun to show the 'Running' status immediately


# --- Polling and Display Logic (The Consumer) ---

@st.experimental_fragment(run_every="500ms") # Poll the queue every 500ms
def update_simulation_display():
    
    # 1. Process updates from the Queue
    if st.session_state.simulation_running:
        
        while UPDATE_QUEUE:
            try:
                update = UPDATE_QUEUE.popleft() # Safely read data from the queue
                tank_id = update["id"]
                
                # Check if the update is a level or a status
                if "level" in update:
                    # Update the level and previous level for delta calculation
                    st.session_state.tank_states[tank_id]["prev_level"] = \
                        st.session_state.tank_states[tank_id]["level"]
                    st.session_state.tank_states[tank_id]["level"] = update["level"]
                    st.session_state.tank_states[tank_id]["status"] = "Updating"
                    st.session_state.tank_states[tank_id]["timestamp"] = update.get("timestamp")
                
                elif "status" in update and update["status"] == "Finished":
                    st.session_state.tank_states[tank_id]["status"] = "Finished"
                    
            except IndexError:
                # Queue is empty
                break
            except Exception as e:
                st.error(f"Error processing queue update: {e}")
                break

    # 2. Draw the Dashboard UI using columns
    st.subheader("Live Status")
    cols = st.columns(len(st.session_state.tank_states))
    
    # Iterate through the DEFINITIVE source of truth: st.session_state.tank_states
    for i, (tank_name, data) in enumerate(st.session_state.tank_states.items()):
        with cols[i]:
            
            current_level = data['level']
            prev_level = data['prev_level']
            
            # Calculate delta for the metric widget
            delta = round(current_level - prev_level, 2)
            delta_str = f"{delta:.2f} m³"
            
            # Display the main metric
            st.metric(
                label=f"Tank: {tank_name}",
                value=f"{current_level:.2f} m³",
                delta=delta_str if delta != 0.0 else None,
            )
            
            # Visual progress bar (Max Level = 10.0)
            progress = current_level / 10.0
            st.progress(progress, text=f"Fill: {int(progress * 10)} / 10")
            
            # Display status
            status_text = f"Status: {data['status']}"
            if data['status'] == "Updating":
                st.caption(f"Last update: {data['timestamp']}")
            elif data['status'] == "Finished":
                st.success("Simulation Complete")
            else:
                st.info("Awaiting Start")


# Run the update fragment
update_simulation_display()

# Final status check for the bottom of the page
finished_count = sum(1 for data in st.session_state.tank_states.values() if data.get('status') == "Finished")

if st.session_state.simulation_running and finished_count == len(TANK_CONFIGS):
    st.session_state.simulation_running = False
    st.success("All tank simulations have concluded.")