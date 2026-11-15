#!/usr/bin/env bash
set -euo pipefail
CONTROL_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$CONTROL_DIR/cache/lightnav"
docker run --rm \
    --entrypoint /opt/vla/bin/hf \
    -e HF_HUB_OFFLINE=0 -e TRANSFORMERS_OFFLINE=0 \
    --mount "type=bind,src=$CONTROL_DIR/cache/lightnav,dst=/models" \
    dogi-control-lightnav:latest download LightOriginsHQ/LightNav-0 \
    --revision 826dc5fbfa37afa8293d2e336d329b6ffc0bfb64 \
    --local-dir /models/LightNav-0
