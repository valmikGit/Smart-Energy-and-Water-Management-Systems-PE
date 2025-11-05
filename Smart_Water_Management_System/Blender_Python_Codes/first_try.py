import bpy

# -----------------------------
# CONFIGURATION
# -----------------------------
tank_name = "Cylinder.001"   # Outer cylinder (tank)
water_name = "Liquid"        # Inner cylinder (water)
start_frame = 1
end_frame = 100              # Total animation duration in frames
max_fill_height = None       # If None, automatically matches tank height

# -----------------------------
# OBJECT REFERENCES
# -----------------------------
tank = bpy.data.objects.get(tank_name)
water = bpy.data.objects.get(water_name)

if not tank or not water:
    raise ValueError(f"Could not find objects '{tank_name}' or '{water_name}' in the scene.")

# -----------------------------
# DETERMINE HEIGHTS
# -----------------------------
tank_height = tank.dimensions.z  # height of the outer cylinder
water_height = water.dimensions.z

# If not specified, fill to tank height
if max_fill_height is None:
    max_fill_height = tank_height

# -----------------------------
# SET TIMELINE RANGE
# -----------------------------
bpy.context.scene.frame_start = start_frame
bpy.context.scene.frame_end = end_frame

# -----------------------------
# RESET INITIAL WATER SCALE AND POSITION
# -----------------------------
# Start completely empty (flat at bottom)
water.scale.z = 0.0
water.location.z = tank.location.z - tank_height / 2.0  # base aligned with tank bottom
water.keyframe_insert(data_path="scale", index=2, frame=start_frame)
water.keyframe_insert(data_path="location", index=2, frame=start_frame)

# -----------------------------
# ANIMATE WATER FILL
# -----------------------------
frames = end_frame - start_frame
target_scale_z = max_fill_height / water_height  # how much to scale Z
target_loc_z = tank.location.z - tank_height / 2.0 + max_fill_height / 2.0  # top aligns with tank top

for f in range(start_frame, end_frame + 1):
    bpy.context.scene.frame_set(f)
    progress = (f - start_frame) / frames

    # Linear interpolation for scale and position
    current_scale_z = progress * target_scale_z
    current_loc_z = (tank.location.z - tank_height / 2.0) + (progress * max_fill_height / 2.0)

    # Clamp to final target
    if current_scale_z > target_scale_z:
        current_scale_z = target_scale_z
    if current_loc_z > target_loc_z:
        current_loc_z = target_loc_z

    water.scale.z = current_scale_z
    water.location.z = current_loc_z

    water.keyframe_insert(data_path="scale", index=2)
    water.keyframe_insert(data_path="location", index=2)

print("Water fill animation complete! The inner cylinder now rises from the base to the top of the tank.")