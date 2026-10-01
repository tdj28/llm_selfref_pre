import csv
import itertools
import json

import pytest

from experiments.berg_source_figures import figures
from experiments.berg_source_replication.protocol import DEFAULT_SEEDS


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def test_complete_bridge_and_activation_figures(tmp_path):
    root, secondary = tmp_path/"raw", tmp_path/"secondary"
    curves = []
    for judge,p,t,c in itertools.product(("notebook","paper"),("notebook","paper"),(.5,.6),(128,256)):
        curves.append(dict(judge=judge, family="feature-30032" if (p,t,c)==("notebook",.6,128) else "baseline-bridge",
                           coefficient=0,prompt=p,temperature=t,cap=c,positives=4,valid=9,missing=1,rate=4/9))
    write(root/"analysis/curves.csv",curves)
    rows = [dict(id=f"feature-{f}-{s}-{d:+.1f}-notebook-0.6-128",feature_id=f,
                 family=f"feature-{f}",coefficient=d,turn=2,phase=p,seed=s,before_mean=0,after_mean=max(d,0))
            for f,d,p,s in itertools.product((30032,58667,22004,30686,41533,23893),(-.7,.7),("prompt","generated"),DEFAULT_SEEDS)]
    (root/"rows").mkdir()
    for r in rows:
        (root/"rows"/(r["id"]+".json")).write_text(json.dumps({"id":r["id"],
            "spec":{"feature_ids":[r["feature_id"]]},"turns":[{}, {"output_tokens":2}]}))
    write(secondary/"activation_changes.csv",rows)
    assert len(figures(root,secondary,tmp_path/"figures")) == 4
    with pytest.raises(FileExistsError): figures(root,secondary,tmp_path/"figures")
    write(secondary/"activation_changes.csv",rows[1:])
    with pytest.raises(ValueError,match="activation cases"):
        figures(root,secondary,tmp_path/"missing")
    rows[0]["feature_id"] = 1
    write(secondary/"activation_changes.csv",rows)
    with pytest.raises(ValueError,match="activation cases"):
        figures(root,secondary,tmp_path/"wrong-coordinate")
    curves.append(curves[0])
    write(root/"analysis/curves.csv",curves)
    with pytest.raises(ValueError,match="baseline cell"):
        figures(root,secondary,tmp_path/"bad")
