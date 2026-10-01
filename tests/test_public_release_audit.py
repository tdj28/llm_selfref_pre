from __future__ import annotations

import hashlib
import gzip
import json
import subprocess
import unittest
from pathlib import Path, PurePosixPath

from experiments.causal_transplant.build_release_manifest import is_private_name

from scripts.audit_public_release import (
    RELEASE_MANIFEST_ALIASES,
    is_allowed_placeholder,
    is_release_manifest,
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

    def test_nul_byte_does_not_hide_a_secret(self) -> None:
        token = b"sk-" + (b"a" * 32)
        findings = scan_blob("image.bin", b"\x00" + token)
        self.assertEqual([finding.rule for finding in findings], ["openai-key"])

    def test_gzip_log_is_scanned_without_echoing_value(self) -> None:
        token = b"live" + b"value" * 8
        findings = scan_blob("setup.log.gz", gzip.compress(b"OSF_TOKEN=" + token))
        self.assertEqual([finding.rule for finding in findings], ["secret-assignment"])
        self.assertNotIn(token.decode(), repr(findings))

    def test_inline_json_secret_and_placeholder(self) -> None:
        token = b"live" + b"value" * 8
        for name in (b"OSF_TOKEN", b"RUNPOD_API_KEY"):
            with self.subTest(name=name):
                findings = scan_blob("record.json", b'{"other": 1, "' + name + b'": "' + token + b'"}')
                self.assertEqual([finding.rule for finding in findings], ["quoted-secret-mapping"])
                self.assertNotIn(token.decode(), repr(findings))
                self.assertEqual(scan_blob("record.json", b'{"' + name + b'": "REDACTED"}'), [])

    def test_corrupt_and_oversized_gzip_fail_closed(self) -> None:
        from unittest.mock import patch

        self.assertEqual(scan_blob("broken.gz", b"not gzip")[0].rule, "invalid-compressed-file")
        with patch("scripts.audit_public_release.MAX_DECOMPRESSED_BYTES", 16):
            self.assertEqual(scan_blob("large.gz", gzip.compress(b"x" * 17))[0].rule, "compressed-scan-limit")

    def test_release_manifest_names_are_case_insensitive(self) -> None:
        for name in ("release_manifest.json", "RELEASE_MANIFEST.json", "MANIFEST.json"):
            self.assertTrue(is_release_manifest("data/run/" + name))
        self.assertFalse(is_release_manifest("data/run/plan_manifest.json"))
        self.assertFalse(is_release_manifest("data/run/manifest.json"))

    def test_annotation_filename_variants_are_rejected(self) -> None:
        paths = ("data/run/coder1.csv", "data/run/wave1_coder_A.csv", "data/run/annotation_key_v3_wave1.csv")
        self.assertEqual(len(path_findings(paths)), len(paths))

    def test_private_annotation_variants_are_ignored_and_not_manifested(self) -> None:
        names = ("coder1.csv", "wave1_coder_A.csv", "annotation_key_v3_wave1.csv", "annotation_key_v3_wave1.csv.sha256")
        paths = ["data/causal_transplant/confirmatory_v1_20260709/" + name for name in names]
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin"],
            cwd=Path(__file__).resolve().parents[1],
            input="\n".join(paths) + "\n", text=True, capture_output=True, check=True,
        )
        self.assertEqual(set(result.stdout.splitlines()), set(paths))
        for name in names:
            self.assertTrue(is_private_name(name), name)
        self.assertFalse(is_private_name("human_annotation_packet_v3_wave1.csv"))

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


