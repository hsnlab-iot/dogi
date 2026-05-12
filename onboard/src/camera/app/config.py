import dataclasses
import tomli
from typing import Optional


@dataclasses.dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    mcp_prefix: str = "/mcp"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 9000


@dataclasses.dataclass
class CameraConfig:
    device: str = "/dev/video0"
    width: int = 640
    height: int = 480
    fps: int = 30
    format: Optional[str] = None


@dataclasses.dataclass
class StreamConfig:
    default_address: str = "127.0.0.1"
    default_port: int = 5000
    codec: str = "h264_v4l2m2m"
    bitrate: str = "1M"
    use_hardware: bool = True
    mtu: int = 1400
    payload_type: int = 96
    qstream_max_buffers: int = 2
    qsnap_max_buffers: int = 1
    q_leaky: int = 2


@dataclasses.dataclass
class SnapshotConfig:
    format: str = "jpeg"
    quality: int = 80
    timeout_seconds: float = 3.0
    width: Optional[int] = None
    height: Optional[int] = None


@dataclasses.dataclass
class Config:
    server: ServerConfig = dataclasses.field(default_factory=ServerConfig)
    camera: CameraConfig = dataclasses.field(default_factory=CameraConfig)
    stream: StreamConfig = dataclasses.field(default_factory=StreamConfig)
    snapshot: SnapshotConfig = dataclasses.field(default_factory=SnapshotConfig)


def load_config(path: str) -> Config:
    with open(path, "rb") as f:
        data = tomli.load(f)

    cfg = Config()

    if "server" in data:
        s = data["server"]
        cfg.server = ServerConfig(
            host=s.get("host", cfg.server.host),
            port=s.get("port", cfg.server.port),
            mcp_prefix=s.get("mcp_prefix", cfg.server.mcp_prefix),
        )

    if "camera" in data:
        c = data["camera"]
        cfg.camera = CameraConfig(
            device=c.get("device", cfg.camera.device),
            width=c.get("width", cfg.camera.width),
            height=c.get("height", cfg.camera.height),
            fps=c.get("fps", cfg.camera.fps),
            format=c.get("format", cfg.camera.format),
        )

    if "stream" in data:
        s = data["stream"]
        cfg.stream = StreamConfig(
            default_address=s.get("default_address", cfg.stream.default_address),
            default_port=s.get("default_port", cfg.stream.default_port),
            codec=s.get("codec", cfg.stream.codec),
            bitrate=s.get("bitrate", cfg.stream.bitrate),
            use_hardware=s.get("use_hardware", cfg.stream.use_hardware),
            mtu=s.get("mtu", cfg.stream.mtu),
            payload_type=s.get("payload_type", cfg.stream.payload_type),
            qstream_max_buffers=s.get("qstream_max_buffers", cfg.stream.qstream_max_buffers),
            qsnap_max_buffers=s.get("qsnap_max_buffers", cfg.stream.qsnap_max_buffers),
            q_leaky=s.get("q_leaky", cfg.stream.q_leaky),
        )

    if "snapshot" in data:
        s = data["snapshot"]
        cfg.snapshot = SnapshotConfig(
            format=s.get("format", cfg.snapshot.format),
            quality=s.get("quality", cfg.snapshot.quality),
            timeout_seconds=s.get("timeout_seconds", cfg.snapshot.timeout_seconds),
            width=s.get("width", cfg.snapshot.width),
            height=s.get("height", cfg.snapshot.height),
        )

    return cfg
