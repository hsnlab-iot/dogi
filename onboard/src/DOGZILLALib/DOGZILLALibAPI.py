"""FastAPI wrapper around DOGZILLA serial library.

Exposes a queued, non-blocking API that delegates serial operations to a single
worker running in a threadpool executor. Provides a generic `/call` endpoint
and convenience endpoints. Includes a `/health` endpoint.
"""
import asyncio
import time
from typing import Any, Dict, List, Optional
import logging
import base64

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from concurrent.futures import ThreadPoolExecutor

from .DOGZILLALib import DOGZILLA

LOG = logging.getLogger("DOGZILLALibAPI")
logging.basicConfig(level=logging.INFO)


class CallRequest(BaseModel):
    method: str
    args: Optional[List[Any]] = None
    kwargs: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = 10.0


class CallResponse(BaseModel):
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    is_base64: Optional[bool] = False


class SerialManager:
    def __init__(self, port: str = "/dev/ttyAMA0", baud: int = 115200, verbose: bool = False):
        self.port = port
        self.baud = baud
        self.verbose = verbose
        self._dog = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._loop = asyncio.get_event_loop()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self.started_at = time.time()
        self.last_tx_time: Optional[float] = None
        self.last_tx_command: Optional[str] = None
        self.last_response: Optional[Any] = None
        self.last_response_is_base64: bool = False
        self.last_response_b64: Optional[str] = None
        self._running = False

    async def start(self):
        LOG.info('Starting SerialManager for port=%s baud=%s', self.port, self.baud)
        # instantiate DOGZILLA in executor to avoid blocking event loop
        def _make():
            return DOGZILLA(self.port, self.baud, self.verbose)

        self._dog = await self._loop.run_in_executor(self._executor, _make)
        self._running = True
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        LOG.info('Stopping SerialManager')
        self._running = False
        if self._worker_task:
            await self._worker_task
        # close serial by calling stop and deleting instance in executor
        if self._dog:
            def _stopdog():
                try:
                    self._dog.stop()
                except Exception:
                    pass
            await self._loop.run_in_executor(self._executor, _stopdog)
            self._dog = None
        self._executor.shutdown(wait=False)

    async def _worker(self):
        while self._running:
            try:
                item = await self._queue.get()
            except asyncio.CancelledError:
                break
            method, args, kwargs, fut = item
            # execute in executor
            try:
                def _call():
                    fn = getattr(self._dog, method)
                    return fn(*args, **(kwargs or {}))

                self.last_tx_time = time.time()
                self.last_tx_command = method
                res = await self._loop.run_in_executor(self._executor, _call)
                # If result is binary, encode as base64 for JSON transport
                if isinstance(res, (bytes, bytearray)):
                    b = bytes(res)
                    encoded = base64.b64encode(b).decode('ascii')
                    self.last_response = None
                    self.last_response_is_base64 = True
                    self.last_response_b64 = encoded
                    out_result = encoded
                    is_b64 = True
                else:
                    self.last_response = res
                    self.last_response_is_base64 = False
                    self.last_response_b64 = None
                    out_result = res
                    is_b64 = False

                if not fut.cancelled():
                    fut.set_result({'success': True, 'result': out_result, 'is_base64': is_b64})
            except Exception as exc:
                LOG.exception('Error executing %s', method)
                if not fut.cancelled():
                    fut.set_result({'success': False, 'error': str(exc), 'is_base64': False})

    async def call_method(self, method: str, args: Optional[List[Any]] = None, kwargs: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        if not self._running or self._dog is None:
            raise RuntimeError('Serial manager not started')

        if not hasattr(self._dog, method):
            raise AttributeError(f'Method not found: {method}')

        fut = self._loop.create_future()
        await self._queue.put((method, args or [], kwargs or {}, fut))

        try:
            res = await asyncio.wait_for(fut, timeout=timeout)
            return res
        except asyncio.TimeoutError:
            if not fut.done():
                fut.cancel()
            raise

    def health(self) -> Dict[str, Any]:
        port_ok = False
        try:
            # quick check: if _dog exists assume port open
            port_ok = self._dog is not None
        except Exception:
            port_ok = False

        # Provide base64-safe last_response
        last_response = None
        last_response_is_base64 = False
        if self.last_response_is_base64:
            last_response = self.last_response_b64
            last_response_is_base64 = True
        else:
            # if last_response is bytes for some reason, encode it
            if isinstance(self.last_response, (bytes, bytearray)):
                last_response = base64.b64encode(bytes(self.last_response)).decode('ascii')
                last_response_is_base64 = True
            else:
                last_response = self.last_response

        return {
            'port': self.port,
            'port_open': bool(port_ok),
            'uptime_seconds': int(time.time() - self.started_at),
            'queue_length': self._queue.qsize() if self._queue else 0,
            'last_tx_time': int(self.last_tx_time) if self.last_tx_time else None,
            'last_tx_command': self.last_tx_command,
            'last_response': last_response,
            'last_response_is_base64': last_response_is_base64,
        }


app = FastAPI()
_manager: Optional[SerialManager] = None


# Model for method-specific endpoints (no 'method' field)
class MethodRequest(BaseModel):
    args: Optional[List[Any]] = None
    kwargs: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = 2.0


def _register_dogzilla_endpoints():
    # Inspect DOGZILLA methods and register an endpoint per public method
    for name in dir(DOGZILLA):
        if name.startswith('_'):
            continue
        attr = getattr(DOGZILLA, name)
        if not callable(attr):
            continue

        path = f"/dogzilla/{name}"

        async def _handler(req: MethodRequest, _name=name):
            global _manager
            if not _manager:
                raise HTTPException(status_code=503, detail='Serial manager not initialized')
            try:
                res = await _manager.call_method(_name, req.args or [], req.kwargs or {}, timeout=req.timeout or 10.0)
                return CallResponse(**res)
            except AttributeError as ae:
                raise HTTPException(status_code=404, detail=str(ae))
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail='Command timeout')
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))

        # add route (POST)
        try:
            app.add_api_route(path, _handler, methods=['POST'], response_model=CallResponse)
            LOG.debug('Registered endpoint %s', path)
        except Exception:
            LOG.exception('Failed to register endpoint for %s', name)


