"""One-shot HTTP with a total deadline; credentials never enter process argv."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from experiments.openrouter_swap.providers import ENDPOINT, TransportError, _public_body


def _strict(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate response key")
            result[key] = value
        return result
    result = json.loads(payload, object_pairs_hook=pairs)
    json.dumps(result, allow_nan=False)
    return result


def live_sender(api_key, *, deadline=900, run=subprocess.run):
    if (not isinstance(api_key, str) or not api_key or
            any(c.isspace() or c in '\\"' for c in api_key)):
        raise ValueError("Invalid credential")
    if not isinstance(deadline, int) or not 1 <= deadline <= 900:
        raise ValueError("Bounded total deadline required")

    def send(request):
        _public_body(request)
        payload = json.dumps(request, ensure_ascii=False, allow_nan=False).encode()
        if api_key.encode() in payload:
            raise ValueError("Credential in request body")
        failed, status, raw = False, None, None
        with tempfile.TemporaryDirectory(prefix="repeated-swap-http-") as directory:
            root = Path(directory)
            source, target = root / "request.json", root / "response.json"
            source.write_bytes(payload)
            source.chmod(0o600)
            # The key is supplied over stdin, not a shell command or argv.
            config = (f'url = "{ENDPOINT}"\nrequest = "POST"\n'
                      f'header = "Authorization: Bearer {api_key}"\n'
                      'header = "Content-Type: application/json"\n'
                      f'data-binary = "@{source}"\noutput = "{target}"\n')
            try:
                response = run(["curl", "--disable", "--silent", "--show-error",
                                "--noproxy", "*", "--proto", "=https",
                                "--connect-timeout", "30", "--max-time", str(deadline),
                                "--max-filesize", str(32 * 1024 * 1024),
                                "--write-out", "%{http_code}", "--config", "-"],
                               input=config.encode(), capture_output=True,
                               timeout=deadline + 10, check=False)
                status = int(response.stdout) if response.stdout.isdigit() else None
                if response.returncode or status != 200:
                    raise ValueError("HTTP request did not complete")
                body = target.read_bytes()
                if len(body) > 32 * 1024 * 1024 or api_key.encode() in body:
                    raise ValueError("Invalid response")
                raw = _strict(body)
                if api_key in json.dumps(raw, ensure_ascii=False):
                    raise ValueError("Credential in decoded response")
                _public_body(raw)
                if not isinstance(raw, dict) or raw.get("error") is not None:
                    raise ValueError("Provider returned error")
            except Exception:
                failed = True
        # No transport body, header, credential or exception context escapes.
        if failed:
            raise TransportError(status)
        return raw
    return send
