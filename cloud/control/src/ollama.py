import json
import ollama
import threading
import time
from urllib.parse import urlparse, urlunparse


_registry_lock = threading.RLock()
_workers_by_server = {}
_owner_to_server = {}


def _normalize_model_list(models):
    normalized = set()
    for model in models or []:
        value = str(model or '').strip()
        if value:
            normalized.add(value)
    return sorted(normalized)


def _extract_first_number(payload, keys):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _extract_context_size(model_item):
    if not isinstance(model_item, dict):
        return 0

    details = model_item.get('details') if isinstance(model_item.get('details'), dict) else {}
    options = model_item.get('options') if isinstance(model_item.get('options'), dict) else {}

    candidates = [
        _extract_first_number(model_item, ['context_size', 'context_length', 'ctx_size', 'num_ctx']),
        _extract_first_number(details, ['context_size', 'context_length', 'ctx_size', 'num_ctx']),
        _extract_first_number(options, ['num_ctx', 'context_size', 'context_length', 'ctx_size']),
    ]

    for candidate in candidates:
        if candidate is not None:
            try:
                return int(candidate)
            except Exception:
                continue

    return 0


def _extract_gpu_utilization(model_item):
    size_vram = _extract_first_number(model_item, ['size_vram', 'gpu_memory', 'gpu_bytes'])
    model_size = _extract_first_number(model_item, ['size', 'model_size'])

    if size_vram is not None and model_size and model_size > 0:
        return max(0.0, min(100.0, (size_vram / model_size) * 100.0))

    return 0.0


def _normalize_ps_models(ps_payload):
    models = ps_payload.get('models', []) if isinstance(ps_payload, dict) else []
    if not isinstance(models, list):
        return []

    normalized = []
    for item in models:
        if not isinstance(item, dict):
            continue

        model_name = item.get('model') or 'unknown'
        normalized.append(
            {
                'model': str(model_name),
                'gpu_utilization': round(_extract_gpu_utilization(item), 2),
                'context_length': _extract_context_size(item),
            }
        )

    normalized.sort(key=lambda entry: entry['model'])
    return normalized


def openai_base_to_ollama_host(openai_api_base):
    raw = str(openai_api_base or '').strip()
    if not raw:
        return ''

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        parsed = urlparse(f'http://{raw}')

    if not parsed.netloc:
        return raw.rstrip('/').removesuffix('/v1')

    path = parsed.path or ''
    if path.endswith('/v1/'):
        path = path[:-4]
    elif path.endswith('/v1'):
        path = path[:-3]

    path = path.rstrip('/')
    return urlunparse((parsed.scheme, parsed.netloc, path, '', '', ''))


def _response_to_dict(payload):
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, 'model_dump'):
        try:
            return payload.model_dump()
        except Exception:
            return {}
    if hasattr(payload, 'dict'):
        try:
            return payload.dict()
        except Exception:
            return {}
    return {}


def _load_model(client, model, keep_alive):
    client.generate(
        model=model,
        prompt='',
        stream=False,
        keep_alive=keep_alive,
        options={'num_predict': 0},
    )


def _unload_model(client, model):
    client.generate(
        model=model,
        prompt='',
        stream=False,
        keep_alive=0,
        options={'num_predict': 0},
    )


def _fetch_server_ps(client):
    payload = _response_to_dict(client.ps())
    return _normalize_ps_models(payload), payload


