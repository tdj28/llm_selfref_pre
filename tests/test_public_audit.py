import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "public_audit", Path(__file__).resolve().parents[1] / "scripts/audit_public_files.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class PublicAuditTests(unittest.TestCase):
    def test_normal_document(self):
        self.assertEqual(audit.audit_entry("README.md", b"No keys are included."), [])

    def test_private_filenames(self):
        for name in (".env", ".env.local", "checkpoint.md", "keys/id_ed25519"):
            with self.subTest(name=name):
                self.assertTrue(audit.audit_entry(name, b""))

    def test_private_directory(self):
        self.assertTrue(audit.audit_entry(".ssh/config", b""))

    def test_credential_value_is_not_printed(self):
        value = b"sk-" + b"x" * 30
        errors = audit.audit_entry("unexpected.txt", value)
        self.assertEqual(errors, ["possible credential: unexpected.txt"])
        self.assertNotIn(value.decode(), str(errors))

    def test_other_provider_formats(self):
        for prefix in (b"ghp_", b"hf_"):
            self.assertTrue(audit.audit_entry("unexpected.txt", prefix + b"x" * 40))


if __name__ == "__main__":
    unittest.main()
