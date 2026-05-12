"""Streamer client: start streamer and monitor health.

Usage: run as script or import and call `start_monitor()`.
"""
import os
import time
import threading
import logging
import socket
from collections import deque
import requests
from urllib.parse import urlparse, urljoin

import config

LOG = logging.getLogger('streamer_client')
logging.basicConfig(level=logging.INFO)


def _load_streamer_url():
    cfg = config.get_config_data()
    url = cfg.get('streamer', {}).get('url')
    if not url:
        raise RuntimeError('streamer.url not found in config')

    # Replace placeholder tokens like ROBOT_IP or robot_ip with env var if present
    if 'ROBOT_IP' in url or 'robot_ip' in url:
        env_val = os.environ.get('ROBOT_IP') or os.environ.get('robot_ip')
        if env_val:
            url = url.replace('ROBOT_IP', env_val).replace('robot_ip', env_val)
            LOG.info('Replaced robot IP placeholder with %s', env_val)
        else:
            LOG.info('Found robot IP placeholder but no env var ROBOT_IP set; leaving as-is')

    return url.rstrip('/')


def _get_video_port():
    cfg = config.get_config_data()
    ports = cfg.get('ports', {})
    # Prefer stream_port under [streamer], fall back to [ports].video
    streamer_cfg = cfg.get('streamer', {})
    port = streamer_cfg.get('stream_port') or ports.get('video')
    if not port:
        raise RuntimeError('streamer.stream_port or ports.video not found in config')
    return int(port)


def _get_stream_ip():
    cfg = config.get_config_data()
    streamer_cfg = cfg.get('streamer', {})
    ip = streamer_cfg.get('stream_ip')
    if ip:
        return str(ip)
    return None


def _resolve_host_ip(host):
    try:
        return socket.gethostbyname(host)
    except Exception:
        return None


