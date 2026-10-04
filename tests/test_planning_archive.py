"""Local navigation and preservation checks; no collection or network access."""

import hashlib
import os
from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "provenance/planning"
INDEX = ARCHIVE / "README.md"
LINK = re.compile(rb"\]\(([^\s()]+)\)")
MAP_ROW = re.compile(
    r"^\| (docs/[^ |]+\.md) \| \[[^\]]+\]\(([^)]+\.md)\) "
    r"\| (Byte-identical|Relative links only) \|$",
    re.MULTILINE,
)


def git_blob(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def local_links(raw):
    for match in LINK.finditer(raw):
        target = urlsplit(match[1].decode())
        if not target.scheme and not target.netloc and target.path:
            yield unquote(target.path)


class PlanningArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        index = INDEX.read_text()
        cls.commit = re.search(r"Source commit: `([0-9a-f]{40})`", index)[1]
        cls.rows = MAP_ROW.findall(index)
        cls.moves = {old: ARCHIVE / new for old, new, _ in cls.rows}

    def test_map_is_complete_and_unambiguous(self):
        self.assertEqual(len(self.rows), 8)
        self.assertEqual(len(self.moves), 8)
        self.assertEqual(len(set(self.moves.values())), 8)
        self.assertEqual(
            set(ARCHIVE.glob("*.md")), {INDEX, *self.moves.values()}
        )
        for old, target in self.moves.items():
            with self.subTest(old=old):
                self.assertEqual(target.name, Path(old).name)
                self.assertEqual(target.parent, ARCHIVE)
                self.assertFalse(target.is_symlink())

    def test_source_bytes_allow_only_declared_link_rebasing(self):
        changes = []
        for old, new, preservation in self.rows:
            with self.subTest(old=old):
                original = git_blob(self.commit, old)
                destination = ARCHIVE / new

                def rebase(match):
                    target = urlsplit(match[1].decode())
                    if target.scheme or target.netloc or not target.path:
                        return match[0]
                    original_target = (ROOT / old).parent / target.path
                    relative = original_target.resolve().relative_to(ROOT).as_posix()
                    relocated = self.moves.get(relative, ROOT / relative)
                    path = os.path.relpath(relocated, destination.parent)
                    suffix = ("?" + target.query if target.query else "")
                    suffix += "#" + target.fragment if target.fragment else ""
                    changes.append((old, target.path))
                    return b"](" + (path + suffix).encode() + b")"

                expected = LINK.sub(rebase, original)
                self.assertEqual(destination.read_bytes(), expected)
                self.assertEqual(
                    preservation == "Byte-identical", expected == original
                )
        self.assertEqual(len(changes), 8)

    def test_only_required_compatibility_pointer_remains(self):
        for old in self.moves:
            with self.subTest(old=old):
                if old == "docs/HUMAN_CODING_HANDOFF.md":
                    pointer = (ROOT / old).read_bytes()
                    self.assertLessEqual(len(pointer.splitlines()), 8)
                    self.assertIn(
                        b"../provenance/planning/HUMAN_CODING_HANDOFF.md", pointer
                    )
                else:
                    self.assertFalse((ROOT / old).exists())

    def test_local_navigation_targets_exist(self):
        paths = [ROOT / name for name in (
            "AGENTS.md", "docs/README.md", "docs/REPRODUCTION.md",
            "docs/HUMAN_CODING_HANDOFF.md", "provenance/README.md",
        )]
        paths += [INDEX, *self.moves.values()]
        for path in paths:
            for target in local_links(path.read_bytes()):
                with self.subTest(source=path.relative_to(ROOT), target=target):
                    self.assertTrue((path.parent / target).exists())

    def test_active_indexes_do_not_link_to_old_locations(self):
        for name in ("docs/README.md", "docs/REPRODUCTION.md"):
            path = ROOT / name
            for target in local_links(path.read_bytes()):
                relative = (path.parent / target).resolve().relative_to(ROOT)
                self.assertNotIn(relative.as_posix(), self.moves)

    def test_historical_records_are_unchanged_and_resolve_through_map(self):
        snapshot = ROOT / "provenance/root-docs/20261003"
        for path in snapshot.iterdir():
            if path.is_file():
                with self.subTest(snapshot=path.name):
                    self.assertEqual(
                        path.read_bytes(),
                        git_blob(self.commit, path.relative_to(ROOT).as_posix()),
                    )
        for line in (snapshot / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split(maxsplit=1)
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)

        draft = "docs/JLENS_CAUSAL_REPORT_PROTOCOL_20261001.md"
        self.assertEqual((ROOT / draft).read_bytes(), git_blob(self.commit, draft))
        roadmap = "docs/BERG_REPLICATION_MECHANISM_ROADMAP_20260930.md"
        self.assertIn(Path(roadmap).name, (ROOT / draft).read_text())
        historical = b"\n".join(path.read_bytes() for path in snapshot.glob("*.md"))
        for old, target in self.moves.items():
            if old.encode() in historical or old == roadmap:
                self.assertTrue(target.is_file(), old)


if __name__ == "__main__":
    unittest.main()
