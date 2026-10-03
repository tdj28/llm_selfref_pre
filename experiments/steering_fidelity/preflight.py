"""Free BF16 rounding check on released states, not SAE behavioral evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

from .protocol import ROOT, DELIVERY, canonical, sha


def run():
    import torch
    from safetensors.torch import load_file
    from experiments.berg_source_replication.backend import additive
    torch.set_num_threads(1)
    root = ROOT / "data/sae_assay_repair/coordinate_delivery_20260930/residuals"
    files = sorted(root.glob("*.safetensors"))
    chosen = [files[int(i * (len(files) - 1) / 11)] for i in range(12)]
    states = [(path, load_file(str(path))["hidden"]) for path in chosen]
    reference = statistics.median(v for _, h in states for v in h.float().norm(dim=-1).flatten().tolist())
    generator = torch.Generator().manual_seed(2026100201)
    directions = torch.randn(4, 8192, generator=generator)
    directions = directions / directions.norm(dim=-1, keepdim=True)
    rows = []
    for rho in (.04, .075, .15, .30, .60):
        cosines, errors, norm_errors = [], [], []
        for _, hidden in states:
            for vector in directions:
                for sign in (-1, 1):
                    _, m = additive(hidden, vector * sign * reference * rho)
                    cosines.extend(m["cosine"].flatten().tolist())
                    errors.extend(m["relative_error"].flatten().tolist())
                    norm_errors.extend(((m["realized_norm"] - m["requested_norm"]).abs()
                                        / m["requested_norm"]).flatten().tolist())
        passed = sum(c >= DELIVERY["cosine_min"] and e <= DELIVERY["relative_error_max"]
                     and n <= DELIVERY["norm_relative_error_max"]
                     for c, e, n in zip(cosines, errors, norm_errors))
        rows.append({"rho": rho, "positions_including_specials": len(errors),
                     "pass_fraction": passed / len(errors), "cosine_min": min(cosines),
                     "relative_error_max": max(errors), "norm_relative_error_max": max(norm_errors)})
    return {"schema": "bf16_rounding_feasibility_v1", "paid_calls": 0,
            "source_states": {p.relative_to(ROOT).as_posix(): sha(p) for p, _ in states},
            "reference_median_norm_including_specials": reference, "delivery_rule": DELIVERY,
            "directions": "four seeded isotropic synthetic directions; not SAE decoder vectors",
            "scope": "rounding feasibility only; no outcome or semantic suppression evidence",
            "rows": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = run()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("x") as handle:
        handle.write(canonical(result) + "\n")
    print(json.dumps(result["rows"], indent=2))
