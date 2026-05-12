# Test scripts

Small helper scripts to test the HTTP API and the UDP H.264 stream.

Scripts:

- `start_stream.sh [HOST] [PORT] [API_URL]` — request the service to start streaming to HOST:PORT using the API at API_URL (defaults: 127.0.0.1 5000 http://127.0.0.1:8000).
- `stop_stream.sh [API_URL]` — stop streaming.
- `snapshot.sh [API_URL] [OUT_FILE]` — fetch `/snapshot` and save to OUT_FILE (defaults: snapshot.jpg).
- `health.sh [API_URL]` — fetch `/health`.
- `receive_stream_gst.sh [PORT]` — use `gst-launch-1.0` to receive and display the UDP H.264 stream.

Notes:

- These scripts use `curl` and `jq` for nicer output; if `jq` is not installed the JSON will still be printed.
- Run the scripts from the project root, e.g. `./tests/snapshot.sh`.