class ReleaseManifestAliasTests(unittest.TestCase):
    ALIASES = {
        "evidence/source_alignment/RELEASE_MANIFEST.json":
            "data/berg_source_replication/source_aligned_v1_20261001/RELEASE_MANIFEST.json",
        "evidence/ensemble_alignment/RELEASE_MANIFEST.json":
            "data/berg_ensemble_replication/random_subset_v1_20261001/RELEASE_MANIFEST.json",
    }

    def setUp(self) -> None:
        content = b"public result\n"
        self.record = (len(content), hashlib.sha256(content).hexdigest())
        self.relative = "rows/result.json"
        self.manifest = json.dumps({"files": [{
            "path": self.relative, "bytes": self.record[0], "sha256": self.record[1],
        }]}).encode()

    def test_alias_allowlist_is_exact(self) -> None:
        self.assertEqual(RELEASE_MANIFEST_ALIASES, self.ALIASES)
        for alias, source in self.ALIASES.items():
            self.assertTrue(is_release_manifest(alias))
            self.assertTrue(is_release_manifest(source))

    def test_valid_aliases_validate_canonical_rows_without_evidence_rows(self) -> None:
        manifests, records = {}, {}
        for alias, source in self.ALIASES.items():
            manifests.update({alias: self.manifest, source: self.manifest})
            records[str(PurePosixPath(source).parent / self.relative)] = self.record
        findings, verified = release_manifest_findings(manifests, records)
        self.assertEqual(findings, [])
        self.assertEqual(verified, 4)

    def test_alias_requires_source_in_indexed_manifests_map(self) -> None:
        for alias, source in self.ALIASES.items():
            with self.subTest(alias=alias):
                records = {
                    source: (len(self.manifest), hashlib.sha256(self.manifest).hexdigest()),
                    str(PurePosixPath(source).parent / self.relative): self.record,
                    str(PurePosixPath(alias).parent / self.relative): self.record,
                }
                findings, verified = release_manifest_findings({alias: self.manifest}, records)
                self.assertEqual([(f.path, f.rule) for f in findings],
                                 [(alias, "missing-release-alias-source")])
                self.assertEqual(verified, 0)

    def test_alias_requires_byte_equality_not_json_equivalence(self) -> None:
        for alias, source in self.ALIASES.items():
            for changed in (self.manifest + b"\n", b'{"files": []}'):
                with self.subTest(alias=alias, changed=changed):
                    findings, verified = release_manifest_findings(
                        {alias: changed, source: self.manifest},
                        {str(PurePosixPath(source).parent / self.relative): self.record},
                    )
                    self.assertEqual([(f.path, f.rule) for f in findings],
                                     [(alias, "release-alias-mismatch")])
                    self.assertEqual(verified, 1)

    def test_alias_missing_canonical_data_cannot_use_evidence_copy(self) -> None:
        for alias, source in self.ALIASES.items():
            with self.subTest(alias=alias):
                canonical = str(PurePosixPath(source).parent / self.relative)
                findings, verified = release_manifest_findings(
                    {alias: self.manifest, source: self.manifest},
                    {str(PurePosixPath(alias).parent / self.relative): self.record},
                )
                self.assertEqual([(f.path, f.rule) for f in findings],
                                 [(canonical, "untracked-release-file")] * 2)
                self.assertEqual(verified, 0)

    def test_alias_rejects_canonical_size_and_hash_drift(self) -> None:
        for alias, source in self.ALIASES.items():
            for record, rule in (
                ((self.record[0] + 1, self.record[1]), "release-byte-mismatch"),
                ((self.record[0], "0" * 64), "release-hash-mismatch"),
            ):
                with self.subTest(alias=alias, rule=rule):
                    canonical = str(PurePosixPath(source).parent / self.relative)
                    findings, verified = release_manifest_findings(
                        {alias: self.manifest, source: self.manifest},
                        {canonical: record,
                         str(PurePosixPath(alias).parent / self.relative): self.record},
                    )
                    self.assertEqual([(f.path, f.rule) for f in findings], [(canonical, rule)] * 2)
                    self.assertEqual(verified, 0)

    def test_alias_still_validates_manifest_schema_and_paths(self) -> None:
        unsafe = json.loads(self.manifest)
        unsafe["files"][0]["path"] = "../result.json"
        for alias, source in self.ALIASES.items():
            for raw, rule in (
                (b"not json", "invalid-release-manifest"),
                (b'{"files": {}}', "invalid-release-manifest"),
                (b'{"files": [{}]}', "invalid-release-entry"),
                (json.dumps(unsafe).encode(), "unsafe-release-path"),
            ):
                with self.subTest(alias=alias, raw=raw):
                    findings, verified = release_manifest_findings({alias: raw, source: raw}, {})
                    self.assertEqual([f.rule for f in findings], [rule] * 2)
                    self.assertEqual(verified, 0)

    def test_unknown_copy_paths_do_not_infer_aliases_from_content(self) -> None:
        for alias, source in self.ALIASES.items():
            manifest = json.loads(self.manifest)
            manifest["source_manifest"] = source
            raw = json.dumps(manifest).encode()
            for unknown in (
                "evidence/other/RELEASE_MANIFEST.json",
                alias.replace("RELEASE_MANIFEST.json", "release_manifest.json"),
                alias.replace("RELEASE_MANIFEST.json", "archive/RELEASE_MANIFEST.json"),
            ):
                with self.subTest(unknown=unknown, source=source):
                    self.assertTrue(is_release_manifest(unknown))
                    findings, verified = release_manifest_findings(
                        {unknown: raw, source: raw},
                        {str(PurePosixPath(source).parent / self.relative): self.record},
                    )
                    self.assertEqual([(f.path, f.rule) for f in findings], [
                        (str(PurePosixPath(unknown).parent / self.relative), "untracked-release-file"),
                    ])
                    self.assertEqual(verified, 1)

    def test_alias_paths_do_not_bypass_secret_scanning(self) -> None:
        token = b"sk-" + b"a" * 32
        for alias in self.ALIASES:
            with self.subTest(alias=alias):
                findings = scan_blob(alias, b'{"note": "' + token + b'"}')
                self.assertEqual([f.rule for f in findings], ["openai-key"])
                self.assertNotIn(token.decode(), repr(findings))


if __name__ == "__main__":
    unittest.main()
