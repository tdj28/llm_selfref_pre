from experiments.berg_ensemble_diagnostics import figures


def test_both_judges_all_panels_generate_figure_pairs(tmp_path):
    summary = {}
    for judge in ("paper","notebook"):
        summary[judge] = {f:{"estimate_complete_pairs":0.,"exact_marginal95":[-.2,.2],
                            "suppression":{"rate":.5},"amplification":{"rate":.5}}
                          for f in ("target","control-1","control-2","control-3")}
        summary[judge]["zero"] = {"rate":.5}
    summary["notebook"]["control-2"]["estimate_complete_pairs"] = None
    summary["notebook"]["control-3"].update(estimate_complete_pairs=.9,exact_marginal95=[-.5,.5])
    figures(summary,tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "aggregate_effects.png","aggregate_effects.pdf","aggregate_rates.png","aggregate_rates.pdf"}
    assert all(p.stat().st_size > 1000 for p in tmp_path.iterdir())
