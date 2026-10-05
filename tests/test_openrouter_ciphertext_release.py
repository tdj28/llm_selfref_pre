"""The main-release exception binds one opaque provider field, not all outputs."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_public_release as audit


def test_main_release_exception_is_exact_opaque_metadata():
    path = (Path(__file__).resolve().parents[1]
            / "data/openrouter_swap/main_v1_20261004/raw/events.jsonl.gz")
    if not path.exists():
        pytest.skip("Main release not available in this checkout")
    raw = gzip.decompress(path.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == (
        "09a4cce440870d101b2abeeec85e0b75ff31f8d2244e9c98f2a80710fff4a244")
    row = json.loads(raw.splitlines()[2878])
    assert row["seq"] == 2879 and row["kind"] == "settle"
    detail = row["data"]["raw"]["choices"][0]["message"]["reasoning_details"][2]
    assert detail["type"] == "reasoning.encrypted"
    assert detail["format"] == "openai-responses-v1"
    matches = list(dict(audit.DIRECT_SECRET_RULES)["openai-key"].finditer(raw))
    assert len(matches) == 1
    match = matches[0]
    assert (match.start(), match.end()) == (16062128, 16064780)
    assert match.group() in detail["data"].encode()
    assert hashlib.sha256(match.group()).hexdigest() == (
        "691d78ab917852ea46bfe5b9aa349fd1d8c9b6b27a9e60d521cbf5443cb7435d")
    assert audit._reviewed_ciphertext_match(raw, "openai-key", match)
    assert not audit.scan_blob(str(path), path.read_bytes())
    assert not audit._reviewed_ciphertext_match(raw + b"\n", "openai-key", match)
    moved = b" " + raw
    moved_match = dict(audit.DIRECT_SECRET_RULES)["openai-key"].search(moved)
    assert not audit._reviewed_ciphertext_match(moved, "openai-key", moved_match)


def test_openrouter_encrypted_metadata_is_not_a_general_exemption():
    token = b"sk-" + b"z" * 32
    data = b'{"reasoning_details":[{"type":"reasoning.encrypted","data":"' + token + b'"}]}'
    findings = audit.scan_blob("fixture.json", data)
    assert any(f.rule == "openai-key" for f in findings)
    assert token.decode() not in repr(findings)
