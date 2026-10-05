"""Reviewed hash metadata and synthetic guard tests; no private receipt fixture."""
import gzip
import hashlib
import json

import pytest

from scripts import audit_public_release as audit


MATCH_SHA = "5b41f973d0f5a6c58a53803e0011468d817392f474c4e266c9b17dbb93657625"
REVIEWED = (
    (2195, 4378, "c61bb99830e181da1aed8baa1a5189ef3bce3b52e4986465da3c80f520f545f5"),
    (3468727, 3470910, "9a3c4a19359b38f934c2d827d631141d200a0d5b2ad9a786a68b8c8c43f9ac26"),
    (2198, 4381, "e64d68d2a1856a1e5433c56552051cc4209460cce1b25748a8ca12e33d542560"),
    (2090, 4273, "889e6244fdf47fe6153f34981f5ece0448431da72e158c6a410cad09314e332d"),
)


@pytest.mark.parametrize("start,end,blob_sha", REVIEWED)
def test_reviewed_metadata_binds_all_four_containers(start, end, blob_sha):
    assert end - start == 2183
    assert audit.REVIEWED_CIPHERTEXT_MATCHES[("openai-key", start, end, MATCH_SHA)] == blob_sha


def synthetic_forms():
    token = "sk-" + "z" * 32
    response = {"choices": [{"message": {"reasoning_details": [{
        "type": "reasoning.encrypted", "format": "azure-openai-responses-v1", "data": token}]}}]}
    event = {"seq": 728, "kind": "settle", "data": {"raw": response}}
    return (
        json.dumps(response, indent=2).encode(),
        b'{"seq":727,"kind":"reserve"}\n' + json.dumps(event, separators=(",", ":")).encode() + b"\n",
        json.dumps(response, ensure_ascii=False).encode(),
        json.dumps(event, ensure_ascii=False).encode(),
    )


def binding(raw):
    match = dict(audit.DIRECT_SECRET_RULES)["openai-key"].search(raw)
    return ("openai-key", match.start(), match.end(), hashlib.sha256(match.group()).hexdigest())


@pytest.mark.parametrize("index", range(4))
def test_synthetic_forms_require_exact_binding_including_gzip(monkeypatch, index):
    forms = synthetic_forms()
    raw = forms[index]
    assert audit.scan_blob("fixture.json", raw)
    monkeypatch.setattr(audit, "REVIEWED_CIPHERTEXT_MATCHES", {binding(raw): hashlib.sha256(raw).hexdigest()})
    assert not audit.scan_blob("fixture.json", raw)
    assert not audit.scan_blob("fixture.json.gz", gzip.compress(raw, mtime=0))
    for other in forms:
        if other != raw:
            assert audit.scan_blob("other.json", other)


@pytest.mark.parametrize("mutation", ["append", "shift", "type", "format", "match", "extra"])
def test_changed_bytes_never_reuse_review(monkeypatch, mutation):
    raw = synthetic_forms()[0]
    monkeypatch.setattr(audit, "REVIEWED_CIPHERTEXT_MATCHES", {binding(raw): hashlib.sha256(raw).hexdigest()})
    if mutation == "append":
        changed = raw + b"\n"
    elif mutation == "shift":
        changed = b" " + raw
    elif mutation == "type":
        changed = raw.replace(b"reasoning.encrypted", b"reasoning.untrusted")
    elif mutation == "format":
        changed = raw.replace(b"azure-openai-responses-v1", b"another-responses-format")
    elif mutation == "match":
        changed = raw.replace(b"z" * 32, b"y" * 32)
    else:
        changed = raw + b"\n" + b"sk-" + b"q" * 32
    assert any(f.rule == "openai-key" for f in audit.scan_blob("fixture.json", changed))


@pytest.mark.parametrize("part", ["rule", "start", "end", "match_hash", "blob_hash"])
def test_each_guard_component_is_required(monkeypatch, part):
    raw = synthetic_forms()[0]
    key = list(binding(raw))
    blob_hash = hashlib.sha256(raw).hexdigest()
    if part == "rule":
        key[0] = "anthropic-key"
    elif part == "start":
        key[1] += 1
    elif part == "end":
        key[2] -= 1
    elif part == "match_hash":
        key[3] = "0" * 64
    else:
        blob_hash = "0" * 64
    monkeypatch.setattr(audit, "REVIEWED_CIPHERTEXT_MATCHES", {tuple(key): blob_hash})
    assert audit.scan_blob("fixture.json", raw)


def test_encrypted_type_never_exempts_unreviewed_content():
    raw = synthetic_forms()[0]
    findings = audit.scan_blob("fixture.json", raw)
    assert any(f.rule == "openai-key" for f in findings)
    assert ("sk-" + "z" * 32) not in repr(findings)
