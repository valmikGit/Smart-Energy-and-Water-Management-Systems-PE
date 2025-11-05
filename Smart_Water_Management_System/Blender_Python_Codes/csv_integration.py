import bpy
import csv
from datetime import datetime

# ------------------------------------------------
# CONFIGURATION
# ------------------------------------------------
csv_file_path = r"C:\Users\Valmik Belgaonkar\OneDrive\Desktop\Smart-Energy-and-Water-Management-Systems-PE\Smart_Water_Management_System\campus_digital_twin\data\Water_History_A2MFF_2025-05-16_07-00.csv"  # 🔹 Change this to your CSV file path

tank_name = "Cylinder.003"    # Outer cylinder (tank)
water_name = "Liquid"         # Inner cylinder (water)
datetime_format = "%d-%m-%Y %H:%M"  # Format from your CSV
max_fill_height = None        # If None, it will fill to tank height
start_frame = 1

# 🔹 NEW: Simulation Time Scaling Rule
# How many real-world minutes are represented by 1 second in Blender
REAL_MINUTES_PER_SIM_SECOND = 30.0

# ------------------------------------------------
# OBJECT REFERENCES
# ------------------------------------------------
tank = bpy.data.objects.get(tank_name)
water = bpy.data.objects.get(water_name)

if not tank or not water:
    raise ValueError(f"Could not find objects '{tank_name}' or '{water_name}' in the scene.")

# Clear any previous animation data from the water object
water.animation_data_clear()
print(f"Found objects '{tank_name}' and '{water_name}'. Old animations cleared.")

# ------------------------------------------------
# LOAD CSV DATA
# ------------------------------------------------
times = []
totalizer_values = []

print(f"Loading CSV data from: {csv_file_path}")
with open(csv_file_path, newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    
    # Read all rows into a list first
    try:
        all_rows = list(reader)
    except Exception as e:
        raise ValueError(f"Error reading CSV. Check file path and encoding. Error: {e}")

    # 🔹 MODIFIED: Iterate in REVERSE (chronological order)
    # This ensures times[0] is the EARLIEST timestamp
    for row in reversed(all_rows):
        try:
            times.append(datetime.strptime(row["DateTime"], datetime_format))
            totalizer_values.append(float(row["Consumption"]))
        except Exception as e:
            print(f"⚠️ Skipping row due to error: {e}")

if not times or not totalizer_values:
    raise ValueError("No valid data found in CSV. Check file format, column names, and datetime_format.")

# Simulation start/end times are now correctly identified
sim_start_time = times[0]
sim_end_time = times[-1]
real_duration_seconds = (sim_end_time - sim_start_time).total_seconds()

print(f"✅ Data loaded: {len(times)} records.")
print(f"   Simulating from: {sim_start_time}")
print(f"   to: {sim_end_time}")
print(f"   Total real-world duration: {real_duration_seconds / 3600.0:.2f} hours")

# ------------------------------------------------
# 🔹 NEW: CALCULATE FRAMES BASED ON TIME SCALING
# ------------------------------------------------
print("Calculating simulation frames...")
# Get Blender's native frame rate (e.g., 24, 30, 60 fps)
fps = bpy.context.scene.render.fps
print(f"   Using Blender scene frame rate: {fps} fps")
print(f"   Using Rule: {REAL_MINUTES_PER_SIM_SECOND} real mins = 1 Blender second ({fps} frames)")

frames = []
for t in times:
    # 1. Get real seconds passed since the start
    real_seconds_passed = (t - sim_start_time).total_seconds()
    
    # 2. Convert to real minutes passed
    real_minutes_passed = real_seconds_passed / 60.0
    
    # 3. Convert real minutes to Blender simulation seconds
    sim_seconds_passed = real_minutes_passed / REAL_MINUTES_PER_SIM_SECOND
    
    # 4. Convert Blender seconds to Blender frames
    # Add start_frame to offset the entire animation
    current_frame = start_frame + (sim_seconds_passed * fps)
    
    frames.append(int(round(current_frame)))

# ------------------------------------------------
# NORMALIZE AND SCALE VALUES (Requirement 3)
# ------------------------------------------------
# This logic finds the min/max height from the Totalizer column
min_totalizer, max_totalizer = min(totalizer_values), max(totalizer_values)
range_totalizer = max_totalizer - min_totalizer if max_totalizer != min_totalizer else 1.0
normalized_totalizer = [(t - min_totalizer) / range_totalizer for t in totalizer_values]

print(f"   Totalizer range found: {min_totalizer} to {max_totalizer}")

# ------------------------------------------------
# DETERMINE HEIGHTS
# ------------------------------------------------
# This logic ensures the water scales inside the tank
tank_height = tank.dimensions.z
# This is the water mesh's original, unscaled height in the scene
water_original_height = water.dimensions.z 

if max_fill_height is None:
    max_fill_height = tank_height

print(f"   Tank Z-dimension: {tank_height:.2f}. Max fill set to: {max_fill_height:.2f}")

# ------------------------------------------------
# SET TIMELINE RANGE
# ------------------------------------------------
bpy.context.scene.frame_start = start_frame
bpy.context.scene.frame_end = frames[-1]  # Set end frame to the last calculated frame
print(f"   Blender timeline set: {start_frame} to {frames[-1]}")

# ------------------------------------------------
# ANIMATE WATER BASED ON CSV TOTALIZER
# ------------------------------------------------
print("Applying keyframes...")

for frame, progress in zip(frames, normalized_totalizer):
    
    # Compute water height proportional to totalizer value
    # 'progress' is the 0.0-1.0 value from normalized_totalizer
    
    # This is the target Z scale for the water
    # (e.g., if progress=0.5, scale is 50% of (max_fill / original_height))
    current_scale_z = progress * (max_fill_height / water_original_height)
    
    # Handle case of 0 height (scale must be a tiny positive number, not 0)
    if current_scale_z <= 0:
        current_scale_z = 0.0001
        
    # This is the target Z location for the water's origin
    # Assumes tank/water origins are at their geometric center
    current_loc_z = tank.location.z - (tank_height / 2.0) + (progress * max_fill_height / 2.0)

    # Apply scale and position
    water.scale.z = current_scale_z
    water.location.z = current_loc_z

    # Insert keyframes (fast, no frame_set needed)
    water.keyframe_insert(data_path="scale", index=2, frame=frame)
    water.keyframe_insert(data_path="location", index=2, frame=frame)

print("---")
print("✅ Water fill animation complete! Driven by CSV Totalizer data.")
print(f"⏱  Total frames: {frames[-1]}, Records processed: {len(frames)}")