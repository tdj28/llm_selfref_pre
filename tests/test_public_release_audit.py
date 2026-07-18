from __future__ import annotations

import hashlib
import json
import unittest

from scripts.audit_public_release import (
    is_allowed_placeholder,
    path_findings,
    release_manifest_findings,
    scan_blob,
)


class PublicReleaseAuditTests(unittest.TestCase):
    def test_placeholders_and_environment_references_are_allowed(self) -> None:
        for value in (
            b"",
            b"your-key-here",
            b"<secret>",
            b"${OPENAI_API_KEY}",
            b"os.getenv('OPENAI_API_KEY')",
            b"REDACTED",
        ):
            self.assertTrue(is_allowed_placeholder(value), value)

    def test_nonplaceholder_assignment_is_rejected_without_echoing_value(self) -> None:
        secret = b"live" + b"value" * 8
        data = b"RUNPOD_API_" + b"KEY=" + secret + b"\n"
        findings = scan_blob("fixture.env", data)
        self.assertEqual([finding.rule for finding in findings], ["secret-assignment"])
        self.assertNotIn(secret.decode(), repr(findings))

    def test_exact_guest_attestation_fixture_is_the_only_allowed_variant(self) -> None:
        placeholder = b"unit-secret-that-must-never-be-retained"
        self.assertTrue(is_allowed_placeholder(placeholder))
        self.assertFalse(is_allowed_placeholder(placeholder + b"-changed"))
        self.assertEqual(
            scan_blob(
                "fixture.py",
                b'"RUNPOD_API_KEY": "' + placeholder + b'"\n',
            ),
            [],
        )
        findings = scan_blob(
            "fixture.py",
            b'"RUNPOD_API_KEY": "' + placeholder + b'-changed"\n',
        )
        self.assertEqual([finding.rule for finding in findings], ["quoted-secret-mapping"])

    def test_known_token_prefix_is_rejected(self) -> None:
        token = b"sk-" + (b"a" * 32)
        findings = scan_blob("fixture.txt", b"value: " + token)
        self.assertEqual([finding.rule for finding in findings], ["openai-key"])

    def test_prefix_shaped_documentation_placeholder_is_allowed(self) -> None:
        placeholder = b"sk-ant-" + b"your-anthropic-key"
        self.assertEqual(scan_blob("README.md", placeholder), [])

    def test_binary_blob_is_skipped(self) -> None:
        token = b"sk-" + (b"a" * 32)
        self.assertEqual(scan_blob("image.bin", b"\x00" + token), [])

    def test_private_and_unreviewed_paths_are_rejected(self) -> None:
        paths = (
            "checkpoint.md",
            "data/run/annotation_key_v1_private.csv",
            "data/run/coder_1.csv",
            "external/upstream.ipynb",
            "weights/model.safetensors",
        )
        rules = {finding.rule for finding in path_findings(paths)}
        self.assertEqual(
            rules,
            {
                "private-continuity-file",
                "private-annotation-key",
                "private-coder-file",
                "unreviewed-notebook",
                "restricted-model-artifact",
            },
        )

    def test_environment_templates_are_allowed(self) -> None:
        self.assertEqual(path_findings(("steering/.env.example", ".env-example")), [])

    def test_release_manifest_verifies_indexed_hash_and_size(self) -> None:
        content = b"public result\n"
        digest = hashlib.sha256(content).hexdigest()
        manifest_path = "data/run/release_manifest.json"
        manifest = json.dumps(
            {"files": [{"path": "result.txt", "bytes": len(content), "sha256": digest}]}
        ).encode()
        findings, verified = release_manifest_findings(
            {manifest_path: manifest}, {"data/run/result.txt": (len(content), digest)}
        )
        self.assertEqual(findings, [])
        self.assertEqual(verified, 1)

    def test_release_manifest_rejects_hash_drift(self) -> None:
        content = b"public result\n"
        manifest_path = "data/run/release_manifest.json"
        manifest = json.dumps(
            {"files": [{"path": "result.txt", "bytes": len(content), "sha256": "0" * 64}]}
        ).encode()
        findings, verified = release_manifest_findings(
            {manifest_path: manifest},
            {"data/run/result.txt": (len(content), hashlib.sha256(content).hexdigest())},
        )
        self.assertEqual([finding.rule for finding in findings], ["release-hash-mismatch"])
        self.assertEqual(verified, 0)


if __name__ == "__main__":
    unittest.main()
