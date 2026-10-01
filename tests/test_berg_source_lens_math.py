"""Independent small-matrix arithmetic for the declared FP32 readout."""
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")
from experiments.berg_source_replication.backend import Lens


def test_nonsymmetric_transport_and_signed_permutation_against_scalar_sums():
    lens = Lens.__new__(Lens)
    lens.backend = SimpleNamespace(device=torch.device("cpu"))
    matrix = [[1., 2., 0., -1.], [0., 3., 1., 2.], [2., 0., 4., 1.], [1., 0., 2., 5.]]
    weights = [[2., -1., 1., 0.], [0., 1., -2., 3.]]
    norm_weights = [1., .5, 2., 1.5]
    h = [1., 3., 2., -1.]
    lens.matrices = {50: torch.tensor(matrix)}
    lens.weight = torch.tensor(weights)
    lens.norm_weight = torch.tensor(norm_weights)
    lens.eps = .1
    lens.groups = {"test": [0, 1]}
    lens.seeds = [7]
    ip, ins, op, outs = [3, 0, 2, 1], [1., -1., 1., -1.], [2, 3, 0, 1], [-1., 1., 1., -1.]
    lens.random = {(50, 7): [(torch.tensor(ip), torch.tensor(ins)), (torch.tensor(op), torch.tensor(outs))]}
    result = lens.read(torch.tensor(h), 50)
    def multiply(v):
        return [sum(row[k]*v[k] for k in range(4)) for row in matrix]
    random = multiply([h[ip[k]]*ins[k] for k in range(4)])
    expected = {"identity": h, "jacobian": multiply(h),
                "random_j_1": [random[op[k]]*outs[k] for k in range(4)]}
    for name, values in expected.items():
        scale = (sum(v*v for v in values)/4 + .1)**-.5
        normalized = [values[k]*scale*norm_weights[k] for k in range(4)]
        logits = [sum(w[k]*normalized[k] for k in range(4)) for w in weights]
        linear = [sum(w[k]*values[k] for k in range(4)) for w in weights]
        assert result[name]["token_logits"] == pytest.approx(logits, rel=1e-5, abs=1e-6)
        assert result[name]["linear_token_logits"] == pytest.approx(linear)
        assert result[name]["groups"]["test"] == pytest.approx(sum(logits)/2, rel=1e-5)
        assert result[name]["transport_norm"] == pytest.approx(sum(v*v for v in values)**.5)
