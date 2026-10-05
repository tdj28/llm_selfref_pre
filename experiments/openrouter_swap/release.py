"""Build an audited saved-data bundle, or verify one without modifying it."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from . import analysis, protocol
from .ledger import Halted, Ledger, _no_symlinks, read_events
from .runner import Runner


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _load(path):
    _no_symlinks(path)
    value = json.loads(path.read_bytes(), object_pairs_hook=_pairs)
    protocol.canonical(value)  # Reject nonfinite JSON values too.
    return value


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _inventory(root):
    _no_symlinks(root)
    result = {}
    for path in sorted(root.rglob("*")):
        _no_symlinks(path)
        if not path.is_dir():
            if not path.is_file():
                raise ValueError("Nonregular artifact")
            name = path.relative_to(root).as_posix()
            if name != "MANIFEST.json":
                result[name] = {"sha256": protocol.sha(path), "size": path.stat().st_size}
    return result


def _replay(root):
    plan = protocol.verify(root / "PLAN.json")
    runtime = _load(root / "runtime.json")
    freeze, plan_hash = runtime["freeze"], protocol.sha(root / "PLAN.json")
    if (not isinstance(freeze, str) or len(freeze) != 40
            or any(c not in "0123456789abcdef" for c in freeze)
            or runtime["plan_sha256"] != plan_hash):
        raise ValueError("Runtime source binding mismatch")
    frozen = subprocess.check_output(["git", "show", f"{freeze}:{protocol.PLAN}"],
                                     cwd=protocol.ROOT, stderr=subprocess.DEVNULL)
    if frozen != (root / "PLAN.json").read_bytes():
        raise ValueError("Plan differs from recorded local freeze")
    admission = _load(root / "main_admission.json") if (root / "main_admission.json").exists() else None
    admitted = admission["admitted_models"] if admission else []
    if not isinstance(admitted, list) or len(set(admitted)) != len(admitted) or set(admitted) - set(plan["models"]):
        raise ValueError("Invalid main selection")
    with TemporaryDirectory() as temporary:
        raw = Path(temporary).resolve() / "raw"
        raw.mkdir()
        with gzip.open(root / "raw/events.jsonl.gz", "rb") as source, (raw / "events.jsonl").open("xb") as output:
            shutil.copyfileobj(source, output)
        with Ledger(raw, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            runner = Runner(plan, freeze, plan_hash, ledger, sender=None)
            audit = runner.audit()
            if admission is not None:
                events = read_events(raw / "events.jsonl")
                cutoff = next((i for i, event in enumerate(events) if event["kind"] == "reserve"
                               and event["data"]["phase"] == "main"), len(events))
                # Admission preceded main spending; replay that exact journal prefix.
                prior = raw.parent / "admission"
                prior.mkdir()
                (prior / "events.jsonl").write_bytes(b"".join((raw / "events.jsonl").read_bytes().splitlines(True)[:cutoff]))
                with Ledger(prior, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as history:
                    expected = Runner(plan, freeze, plan_hash, history, sender=None).main_admission()
                if admission != expected:
                    raise ValueError("Main admission does not reconstruct")
            try:
                fixtures_pass = runner.require_fixtures()["pass"]
            except Halted:
                fixtures_pass = False
            rows = {"screen": runner.rows("screen")}
            main_started = any(row["phase"] == "main" for row in ledger.rows())
            if admitted or main_started:
                rows["main"] = runner.rows("main", admitted if admission else None)
    complete = (fixtures_pass and not audit["unresolved"] and admission is not None
                and all(all(analysis._value(row, judge, endpoint) is not None
                            for judge in plan["judges"] for endpoint in analysis.ENDPOINTS)
                        for phase in rows.values() for row in phase))
    return {"schema": "openrouter-swap-release-v1", "freeze": freeze, "plan_sha256": plan_hash,
            "status": "complete" if complete else "incomplete", "fixtures_pass": fixtures_pass,
            "audit": audit}, rows, plan


def cell_counts(rows, models, cells, judge):
    """Positive / available label rate; missing labels never become negatives."""
    result = {}
    for model in models:
        result[model] = {}
        for cell in cells:
            selected = [row for row in rows if row["model"] == model and row["cell"] == cell]
            labels = [analysis._value(row, judge, "inclusive_current_assertion") for row in selected]
            known = [value for value in labels if type(value) is bool]
            result[model][cell] = {"positive": sum(known), "labeled": len(known),
                                   "planned": len(selected), "missing": len(selected) - len(known),
                                   "rate": sum(known) / len(known) if known else None}
    return result


def _figures(root, phases, plan):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts = {}
    for phase, rows in phases.items():
        cells = list(protocol.CELLS)[:4] if phase == "screen" else list(protocol.CELLS)
        models = list(plan["models"])
        for judge in ("astra", "opus"):
            name = f"{phase}_{judge}_inclusive"
            panel = counts[name] = cell_counts(rows, models, cells, judge)
            fig, ax = plt.subplots(figsize=(max(8, len(cells) * 1.6), 5.7))
            try:
                values = [[panel[m][c]["rate"] if panel[m][c]["rate"] is not None else float("nan")
                           for c in cells] for m in models]
                cmap = plt.get_cmap("viridis").copy()
                cmap.set_bad("#e5e7eb")
                shown = ax.imshow(values, vmin=0, vmax=1, cmap=cmap, aspect="auto")
                for y, model in enumerate(models):
                    for x, cell in enumerate(cells):
                        v = panel[model][cell]
                        label = (f"{v['positive']}/{v['labeled']}\nmissing {v['missing']}/{v['planned']}"
                                 if v["planned"] else "Not selected")
                        ax.text(x, y, label, ha="center", va="center", fontsize=9,
                                color="white" if v["rate"] is not None and v["rate"] < .5 else "black")
                ax.set(xticks=range(len(cells)), xticklabels=cells, yticks=range(len(models)),
                       yticklabels=[m.title() for m in models], title=f"{phase.title()}: {judge.title()} inclusive attribution",
                       xlabel="Retained instruction / transcript cell", ylabel="Response model")
                fig.colorbar(shown, ax=ax, label="Positive / labeled", fraction=.035, pad=.04)
                fig.subplots_adjust(bottom=.25, left=.14, right=.89, top=.88)
                fig.text(.5, .06, "Cells show positives/labeled and missing/planned; missing labels are excluded from rates.\n"
                         "S = self-reference; H = history; N = neutral; SHAM = independent same-condition donor.\n"
                         "Automated labels, not validated experience reports. Unrun cells are not zero effects.",
                         ha="center", fontsize=8)
                for extension in ("png", "pdf"):
                    fig.savefig(root / f"{name}.{extension}", dpi=160)
            finally:
                plt.close(fig)
    _write(root / "FIGURE_COUNTS.json", counts)


def verify(destination):
    """Read-only exact-inventory, byte-hash and executable receipt audit."""
    root = Path(destination).absolute()
    manifest = _load(root / "MANIFEST.json")
    if set(manifest) != {"schema", "files"} or manifest["schema"] != "openrouter-swap-manifest-v1":
        raise ValueError("Invalid manifest")
    if manifest["files"] != _inventory(root):
        raise ValueError("Release inventory or hash mismatch")
    metadata, rows, plan = _replay(root)
    if _load(root / "RELEASE.json") != metadata:
        raise ValueError("Release audit does not reconstruct")
    counts = {f"{phase}_{judge}_inclusive": cell_counts(items, plan["models"],
              list(protocol.CELLS)[:4] if phase == "screen" else protocol.CELLS, judge)
              for phase, items in rows.items() for judge in ("astra", "opus")}
    if _load(root / "FIGURE_COUNTS.json") != counts:
        raise ValueError("Figure counts do not reconstruct")
    return {"pass": True, "status": metadata["status"], "files": len(manifest["files"])}


def build(run_dir, destination):
    """Copy only explicit public artifacts; never replace an existing release."""
    source, target = Path(run_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source)
    _no_symlinks(target)
    if target.exists():
        raise FileExistsError("Release destination already exists")
    sources = {"runtime.json": source / "runtime.json", "raw/events.jsonl.gz": source / "raw/events.jsonl"}
    sources["PLAN.json"] = protocol.ROOT / protocol.PLAN
    for name in ("fixture_gate.json", "main_admission.json"):
        if (source / name).exists() or (source / name).is_symlink():
            sources[name] = source / name
    snapshots = [p for p in (source / "snapshots").glob("*") if p.name.isdecimal()]
    if snapshots:
        latest = max(snapshots, key=lambda p: int(p.name))
        _no_symlinks(latest)
        sources.update({p.relative_to(source).as_posix(): p for p in latest.glob("*.json")})
    with TemporaryDirectory() as temporary:
        root = Path(temporary).resolve() / "bundle"
        root.mkdir()
        for name, path in sources.items():
            _no_symlinks(path)
            output = root / name
            output.parent.mkdir(parents=True, exist_ok=True)
            if name == "raw/events.jsonl.gz":
                with path.open("rb") as handle, output.open("xb") as compressed:
                    with gzip.GzipFile(filename="", fileobj=compressed, mode="wb", mtime=0) as archive:
                        shutil.copyfileobj(handle, archive)
            else:
                shutil.copyfile(path, output)
        metadata, rows, plan = _replay(root)
        _write(root / "RELEASE.json", metadata)
        _figures(root, rows, plan)
        _write(root / "MANIFEST.json", {"schema": "openrouter-swap-manifest-v1", "files": _inventory(root)})
        result = verify(root)
        shutil.copytree(root, target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify and not args.run_dir:
        parser.error("Building requires --run-dir")
    try:
        result = verify(args.destination) if args.verify else build(args.run_dir, args.destination)
    except (ValueError, OSError, EOFError, Halted, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Release operation failed ({type(error).__name__}); original artifacts retained.\n")
    print(protocol.canonical(result))


if __name__ == "__main__":
    main()
