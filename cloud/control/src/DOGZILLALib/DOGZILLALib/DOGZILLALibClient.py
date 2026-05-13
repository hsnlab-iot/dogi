"""Client proxy for DOGZILLA that calls a remote HTTP API instead of serial.

This implements a `DOGZILLA` class with the same public methods as the original
serial implementation, but each call is proxied to the HTTP API endpoints
exposed by `DOGZILLALibAPI.py` (e.g. POST /dogzilla/<method>). Methods that
return binary data are returned as bytes (the API returns base64-encoded).

Initialization:
  DOGZILLA(api_base=None, port=..., baud=..., verbose=False)
API base URL is taken from the `DOGZILLA_API_BASE` environment variable if set,
otherwise from the `api_base` parameter. If neither provided, raises ValueError.

This class is intended as a compatible replacement for code that uses the
original `DOGZILLA` class, only the initialization may change.
"""
import inspect
from typing import Any
import os
import requests
import base64
import logging

from DOGZILLALib import DOGZILLALib as OriginalLib

LOG = logging.getLogger('DOGZILLALibClient')
logging.basicConfig(level=logging.INFO)


class DOGZILLA:
    def __init__(self, port: str = '/dev/ttyAMA0', baud: int = 115200, verbose: bool = False, api_base: str = None):
        # api_base override by environment variable
        env = os.environ.get('DOGZILLA_API_BASE')
        if env:
            self.api_base = env.rstrip('/')
        else:
            self.api_base = (api_base or os.environ.get('DOGZILLA_API_BASE') or '').rstrip('/')

        if not self.api_base:
            raise ValueError('API base URL must be provided via api_base argument or DOGZILLA_API_BASE env var')

        # keep compatibility with original constructor signature
        self.port = port
        self.baud = int(baud)
        self.verbose = bool(verbose)

        self._remote_methods = [
            name for name, func in inspect.getmembers(OriginalLib.DOGZILLA, predicate=inspect.isfunction)            if not name.startswith('_')
        ]        

    def _post(self, method: str, args: list = None, kwargs: dict = None, timeout: float = 10.0) -> Any:
        url = f"{self.api_base}/dogzilla/{method}"
        payload = {
            'args': args or [],
            'kwargs': kwargs or {},
            'timeout': timeout,
        }
        try:
            resp = requests.post(url, json=payload, timeout=timeout + 5)
        except Exception as e:
            LOG.exception('HTTP request failed for %s', method)
            raise

        if resp.status_code != 200:
            raise RuntimeError(f'API error {resp.status_code}: {resp.text}')

        data = resp.json()
        if not isinstance(data, dict):
            return data
        if not data.get('success'):
            err = data.get('error') or 'unknown error'
            raise RuntimeError(f'Command error: {err}')

        result = data.get('result')
        is_b64 = bool(data.get('is_base64'))
        if is_b64 and isinstance(result, str):
            try:
                return base64.b64decode(result)
            except Exception:
                # return raw string if decode fails
                return result
        return result

    def __dir__(self):
        # Combine standard attributes with the discovered remote methods
        return sorted(super().__dir__() + self._remote_methods)

    def __getattr__(self, name: str):
        # proxy public methods to remote API
        if name.startswith('_') or name not in self._remote_methods:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        def _method(*args, **kwargs):
            # original methods are synchronous; call remote API synchronously
            return self._post(name, list(args), kwargs)

        return _method


def _test():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', help='API base URL (overrides DOGZILLA_API_BASE)')
    parser.add_argument('--method', help='Method to call')
    parser.add_argument('--args', help='Comma-separated args', default='')
    args = parser.parse_args()
    api = args.api or os.environ.get('DOGZILLA_API_BASE')
    if not api:
        print('Set DOGZILLA_API_BASE or pass --api')
        return
    dog = DOGZILLA(api_base=api)
    if args.method:
        parts = [p for p in args.args.split(',') if p]
        print(dog._post(args.method, parts))


if __name__ == '__main__':
    _test()