# Register endpoints at import time so docs show them
_register_dogzilla_endpoints()


@app.on_event('startup')
async def startup_event():
    global _manager
    if _manager is None:
        # Default port can be overridden by environment or caller; use default here
        _manager = SerialManager(port='/dev/ttyAMA0', baud=115200, verbose=False)
        await _manager.start()
    else:
        # If a manager was provided (via CLI), ensure it is started
        if not _manager._running:
            await _manager.start()


@app.on_event('shutdown')
async def shutdown_event():
    global _manager
    if _manager:
        await _manager.stop()


def _setup_logging(debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    logging.getLogger().setLevel(level)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run DOGZILLA FastAPI server')
    parser.add_argument('--serial-port', type=str, default='/dev/serial0', help='Serial device path')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='HTTP host')
    parser.add_argument('--port', type=int, default=8001, help='HTTP port')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging and verbose serial')
    args = parser.parse_args()

    _setup_logging(args.debug)

    # Pre-create manager so startup_event uses configured port/verbose
    _manager = SerialManager(port=args.serial_port, baud=args.baud, verbose=args.debug)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level='debug' if args.debug else 'info')


@app.post('/call', response_model=CallResponse)
async def call_endpoint(req: CallRequest):
    global _manager
    if not _manager:
        raise HTTPException(status_code=503, detail='Serial manager not initialized')
    try:
        res = await _manager.call_method(req.method, req.args, req.kwargs, timeout=req.timeout or 10.0)
        return CallResponse(**res)
    except AttributeError as ae:
        raise HTTPException(status_code=404, detail=str(ae))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail='Command timeout')
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/health')
async def health():
    global _manager
    if not _manager:
        raise HTTPException(status_code=503, detail='Serial manager not initialized')
    return _manager.health()


@app.post('/set_verbose')
async def set_verbose(v: bool):
    global _manager
    if not _manager:
        raise HTTPException(status_code=503, detail='Serial manager not initialized')
    _manager.verbose = bool(v)
    return {'verbose': _manager.verbose}
