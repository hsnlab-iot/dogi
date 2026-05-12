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
    port = ports.get('video')
    if not port:
        raise RuntimeError('ports.video not found in config')
    return int(port)


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

    url = urljoin(base_url + '/', 'start_streamer')
    payload = {'ip': ip, 'port': int(port)}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except Exception as exc:
        # Log a concise single-line error (no traceback)
        LOG.error('Start streamer request failed: %s', str(exc))
        return False

    if resp.status_code == 200:
        LOG.info('Started streamer at %s:%s via %s', ip, port, url)
        return True
    else:
        # concise failure message
        text = resp.text[:200].replace('\n', ' ')
        LOG.warning('Failed to start streamer: %s %s', resp.status_code, text)
        return False


def check_health(base_url, timeout=3):
    """Check streamer health. Returns True if healthy, False otherwise.

    Tries several common endpoints: /health, /status, then root.
    Health considered OK for HTTP 200 and if response contains 'ok' or status=ok.
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
            status = j.get('status') or j.get('state') or j.get('ok')
            if status is None:
                return True, None
            if isinstance(status, bool):
                return bool(status), None
            if isinstance(status, str) and status.lower() in ('ok', 'running', 'healthy'):
                return True, None
            last_error = f'status={status}'
            continue
        except Exception:
            # Not JSON: check body text
            txt = (resp.text or '').lower()
            if 'ok' in txt or 'running' in txt or 'healthy' in txt:
                return True, None
            # treat plain 200 as healthy
            return True, None

    return False, last_error


class StreamerMonitor(threading.Thread):
    def __init__(self, base_url, video_port, check_interval=10):
        super().__init__(daemon=True)
        self.base_url = base_url.rstrip('/')
        self.video_port = int(video_port)
        self.check_interval = check_interval
        self._stop = threading.Event()
        # health tracking
        self.is_healthy = None
        self.last_change = time.time()
        self.total_uptime = 0.0
        self.total_downtime = 0.0
        self.current_down_start = None
        self.recent_down_events = deque(maxlen=10)

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

        # Ensure streamer is started initially (best-effort)
        start_streamer(self.base_url, ip=local_ip, port=self.video_port)

        while not self._stop.is_set():
            healthy, err = check_health(self.base_url)

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
                # attempt restart (best-effort)
                started = start_streamer(self.base_url, ip=local_ip, port=self.video_port)
                if started:
                    LOG.info('Restart request sent')

            time.sleep(self.check_interval)


def start_monitor(check_interval=10):
    base_url = _load_streamer_url()
    port = _get_video_port()
    monitor = StreamerMonitor(base_url, port, check_interval=check_interval)
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
