"""Exact-byte false-positive exception, never a general ciphertext bypass."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_public_release as audit


def test_exact_match_and_whole_blob_required(monkeypatch):
    token = b"sk-" + b"a" * 32
    data = b'{"encrypted_content":"' + token + b'"}'
    pattern = dict(audit.DIRECT_SECRET_RULES)["openai-key"]
    match = pattern.search(data)
    binding = ("openai-key", match.start(), match.end(), hashlib.sha256(token).hexdigest())
    monkeypatch.setattr(audit, "REVIEWED_CIPHERTEXT_MATCHES",
                        {binding: hashlib.sha256(data).hexdigest()})
    assert not audit.scan_blob("fixture.json", data)
    for changed in (data + b"\n", b" " + data, data.replace(b"encrypted_content", b"api_key"),
                    data.replace(b"a", b"b", 1), data + b"\n" + token):
        assert any(f.rule == "openai-key" for f in audit.scan_blob("fixture.json", changed))
    for changed_binding in (("anthropic-key", *binding[1:]),
                            (binding[0], binding[1] + 1, *binding[2:]),
                            (*binding[:2], binding[2] + 1, binding[3]),
                            (*binding[:3], "0" * 64)):
        monkeypatch.setattr(audit, "REVIEWED_CIPHERTEXT_MATCHES",
                            {changed_binding: hashlib.sha256(data).hexdigest()})
        assert audit.scan_blob("fixture.json", data)
    monkeypatch.setattr(audit, "REVIEWED_CIPHERTEXT_MATCHES", {binding: "0" * 64})
    assert audit.scan_blob("fixture.json", data)


def test_ciphertext_fields_are_not_generally_exempt():
    token = b"sk-" + b"a" * 32
    assert audit.scan_blob("fixture.json", b'{"encrypted_content":"' + token + b'"}')


def test_real_release_match_is_the_reviewed_opaque_field():
    path = Path(__file__).resolve().parents[1] / "data/frontier_bilingual_b1/completed_20261002/raw/events.jsonl"
    if not path.exists():
        pytest.skip("Completed release not yet packaged")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "923b93b3b4e699e55878295c114de3df6bda3d624763494abe53d51497bc4925"
    row = json.loads(raw.splitlines()[724])
    assert row["kind"] == "result"
    assert row["data"]["id"] == "judge:astra-block-03-en-final-self-history:openai:structured"
    output = row["data"]["raw"]["output"][0]
    assert output["type"] == "reasoning"
    ciphertext = output["encrypted_content"].encode()
    assert len(ciphertext) == 4004
    matches = list(dict(audit.DIRECT_SECRET_RULES)["openai-key"].finditer(raw))
    assert len(matches) == 1 and matches[0].group() in ciphertext
    assert not audit.scan_blob(str(path), raw)
    assert audit.scan_blob(str(path), raw + b"\n")
