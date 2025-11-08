import bpy
import csv
from datetime import datetime

# ------------------------------------------------
# CONFIGURATION
# ------------------------------------------------
csv_file_path = r"C:\Users\Valmik Belgaonkar\OneDrive\Desktop\Smart-Energy-and-Water-Management-Systems-PE\Smart_Water_Management_System\campus_digital_twin\data\Water_History_A2MFF_2025-05-16_07-00.csv"  # Change this

water_name = "Cylinder"               # Name of the water cylinder object
datetime_format = "%d-%m-%Y %H:%M"  # Format of your timestamp in CSV
start_frame = 1
REAL_MINUTES_PER_SIM_SECOND = 30.0  # 30 real-world minutes = 1 sim second

# Optional: define a maximum visible fill height (Blender units)
# If None, it will use the current cylinder height as the max
max_visible_height = None

# ------------------------------------------------
# OBJECT REFERENCE
# ------------------------------------------------
water = bpy.data.objects.get(water_name)

if not water:
    raise ValueError(f"Could not find object '{water_name}' in the scene.")

# Clear any previous animation data
water.animation_data_clear()
print(f"✅ Found '{water_name}'. Old animations cleared.")

# ------------------------------------------------
# LOAD CSV DATA
# ------------------------------------------------
times = []
values = []

print(f"Loading CSV data from: {csv_file_path}")
with open(csv_file_path, newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    try:
        all_rows = list(reader)
    except Exception as e:
        raise ValueError(f"Error reading CSV. Check file path and encoding. Error: {e}")

    # Ensure chronological order (earliest first)
    for row in reversed(all_rows):
        try:
            times.append(datetime.strptime(row["DateTime"], datetime_format))
            values.append(float(row["Consumption"]))
        except Exception as e:
            print(f"⚠️ Skipping row: {e}")

if not times or not values:
    raise ValueError("❌ No valid data found in CSV. Check 'DateTime' and 'Consumption' columns.")

print(f"✅ Loaded {len(values)} records from {times[0]} to {times[-1]}.")

# ------------------------------------------------
# TIME → FRAMES CONVERSION
# ------------------------------------------------
fps = bpy.context.scene.render.fps
frames = []

for t in times:
    real_seconds_passed = (t - times[0]).total_seconds()
    real_minutes_passed = real_seconds_passed / 60.0
    sim_seconds_passed = real_minutes_passed / REAL_MINUTES_PER_SIM_SECOND
    frame = start_frame + int(round(sim_seconds_passed * fps))
    frames.append(frame)

bpy.context.scene.frame_start = start_frame
bpy.context.scene.frame_end = frames[-1]
print(f"🕐 Timeline set: {start_frame} to {frames[-1]} frames.")

# ------------------------------------------------
# SCALING / NORMALIZATION
# ------------------------------------------------
min_val, max_val = min(values), max(values)
val_range = max_val - min_val if max_val != min_val else 1.0
normalized_values = [(v - min_val) / val_range for v in values]

print(f"📊 Data range: {min_val:.2f} → {max_val:.2f}")

# ------------------------------------------------
# WATER HEIGHT SETTINGS
# ------------------------------------------------
# Compute mesh height in object space (unscaled)
original_height = (water.dimensions.z / water.scale.z)

# If no max height provided, use the current mesh height as limit
if max_visible_height is None:
    max_visible_height = original_height

print(f"💧 Original water height: {original_height:.2f}")
print(f"💧 Max visible height set to: {max_visible_height:.2f}")

# We’ll fix the bottom of the water at its current base (no downward movement)
bottom_z = water.location.z - (original_height * water.scale.z / 2.0)

# ------------------------------------------------
# APPLY ANIMATION
# ------------------------------------------------
print("🎬 Applying keyframes...")

for frame, progress in zip(frames, normalized_values):
    # Compute new Z scale
    scale_z = progress * (max_visible_height / original_height)
    if scale_z <= 0:
        scale_z = 0.0001  # Avoid collapse to 0

    # Compute new location (so bottom stays fixed)
    new_height = original_height * scale_z
    new_loc_z = bottom_z + new_height / 2.0

    # Apply transformations
    water.scale.z = scale_z
    water.location.z = new_loc_z

    # Insert keyframes
    water.keyframe_insert(data_path="scale", index=2, frame=frame)
    water.keyframe_insert(data_path="location", index=2, frame=frame)

print("---")
print("✅ Water height animation complete!")
print(f"   Frames: {len(frames)} | Range: {frames[0]}–{frames[-1]}")