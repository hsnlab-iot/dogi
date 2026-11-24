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


## Deploy & Run on the V100 Lab PC

### 1. Unpack the Transfer Bundle

Set `DOGI_DIR` to your `dogi` repo path (e.g. `~/dogi`), extract the `.tar.gz`, verify checksums, and place the adapter and wheel into `cloud/control/cache/lightnav/`:

```bash
DOGI_DIR="/path/to/dogi"
BUNDLE_TAR="$(ls -t ~/dogi_vla_bundle_*.tar.gz | head -n 1)"
BUNDLE_NAME="$(basename "${BUNDLE_TAR}" .tar.gz)"

# Extract and verify checksums
tar -xzf "${BUNDLE_TAR}" -C /tmp
(cd "/tmp/${BUNDLE_NAME}" && sha256sum -c SHA256SUMS)

# Stage adapter and wheel
rm -rf "${DOGI_DIR}/cloud/control/cache/lightnav/adapter"
mkdir -p "${DOGI_DIR}/cloud/control/cache/lightnav/adapter" \
         "${DOGI_DIR}/cloud/control/cache/lightnav/wheels"

cp -R "/tmp/${BUNDLE_NAME}/adapter/." "${DOGI_DIR}/cloud/control/cache/lightnav/adapter/"
rm -f "${DOGI_DIR}/cloud/control/cache/lightnav/wheels/lightnav_mujoco"*.whl
cp "/tmp/${BUNDLE_NAME}/wheels/lightnav_mujoco"*.whl "${DOGI_DIR}/cloud/control/cache/lightnav/wheels/"
```

### 2. Build, Download Base Weights (Once), and Start the VLA Container

```bash
cd "${DOGI_DIR}/cloud/control"

# Build the VLA image (installs peft, accelerate, and the lightnav_mujoco wheel)
docker compose -f docker-compose.yaml -f docker-compose.vla.yaml build control

# Download pinned LightNav-0 base weights (~9.7 GB) if not already present
if [ ! -f cache/lightnav/LightNav-0/config.json ]; then
  bash scripts/vla-download.sh
fi

# Start the control container with the VLA override
docker compose -f docker-compose.yaml -f docker-compose.vla.yaml up -d --no-deps control
```

### 3. Verify V100 FP16 Load (Optional)

```bash
cd "${DOGI_DIR}/cloud/control"

docker compose -f docker-compose.yaml -f docker-compose.vla.yaml exec control \
  /opt/vla/bin/python -c '
import torch
from lightnav_mujoco.model.lightnav_adapter import DirectActionLightNav

print("Torch / CUDA:", torch.__version__, torch.version.cuda)
print("GPU / Arch  :", torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
assert torch.__version__ == "2.11.0+cu126"
assert "sm_70" in torch.cuda.get_arch_list()

model = DirectActionLightNav.from_adapter(
    "/models/adapter",
    model_path="/models/LightNav-0",
    device="cuda",
    dtype="float16",
)
model.half().eval()
print(f"Loaded cleanly in {model.dtype}; VRAM: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
'
```

### 4. Run on Dogi

1. Start the robot's camera stream.
2. Open the Dogi web UI and select **VLA**.
3. Wait for **Ready** and **Camera receiving**.
4. Enter an instruction and click **Prompt** (keep the physical stop available).