def _choose_local_ip(remote_ip, remote_port=80):
    """Return the local IP address used to reach remote_ip.

    Uses a UDP socket connect trick which does not send packets.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((remote_ip, remote_port if remote_port else 80))
            local_ip = s.getsockname()[0]
            return local_ip
    except Exception:
        # Fallback: try hostname addresses
        try:
            candidates = socket.gethostbyname_ex(socket.gethostname())[2]
            for ip in candidates:
                if not ip.startswith('127.'):
                    return ip
        except Exception:
            pass
    # Last resort
    return '127.0.0.1'


def start_streamer(base_url, ip=None, port=None, timeout=5):
    """POST to {base_url}/start_streamer with payload {'ip': ip, 'port': port}.

    Returns True on success (HTTP 200), False otherwise.
    """
    if ip is None:
        raise ValueError('ip is required')
    if port is None:
        raise ValueError('port is required')

    # endpoint per spec
    url = urljoin(base_url + '/', 'start_stream')
    # The onboard service expects a JSON with keys matching StreamControlRequest: {"address":..., "port":...}
    payload = {'address': ip, 'port': int(port)}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except Exception as exc:
        # Log a concise single-line error (no traceback)
        LOG.error('Start streamer request failed: %s', str(exc))
        return False

    if resp.status_code == 200:
        # Try to parse any acknowledgement from the remote service about actual address/port
        actual_addr = None
        actual_port = None
        try:
            j = resp.json()
            # onboard returns {"streaming": True, "address": address, "port": port}
            actual_addr = j.get('address') or j.get('addr') or None
            actual_port = j.get('port') or None
        except Exception:
            j = None

        if actual_addr or actual_port:
            LOG.info('Requested streamer start at %s:%s via %s; remote acknowledged %s:%s',
                     ip, port, url, actual_addr or ip, actual_port or port)
        else:
            LOG.info('Started streamer at %s:%s via %s', ip, port, url)

        return True
    else:
        # concise failure message
        text = resp.text[:200].replace('\n', ' ')
        LOG.warning('Failed to start streamer: %s %s', resp.status_code, text)
        return False


def check_health(base_url, timeout=3):
    """Check streamer health.

    Returns tuple: (healthy: bool, last_error: str|None, details: dict|None)
    `details` contains parsed JSON when available (e.g. {'uptime_seconds':..., 'streaming': False}).
    """
    candidates = ['health', 'status', '']
    last_error = None
    for path in candidates:
        url = urljoin(base_url + '/', path)
        try:
            resp = requests.get(url, timeout=timeout)
        except Exception as exc:
            last_error = str(exc)
            continue
        if resp.status_code != 200:
            last_error = f'HTTP {resp.status_code}'
            continue
        # Try JSON
        try:
            j = resp.json()
            # If JSON present, consider service reachable. return JSON as details.
            return True, None, j
        except Exception:
            # Not JSON: check body text
            txt = (resp.text or '').lower()
            if 'ok' in txt or 'running' in txt or 'healthy' in txt:
                return True, None, None
            # treat plain 200 as healthy
            return True, None, None

    return False, last_error, None


class StreamerMonitor(threading.Thread):
    def __init__(self, base_url, video_port, check_interval=10, status_log_interval=60, stream_ip=None):
        super().__init__(daemon=True)
        self.base_url = base_url.rstrip('/')
        self.video_port = int(video_port)
        self.check_interval = check_interval
        self.status_log_interval = int(status_log_interval)
        self._stop = threading.Event()
        # health tracking
        self.is_healthy = None
        self.last_change = time.time()
        self.total_uptime = 0.0
        self.total_downtime = 0.0
        self.current_down_start = None
        self.recent_down_events = deque(maxlen=10)
        self.last_status_log = 0
        self.configured_stream_ip = stream_ip

    def stop(self):
        self._stop.set()

    def run(self):
        LOG.info('Streamer monitor started for %s', self.base_url)
        # Resolve remote IP
        parsed = urlparse(self.base_url)
        host = parsed.hostname or parsed.path
        remote_ip = _resolve_host_ip(host) or host
        remote_port = parsed.port or 80
        local_ip = _choose_local_ip(remote_ip, remote_port)

        # If stream_ip configured, prefer it; otherwise use detected local_ip
        chosen_ip = self.configured_stream_ip or local_ip

        # Ensure streamer is started initially (best-effort)
        start_streamer(self.base_url, ip=chosen_ip, port=self.video_port)

        while not self._stop.is_set():
            healthy, err, details = check_health(self.base_url)

            now = time.time()
            # initialize state
            if self.is_healthy is None:
                self.is_healthy = healthy
                self.last_change = now
                if not healthy:
                    self.current_down_start = now

            if healthy != self.is_healthy:
                # transition
                if healthy:
                    # recovered: update downtime
                    if self.current_down_start:
                        down_dur = now - self.current_down_start
                        self.total_downtime += down_dur
                        self.recent_down_events.append({'start': self.current_down_start, 'duration': down_dur})
                        LOG.info('Streamer recovered: downtime=%ds', int(down_dur))
                        self.current_down_start = None
                else:
                    # went down: update uptime
                    up_dur = now - self.last_change
                    self.total_uptime += up_dur
                    self.current_down_start = now
                    LOG.warning('Streamer became unavailable: reason=%s', err or 'unknown')

                self.is_healthy = healthy
                self.last_change = now

            # If currently unhealthy, try restart and report concise status
            if not self.is_healthy:
                LOG.warning('Streamer unavailable (uptime=%ds downtime=%ds recent_down=%s)',
                            int(self.total_uptime),
                            int(self.total_downtime + (now - (self.current_down_start or now))),
                            list(self.recent_down_events))
                # attempt restart (best-effort) using chosen_ip
                started = start_streamer(self.base_url, ip=chosen_ip, port=self.video_port)
                if started:
                    LOG.info('Restart request sent')
            else:
                # Periodically show concise healthy status
                if now - self.last_status_log >= self.status_log_interval:
                    # compute current uptime and downtime
                    current_up = now - self.last_change if self.is_healthy else 0
                    uptime = self.total_uptime + current_up
                    downtime = self.total_downtime
                    recent = [int(e['duration']) for e in self.recent_down_events]
                    LOG.info('Streamer healthy (uptime=%ds downtime=%ds recent_downs=%s)',
                             int(uptime), int(downtime), recent)
                    self.last_status_log = now

            # If service reachable but reports streaming disabled, attempt start
            streaming_flag = None
            if details and isinstance(details, dict) and 'streaming' in details:
                try:
                    streaming_flag = bool(details.get('streaming'))
                except Exception:
                    streaming_flag = None

            if healthy and streaming_flag is False:
                LOG.info('Remote health reports streaming=false, attempting to start streamer')
                started = start_streamer(self.base_url, ip=chosen_ip, port=self.video_port)
                if started:
                    LOG.info('Start request sent due to remote not streaming')

            time.sleep(self.check_interval)


def start_monitor(check_interval=10):
    base_url = _load_streamer_url()
    port = _get_video_port()
    stream_ip = _get_stream_ip()
    monitor = StreamerMonitor(base_url, port, check_interval=check_interval, stream_ip=stream_ip)
    monitor.start()
    return monitor


if __name__ == '__main__':
    # Simple CLI: start monitor and keep running
    LOG.info('Launching streamer client...')
    cfg_url = None
    try:
        monitor = start_monitor(check_interval=10)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info('Stopping streamer client...')
        try:
            monitor.stop()
        except Exception:
            pass
