# Run LightNav on Dogi

Run with the existing Dogi stack and
`control-control:latest` image installed. Start the robot's camera stream.

From the trainer checkout, build the wheel with `uv build --wheel`. Copy the
wheel to `cloud/control/cache/lightnav/wheels/` on the lab PC. Copy the
complete exported SDPA adapter directory to `cloud/control/cache/lightnav/adapter/`
so `direct_action_meta.json` is directly inside that directory.

Build the VLA image and download the model once:

```bash
cd ~/dogi/cloud/control
docker compose -f docker-compose.yaml -f docker-compose.vla.yaml build control &&
  bash scripts/vla-download.sh
```

Start the control container:

```bash
docker compose -f docker-compose.yaml -f docker-compose.vla.yaml up -d --no-deps control
```

Open the web ui, select **VLA**, and wait for **Ready** and
**Camera receiving**. Enter an instruction and press **Prompt**.
VLA sends commands directly to the robot. Keep its physical stop available during testing.

- **Stop** ends the current action. **New** also clears the instruction.
- **Adaptive steering** adjusts arc and turn pulses and the settling delay.
  **Apply** stops the trial; press **Prompt** to run again.
- **Invert navigation yaw** reverses automatic turning if directions are swapped.
- **Manual motion** tests `vx`, `vy`, and yaw for a short pulse. The robot driver
  raises small nonzero yaw commands to magnitude 30.
- **Camera pitch** tilts the view. **Center** returns it to level.
