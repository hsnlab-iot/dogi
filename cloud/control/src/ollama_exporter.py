#!/usr/bin/env python3

import argparse
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_INTERVAL_SECONDS = 3.0
HEARTBEAT_SECONDS = 60.0
HTTP_TIMEOUT_SECONDS = 1.0


def parse_args():
	parser = argparse.ArgumentParser(
		description="Export Ollama /api/ps state to VictoriaMetrics via line protocol."
	)
	parser.add_argument(
		"--ollama-url",
		default=DEFAULT_OLLAMA_URL,
		help="Ollama base URL (base; /api/ps will be queried)",
	)
	parser.add_argument(
		"--victoria-url",
		required=True,
		help="VictoriaMetrics base URL for line protocol (will append /write if missing)",
	)
	parser.add_argument(
		"--interval",
		type=float,
		default=DEFAULT_INTERVAL_SECONDS,
		help="Polling interval in seconds (default: 3)",
	)
	parser.add_argument(
		"--measurement",
		default="ollama_state",
		help="Measurement name used in line protocol (default: ollama_state)",
	)
	parser.add_argument(
		"--log-level",
		default="INFO",
		choices=["DEBUG", "INFO", "WARNING", "ERROR"],
		help="Log level (default: INFO)",
	)
	return parser.parse_args()


def _escape_tag_value(value):
	return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


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
	# Look into common places for context/configured context length and
	# return a plain integer (or 0 if not present). Avoid returning tuples.
	if not isinstance(model_item, dict):
		return 0

	details = model_item.get("details") if isinstance(model_item.get("details"), dict) else {}
	options = model_item.get("options") if isinstance(model_item.get("options"), dict) else {}

	candidates = [
		_extract_first_number(model_item, ["context_size", "context_length", "ctx_size", "num_ctx"]),
		_extract_first_number(details, ["context_size", "context_length", "ctx_size", "num_ctx"]),
		_extract_first_number(options, ["num_ctx", "context_size", "context_length", "ctx_size"]),
	]

	for c in candidates:
		if c is not None:
			try:
				return int(c)
			except Exception:
				continue

	return 0


def _extract_gpu_utilization(model_item):

	size_vram = _extract_first_number(model_item, ["size_vram", "gpu_memory", "gpu_bytes"])
	model_size = _extract_first_number(model_item, ["size", "model_size"])

	if size_vram is not None and model_size and model_size > 0:
		return max(0.0, min(100.0, (size_vram / model_size) * 100.0))

	return 0.0

def _normalize_models(ps_payload):
	models = ps_payload.get("models", [])
	if not isinstance(models, list):
		return []

	normalized = []
	for item in models:
		if not isinstance(item, dict):
			continue

		model_name = (
			item.get("model")
			or "unknown"
		)

		normalized.append(
			{
				"model": str(model_name),
				"gpu_utilization": round(_extract_gpu_utilization(item), 2),
				"context_length": _extract_context_size(item),
			}
		)

	normalized.sort(key=lambda entry: entry["model"])
	return normalized


def build_line_protocol(measurement, normalized_models):
	lines = [f"{measurement} model_count={len(normalized_models)}i"]
	for entry in normalized_models:
		model_tag = _escape_tag_value(entry["model"])
		ctx = int(entry.get("context_length") or 0)
		gpu = float(entry.get("gpu_utilization") or 0.0)
		line = (
			f"{measurement},model={model_tag} "
			f"gpu_utilization={gpu},"
			f"context_length={ctx}i"
		)
		lines.append(line)
	return "\n".join(lines)


def fetch_ollama_ps(ollama_base_url):
	endpoint = urllib.parse.urljoin(ollama_base_url.rstrip("/") + "/", "api/ps")
	request = urllib.request.Request(endpoint, method="GET")
	with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
		raw = response.read()
	return json.loads(raw.decode("utf-8"))


def push_to_victoria(victoria_url, line_payload):
	req = urllib.request.Request(
		victoria_url,
		method="POST",
		data=line_payload.encode("utf-8"),
		headers={"Content-Type": "text/plain; charset=utf-8"},
	)
	with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
		response.read()


def run_export_loop(ollama_url, victoria_url, interval, measurement):
	last_sent_fingerprint = None
	last_sent_at = 0.0

	while True:
		cycle_started = time.monotonic()

		try:
			ps_payload = fetch_ollama_ps(ollama_url)
			normalized_models = _normalize_models(ps_payload)

			if not normalized_models:
				logging.debug("No loaded models reported by Ollama /api/ps")

			line_payload = build_line_protocol(measurement, normalized_models)
			fingerprint = json.dumps(normalized_models, sort_keys=True, separators=(",", ":"))
			now = time.monotonic()

			changed = fingerprint != last_sent_fingerprint
			heartbeat_due = (now - last_sent_at) >= HEARTBEAT_SECONDS

			if line_payload and (changed or heartbeat_due):
				push_to_victoria(victoria_url, line_payload)
				last_sent_fingerprint = fingerprint
				last_sent_at = now
				logging.info(
					"Exported %d model state line(s) to VictoriaMetrics%s",
					len(normalized_models),
					" (heartbeat)" if not changed else "",
				)
			else:
				logging.debug("State unchanged; skipping export")

		except urllib.error.HTTPError as err:
			logging.error("HTTP error: %s %s", err.code, err.reason)
		except urllib.error.URLError as err:
			logging.error("Network error: %s", err.reason)
		except json.JSONDecodeError as err:
			logging.error("Invalid JSON from Ollama /api/ps: %s", err)
		except Exception as err:
			logging.exception("Unexpected error in export loop: %s", err)

		elapsed = time.monotonic() - cycle_started
		sleep_for = max(0.0, interval - elapsed)
		time.sleep(sleep_for)


def main():
	args = parse_args()

	if args.interval <= 0:
		raise SystemExit("--interval must be > 0")

	logging.basicConfig(
		level=getattr(logging, args.log_level),
		format="%(asctime)s %(levelname)s %(message)s",
	)

	logging.info("Starting Ollama exporter")
	logging.info("Ollama URL: %s", args.ollama_url)
	# Normalize Victoria URL to ensure it targets the /write endpoint used by
	# VictoriaMetrics line-protocol ingestion. If user already provided a
	# /write path, leave it alone.
	victoria_url = args.victoria_url
	try:
		parsed = urllib.parse.urlparse(victoria_url)
		if not parsed.path.endswith("/write"):
			victoria_url = urllib.parse.urljoin(victoria_url.rstrip("/") + "/", "write")
	except Exception:
		victoria_url = args.victoria_url

	logging.info("Victoria URL: %s", victoria_url)
	logging.info("Polling interval: %.2fs", args.interval)

	run_export_loop(
		ollama_url=args.ollama_url,
		victoria_url=victoria_url,
		interval=args.interval,
		measurement=args.measurement,
	)


if __name__ == "__main__":
	main()
