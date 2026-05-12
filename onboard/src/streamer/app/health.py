import time
import psutil


def get_health(streamer, start_time: float):
    """Return basic health information. Camera details removed as optional.

    Fields:
      - uptime_seconds
      - streaming (bool)
      - cpu_percent
      - memory (dict)
    """
    uptime = time.time() - start_time
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.1)

    return {
        "uptime_seconds": int(uptime),
        "streaming": bool(streamer.is_running()) if streamer is not None else False,
        "cpu_percent": cpu,
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
        },
    }
