#!/usr/bin/env python3
"""Bind a finished repeated-study release to its separate manuscript package.

Offline only. Replay the frozen row analysis, including its bootstrap intervals,
then verify the existing subsection/figure package. --write creates a new binding
file outside both inputs; it never edits a release, figure or main manuscript.
--paper also binds paper/repeated_extension.tex, creating it only with --write
and a pinned source commit. The subsection and figure path reconstruct exactly.
An explicitly pending publication commit is allowed until --require-pinned.
This is deterministic implementation QA, not independent scientific validation.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import repeat_publication as publication
from experiments.repeated_swap import analysis

base, p = publication.base, publication.p
SOURCES = ("scripts/verify_repeated_extension.py", "tests/test_repeated_extension.py")
PACKAGE = "evidence/repeated_extension"
PAPER = "paper/repeated_extension.tex"
ROW_FILES = ("PLAN.json", "RELEASE.json", "rows.json", "analysis.json")
SCOPE = {
    "row_analysis_replayed": True,
    "bootstrap_and_variance_uncertainty_replayed": True,
    "release_receipts_verified_by_release_adapter": True,
    "paper_and_figures_reconstructed_by_publication_helper": True,
    "new_inference_or_labels": False,
    "independent_human_validation": False,
    "authorizes_collection": False,
}


def _check(ok, message):
    base._check(ok, message)


def _same(actual, expected, message):
    _check(p.canonical(actual) == p.canonical(expected), message)


def _load_bound(root, name, entries):
    raw = (root / name).read_bytes()
    entry = next((item for item in entries if item["path"] == name), None)
    _check(entry == {"path": name, "bytes": len(raw), "sha256": base._sha(raw)},
           "Bound input changed: " + name)
    return base._load(root / name)


def _derive(rows, saved, metadata):
    # Use exactly the frozen analysis: no substitute bootstrap or new estimand.
    replay = analysis.analyze(rows)
    _same(saved, replay, "Released analysis differs from frozen row replay")
    data = publication._projection(replay, metadata)
    summaries = {}
    for model, block in data["models"].items():
        summaries[model] = {}
        for reader, endpoints in block["readers"].items():
            summaries[model][reader] = {}
            for endpoint, result in endpoints.items():
                contrast = result["contrasts"]["instruction_minus_transcript"]
                summaries[model][reader][endpoint] = {
                    "cells": deepcopy(result["cells"]),
                    "missingness": deepcopy(result["missingness"]),
                    "contrast": {key: deepcopy(value) for key, value in contrast.items()
                                 if key != "per_block"},
                    "variance": deepcopy(result["variance"]),
                }
    return data, summaries


def inspect(release, package, *, release_manifest_sha256, publication_manifest_sha256,
            require_pinned=False):
    source, target = Path(release).absolute(), Path(package).absolute()
    publication._digest(release_manifest_sha256)
    publication._digest(publication_manifest_sha256)
    base._no_symlinks(source)
    base._no_symlinks(target)
    binding = base._load(target / "binding.json")
    _check(not require_pinned or binding.get("release_commit_state") == "bound",
           "Publication source commit is pending")
    # This includes raw receipt replay, immutable freezes, final launch records,
    # full inventories, and deterministic reconstruction of text and figures.
    verdict = publication.verify(source, target,
        release_manifest_sha256=release_manifest_sha256,
        manifest_sha256=publication_manifest_sha256)
    _check(verdict["pass"], "Publication verification failed")
    release_entries = base._load(source / "MANIFEST.json")["files"]
    saved = {name: _load_bound(source, name, release_entries) for name in ROW_FILES}
    p.verify(source / "PLAN.json")  # Deliberately omit freeze: never query a remote.
    data, summaries = _derive(saved["rows.json"], saved["analysis.json"], saved["RELEASE.json"])
    _same(base._load(target / "figure_data.json"), data, "Figure data differs from row replay")
    _same(binding, base._load(target / "binding.json"), "Publication binding changed")
    _check(p.sha(source / "MANIFEST.json") == release_manifest_sha256
           and p.sha(target / "MANIFEST.json") == publication_manifest_sha256,
           "Manifest changed during verification")
    _same(base._entries(source), release_entries, "Release changed during verification")
    _same(base._entries(target), base._load(target / "MANIFEST.json")["files"],
          "Publication changed during verification")
    result = {
        "schema": "repeated-row-paper-binding-v1", "scope": SCOPE,
        "release_manifest_sha256": release_manifest_sha256,
        "publication_manifest_sha256": publication_manifest_sha256,
        "source_commit": binding["release_commit"],
        "source_commit_state": binding["release_commit_state"],
        "scientific_freeze": binding["scientific_freeze"],
        "operational_freeze": binding["operational_freeze"],
        "release_status": data["release_status"],
        "collection_complete": data["collection_complete"],
        "endpoint_complete": data["endpoint_complete"],
        "primary_reader": "astra", "primary_endpoint": "inclusive_current_assertion",
        "primary_family_size": 2, "primary_individual_confidence": .975,
        "nominal_family_confidence": .95,
        "inventory": data["inventory"], "models": summaries,
        "row_inputs": [entry for entry in release_entries if entry["path"] in ROW_FILES],
        "paper_outputs": base._entries(target),
        "source_hashes": {name: p.sha(ROOT / name) for name in SOURCES},
    }
    base._public(result)
    return result


def _paper_bytes(package, result):
    _check(Path(package).resolve() == (ROOT / PACKAGE).resolve(), "Paper requires the canonical evidence package")
    _check(result["source_commit_state"] == "bound", "Paper source commit is pending")
    text = (Path(package) / "subsection.tex").read_text()
    replacements = {
        r"\subsection{Repeated answers and source variation}":
            "\\subsection{Repeated answers and source variation}\n\\label{sec:repeated-extension}",
        r"\includegraphics[width=\linewidth]{repeated_main.pdf}":
            r"\includegraphics[width=\linewidth]{../evidence/repeated_extension/repeated_main.pdf}",
        r"\end{table}": "\\label{tab:repeated-extension}\n\\end{table}",
        r"\end{figure}": "\\label{fig:repeated-extension}\n\\end{figure}",
    }
    for original, replacement in replacements.items():
        _check(text.count(original) == 1, "Unexpected generated subsection structure")
        text = text.replace(original, replacement, 1)
    prefix = "% Source release commit: " + result["source_commit"] + "\n"
    prefix += "% Release manifest SHA-256: " + result["release_manifest_sha256"] + "\n"
    return (prefix + text).encode("utf-8")


def _bind_paper(package, result, *, write):
    path = ROOT / PAPER
    base._no_symlinks(path)
    _check(not write or not path.exists(), "Paper subsection destination must be new")
    raw = _paper_bytes(package, result)
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
    _check(path.read_bytes() == raw, "Paper subsection or figure path does not reconstruct")
    return {"path": PAPER, "bytes": len(raw), "sha256": base._sha(raw)}


def check_binding(release, package, binding_path, *, write=False, paper=False, **kwargs):
    path = Path(binding_path).absolute()
    base._no_symlinks(path)
    _check(path.suffix == ".json", "Binding must be a JSON file")
    _check(not any(path.resolve().is_relative_to(Path(root).resolve()) for root in (release, package)),
           "Binding must be outside the immutable release and presentation")
    _check(not write or not path.exists(), "Binding destination must be new")
    result = inspect(release, package, **kwargs)
    if paper:
        result["paper_input"] = _bind_paper(package, result, write=write)
    if write:
        base._write(path, result)
    else:
        _same(base._load(path), result, "Row-to-paper binding does not reconstruct")
    return {"pass": True, "binding_sha256": p.sha(path),
            "source_commit_state": result["source_commit_state"],
            "collection_complete": result["collection_complete"],
            "endpoint_complete": result["endpoint_complete"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--publication", required=True)
    parser.add_argument("--release-manifest-sha256", required=True)
    parser.add_argument("--publication-manifest-sha256", required=True)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--write", action="store_true", help="Create a new separate binding; never overwrite")
    parser.add_argument("--require-pinned", action="store_true")
    parser.add_argument("--paper", action="store_true", help="Bind the separate paper/repeated_extension.tex subsection")
    args = parser.parse_args(argv)
    result = check_binding(args.release, args.publication, args.binding, write=args.write, paper=args.paper,
        release_manifest_sha256=args.release_manifest_sha256,
        publication_manifest_sha256=args.publication_manifest_sha256,
        require_pinned=args.require_pinned)
    print(p.canonical(result))


if __name__ == "__main__":
    main()
