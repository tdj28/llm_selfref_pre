"""Offline replay with the exact reviewed October 5 scanner, not a relaxed scan."""
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AUDITOR = "scripts/audit_public_release.py"
OLD_SHA = "97db36ab3d45eb9e59127b66ee96fce57897dc27aa5ce2349b60538171d5a1e6"
CURRENT_SHA = "51ef43e48907457daa903d1adc991fa9c3193ad2a8c41aabaca089466f286ced"
CURRENT_COMMIT = "b859a8430e1602fecf4317d6e2b5e0de98e47c86"
OLD_COMMIT = "0438e6c12e6024da7e4284ec6c396e27c6c1738a"
COMPAT_SHA = "fe26aabbbfbd63937ddf1e6fdcaeaf1227465b1419668441d3c54fbd142d7ee4"
MAPPING_SHA = "1fa35c8ca094c4936d3836b1f28f3cf9226836451f2efc0249c65ccc5f0f69ce"


def checked_scanner(root=ROOT):
    from experiments import dose_release_compat as c
    before = c.regular(Path(root) / AUDITOR)
    c.require(c.digest(before) == CURRENT_SHA, "Unapproved current public scanner")
    git = c.GitBlobs(root)
    archived = git.query("cat-file", "blob", OLD_COMMIT + ":" + AUDITOR)
    reviewed = git.query("cat-file", "blob", CURRENT_COMMIT + ":" + AUDITOR)
    c.require(c.digest(archived) == OLD_SHA and reviewed == before,
              "Historical/reviewed scanner blob differs")
    return archived, before


@contextmanager
def source_hash_view(root=ROOT):
    """Historical provenance only. Imported public-scanner functions stay current."""
    from experiments.openrouter_swap import protocol as common
    from experiments import openweights_a2_figures as figures
    from experiments import dose_release_compat as c
    archived, before = checked_scanner(root)
    scanner = Path(root) / AUDITOR
    with ExitStack() as stack:
        for module, name in ((common, "sha"), (figures, "_sha")):
            original = getattr(module, name)
            def historical(path, original=original):
                if Path(path).absolute() == scanner:
                    c.require(c.regular(scanner) == before, "Public scanner changed during replay")
                    return c.digest(archived)
                return original(path)
            stack.enter_context(patch.object(module, name, historical))
        yield {"historical_scanner_sha256": OLD_SHA, "active_scanner_sha256": CURRENT_SHA}
    c.require(c.regular(scanner) == before, "Public scanner changed during replay")


def run_child(view, env, action, arguments=()):
    from experiments import dose_release_compat as c
    result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                             "_dose_child", action, *map(str, arguments)],
                            cwd=view, env=env, capture_output=True, text=True, timeout=1800)
    c.require(result.returncode == 0, "Current-scanner replay failed:\n"
              + result.stdout[-6000:] + result.stderr[-6000:])
    return result.stdout


def mapping_replay(root=ROOT):
    from experiments import mapping_release_history as h
    c = h.compat
    with h.verified_view(root) as (view, env, record):
        adapter = view / h.ADAPTER
        c.require(not adapter.exists(), "Test adapter entered historical inventory")
        with adapter.open("xb") as stream:
            stream.write(c.regular(h.__file__))
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "_mapping_child"],
                                cwd=view, env={**env, "MAPPING_HISTORY_CHILD": "1"},
                                capture_output=True, text=True, timeout=1800)
        c.require(result.returncode == 0, "Mapping historical tests failed:\n"
                  + result.stdout[-6000:] + result.stderr[-6000:])
        lines = [line[len(h.MARKER):] for line in result.stdout.splitlines() if line.startswith(h.MARKER)]
        c.require(len(lines) == 1, "Missing/duplicate mapping execution receipt")
        receipt = json.loads(lines[0])
        c.require(h.valid_receipt(receipt), "Incomplete mapping execution receipt")
        return {"execution": receipt, "historical_view": record}


@contextmanager
def current_scanner_view(*, child=False):
    from experiments import dose_release_compat as c, mapping_release_history as h
    c.require(c.digest(c.regular(c.__file__)) == COMPAT_SHA, "Bound dose adapter changed")
    c.require(c.digest(c.regular(h.__file__)) == MAPPING_SHA, "Mapping adapter changed")
    if not child:
        checked_scanner()
    with patch.object(c, "NEW_AUDITOR", CURRENT_SHA), \
         patch.object(c, "run_child", run_child), \
         patch.object(h, "SCANNER_COMMIT", CURRENT_COMMIT), \
         patch.object(h, "replay", mapping_replay):
        yield


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("_dose_child", "_mapping_child"):
        raise ValueError("Internal offline child entry point only")
    if args[0] == "_mapping_child":
        with current_scanner_view(child=True):
            from experiments import mapping_release_history as h
            return h.child()
    from experiments import dose_release_compat as c
    c.require(c.digest(c.regular(c.__file__)) == COMPAT_SHA, "Bound dose adapter changed")
    with patch.object(c, "NEW_AUDITOR", CURRENT_SHA):
        return c.child(args[1], args[2:])


if __name__ == "__main__":
    sys.exit(main())
