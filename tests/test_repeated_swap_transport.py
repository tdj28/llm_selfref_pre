import json
from pathlib import Path
import re
import subprocess

import pytest

from experiments.repeated_swap.transport import live_sender
from experiments.openrouter_swap.providers import TransportError


def test_key_stdin_only_and_deadline():
    def run(argv, **kwargs):
        assert "private-test-value" not in " ".join(argv)
        assert "--max-time" in argv and kwargs["timeout"] == 910
        text = kwargs["input"].decode()
        path = re.search(r'output = "([^"]+)"', text)[1]
        Path(path).write_text(json.dumps({"id": "test"}))
        return subprocess.CompletedProcess(argv, 0, b"200", b"")
    assert live_sender("private-test-value", run=run)({"model": "test"}) == {"id": "test"}


@pytest.mark.parametrize("code,body", [(28,b""),(0,b'{"x":1,"x":2}'),
                                      (0,b'{"v":"private-test-value"}'),
                                      (0,b'{"error":"failure"}')])
def test_bad_response_is_sanitized(code, body):
    def run(argv, **kwargs):
        path = re.search(r'output = "([^"]+)"', kwargs["input"].decode())[1]
        Path(path).write_bytes(body)
        return subprocess.CompletedProcess(argv, code, b"200", b"private-test-value")
    with pytest.raises(TransportError) as exc:
        live_sender("private-test-value", run=run)({"model": "test"})
    assert "private-test-value" not in str(exc.value)
    assert exc.value.__context__ is None


def test_no_retry_after_timeout():
    calls = []
    def run(*args, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("test", 910)
    with pytest.raises(TransportError):
        live_sender("private-test-value", run=run)({"model": "test"})
    assert len(calls) == 1
