import argparse
import io
import time
import logging
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse

from fastmcp import FastMCP
import base64

from .config import load_config
from .streamer import Streamer
from .schemas import StreamControlRequest
from .health import get_health

import asyncio


def create_app(cfg):
    app = FastAPI()

    streamer = Streamer()
    start_time = time.time()

    app.state.streamer = streamer
    app.state.current_stream_address = None
    app.state.current_stream_port = None
    app.state.cfg = cfg

    mcp = FastMCP("CameraManager")
    app.mount("/mcp", mcp.http_app(transport="sse"))

    @mcp.tool()
    async def camera_snapshot() -> str:
        """Takes a real-time photo from the camera and returns it as a base64 string."""
        frame = await asyncio.to_thread(streamer.snapshot, cfg, 2.0)
        if frame is None:
            return "Error: Camera not available"
        
        jpeg_bytes = await asyncio.to_thread(streamer.frame_to_jpeg_bytes, frame, 85)
        # AI Agents often prefer base64 for direct image insertion
        b64_data = base64.b64encode(jpeg_bytes).decode("utf-8")
        return f"data:image/jpeg;base64,{b64_data}"

    @app.on_event("startup")
    async def startup():
        # nothing to start by default; streamer starts on demand
        return

    @app.on_event("shutdown")
    async def shutdown():
        streamer.stop()

    @app.post("/start_stream")
    async def start_stream(req: StreamControlRequest):
        try:
            address = req.address or cfg.stream.default_address
            port = req.port or cfg.stream.default_port
            # If streamer already running with different params, stop it first
            if streamer.is_running():
                cur_addr = app.state.current_stream_address
                cur_port = app.state.current_stream_port
                if cur_addr != address or cur_port != port:
                    # stop existing streamer before starting with new params
                    streamer.stop()
            # If already running with same params, return current state
            if streamer.is_running():
                return {"streaming": True, "address": app.state.current_stream_address, "port": app.state.current_stream_port}

            # start streamer with requested params
            streamer.start(address, port, cfg)
            app.state.current_stream_address = address
            app.state.current_stream_port = port
            return {"streaming": True, "address": address, "port": port}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/stop_stream")
    async def stop_stream():
        streamer.stop()
        app.state.current_stream_address = None
        app.state.current_stream_port = None
        return {"streaming": False}

    @app.get("/snapshot")
    async def snapshot():
        # ask streamer for a single frame; streamer will use appsink when streaming or
        # create a short-lived pipeline when not streaming
        # Run blocking snapshot in a thread so it doesn't block the event loop.
        timeout = cfg.snapshot.timeout_seconds
        frame = await asyncio.to_thread(streamer.snapshot, cfg, timeout)
        if frame is None:
            raise HTTPException(status_code=503, detail="No frame available")

        # encode to JPEG using GStreamer to avoid OpenCV dependency
        jpeg_bytes = await asyncio.to_thread(streamer.frame_to_jpeg_bytes, frame, cfg.snapshot.quality, 2.0)
        if not jpeg_bytes:
            raise HTTPException(status_code=500, detail="Failed to encode image")

        return Response(content=jpeg_bytes, media_type="image/jpeg")

    @app.get("/health")
    async def health():
        return get_health(streamer, start_time)

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--debug", action="store_true", help="enable debug logging")
    args = parser.parse_args()

    # Find default config file in current folder if --config not provided.
    import os
    config_path = args.config
    if not config_path:
        for candidate in ("camera.toml", "config.toml", "config.example.toml"):
            if os.path.exists(candidate):
                config_path = candidate
                break
        if not config_path:
            config_path = "config.example.toml"

    # configure logging early so modules can log diagnostic info
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    logger = logging.getLogger(__name__)

    logger.info('Using config file: %s', config_path)

    cfg = load_config(config_path)
    # pre-flight environment check for GStreamer components
    try:
        from .streamer import check_environment
        env = check_environment()
    except Exception as e:
        logger.error('Environment check failed (could not import GStreamer): %s', e)
        raise

    missing = [k for k, v in env['elements'].items() if not v]
    if missing:
        logger.error('Missing required GStreamer elements: %s', missing)
        logger.error('GStreamer environment report: %s', env)
        raise SystemExit(2)

    if not env.get('hw_encoder'):
        logger.warning('No hardware H.264 encoder detected; software encoding will be used.')

    app = create_app(cfg)

    import uvicorn

    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port)


if __name__ == "__main__":
    main()
