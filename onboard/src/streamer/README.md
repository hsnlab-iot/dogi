# Camera streaming + snapshot service

Lightweight FastAPI service to:
- stream video via UDP (Using GStreamer H.264 encoder and appsink for snapshots)
- return snapshot images on demand (JPEG encoded on request only)
- expose health information

Quick start (create a virtualenv, install deps):

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Run with a config file:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# or: python -m app.main --config config.example.toml
```

Endpoints:
- `POST /start_stream` {address, port} — start UDP H.264 stream
- `POST /stop_stream` — stop streaming
- `GET /snapshot` — returns a JPEG snapshot (encoded on demand)
- `GET /health` — service health JSON
