import pyrealsense2 as rs

rs_pipeline = rs.pipeline()
ctx = rs.context()
devices = ctx.query_devices()

# Print settings for each device
for device in devices:
    print(f"Device Name: {device.get_info(rs.camera_info.name)}")
    for sensor in device.query_sensors():
        sensor_name = sensor.get_info(rs.camera_info.name)
        print(f"  Sensor Name: {sensor_name}")