class _OllamaServerWorker:
    def __init__(self, server_url):
        self.server_url = server_url
        self._client = ollama.Client(host=server_url)
        self._owners = {}
        self._loaded_models = set()
        self._revision = 0
        self._condition = threading.Condition()
        self._last_error = ''
        self._last_reconcile_at = 0.0
        self._last_ps_at = 0.0
        self._last_ps_models = []
        self._thread = threading.Thread(
            target=self._run,
            name=f'ollama-worker:{server_url}',
            daemon=True,
        )
        self._thread.start()

    def set_owner_models(self, owner, models, keep_alive):
        desired_models = set(_normalize_model_list(models))
        keep_alive_value = str(keep_alive or '30m').strip() or '30m'

        with self._condition:
            if desired_models:
                self._owners[owner] = {
                    'models': desired_models,
                    'keep_alive': keep_alive_value,
                }
            else:
                self._owners.pop(owner, None)

            self._revision += 1
            self._condition.notify_all()

    def remove_owner(self, owner):
        with self._condition:
            self._owners.pop(owner, None)
            self._revision += 1
            self._condition.notify_all()

    def _current_desired_models(self):
        desired = set()
        for data in self._owners.values():
            desired.update(data.get('models', set()))
        return desired

    def _current_keep_alive(self):
        for owner in sorted(self._owners.keys()):
            keep_alive = str(self._owners[owner].get('keep_alive') or '').strip()
            if keep_alive:
                return keep_alive
        return '30m'

    def _has_newer_revision(self, revision):
        with self._condition:
            return self._revision != revision

    def _set_last_error(self, message):
        self._last_error = str(message or '')

    def _reconcile_models(self, desired_models, keep_alive, revision):
        unload_first = sorted(self._loaded_models - desired_models)
        for model in unload_first:
            if self._has_newer_revision(revision):
                return
            try:
                _unload_model(self._client, model)
                self._loaded_models.discard(model)
                print(f"Ollama unloaded model '{model}' on {self.server_url}")
            except Exception as exc:
                self._set_last_error(f'unload failed for {model}: {exc}')
                print(f"Warning: failed to unload ollama model '{model}' on {self.server_url}: {exc}")

        to_load = sorted(desired_models - self._loaded_models)
        for model in to_load:
            if self._has_newer_revision(revision):
                return
            try:
                _load_model(self._client, model, keep_alive)
                self._loaded_models.add(model)
                print(f"Ollama loaded model '{model}' on {self.server_url} with keep_alive={keep_alive}")
            except Exception as exc:
                self._set_last_error(f'load failed for {model}: {exc}')
                print(f"Warning: failed to load ollama model '{model}' on {self.server_url}: {exc}")

    def _refresh_ps_snapshot(self):
        try:
            ps_models, _raw = _fetch_server_ps(self._client)
            self._last_ps_models = ps_models
            self._last_ps_at = time.time()
        except Exception as exc:
            self._set_last_error(f'ps failed: {exc}')

    def get_status_snapshot(self, include_ps=True):
        with self._condition:
            owners = {
                owner: {
                    'models': sorted(info.get('models', set())),
                    'keep_alive': str(info.get('keep_alive') or ''),
                }
                for owner, info in self._owners.items()
            }
            desired_models = sorted(self._current_desired_models())
            revision = self._revision
            loaded_models = sorted(self._loaded_models)
            last_error = self._last_error
            last_reconcile_at = self._last_reconcile_at
            last_ps_at = self._last_ps_at
            last_ps_models = list(self._last_ps_models)

        if include_ps:
            self._refresh_ps_snapshot()
            last_ps_at = self._last_ps_at
            last_ps_models = list(self._last_ps_models)

        return {
            'server_url': self.server_url,
            'revision': revision,
            'owners': owners,
            'desired_models': desired_models,
            'loaded_models': loaded_models,
            'last_error': last_error,
            'last_reconcile_at': last_reconcile_at,
            'last_ps_at': last_ps_at,
            'ps_models': last_ps_models,
        }

    def _run(self):
        observed_revision = -1

        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._revision != observed_revision)
                observed_revision = self._revision
                desired_models = set(self._current_desired_models())
                keep_alive = self._current_keep_alive()

            self._reconcile_models(desired_models, keep_alive, observed_revision)
            self._last_reconcile_at = time.time()
            self._refresh_ps_snapshot()


def _get_or_create_worker(server_url):
    worker = _workers_by_server.get(server_url)
    if worker is None:
        worker = _OllamaServerWorker(server_url)
        _workers_by_server[server_url] = worker
    return worker


def update_owner_models(openai_api_base, owner, models, keep_alive='30m'):
    owner_name = str(owner or '').strip()
    if not owner_name:
        return

    server_url = openai_base_to_ollama_host(openai_api_base)
    if not server_url:
        unregister_owner(owner_name)
        return

    with _registry_lock:
        previous_server = _owner_to_server.get(owner_name)
        if previous_server and previous_server != server_url:
            previous_worker = _workers_by_server.get(previous_server)
            if previous_worker is not None:
                previous_worker.remove_owner(owner_name)

        _owner_to_server[owner_name] = server_url
        worker = _get_or_create_worker(server_url)

    worker.set_owner_models(owner_name, models, keep_alive)


def unregister_owner(owner):
    owner_name = str(owner or '').strip()
    if not owner_name:
        return

    with _registry_lock:
        server_url = _owner_to_server.pop(owner_name, None)
        if server_url is not None:
            worker = _workers_by_server.get(server_url)
            if worker is not None:
                worker.remove_owner(owner_name)
            return

        for worker in _workers_by_server.values():
            worker.remove_owner(owner_name)


def get_runtime_status(include_ps=True):
    with _registry_lock:
        owner_map = dict(_owner_to_server)
        workers = list(_workers_by_server.values())

    servers = [worker.get_status_snapshot(include_ps=include_ps) for worker in workers]
    servers.sort(key=lambda item: item.get('server_url', ''))

    return {
        'owner_to_server': owner_map,
        'server_count': len(servers),
        'servers': servers,
        'updated_at': time.time(),
    }
