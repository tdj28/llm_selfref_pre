"""Bounded mapping-scaled additive edits with geometry-matched control panels.

Scales are an NF4 designed-corpus mapping reference, not natural activation
peaks. Only vector construction and readout selection change: native addition,
generation, true-zero qualification and re-encoding remain source operations.
Re-encoding is an observation, not a semantic-ablation measurement.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math

import torch

from experiments.berg_source_replication.backend import Backend as SourceBackend
from experiments.operator_matching.backend import Backend as OperatorBackend
from experiments.sae_assay_diagnostic.backend import (
    _finite, _fp32_math, _ids,
)
from . import protocol


MULTIPLIER_BOUNDS = (.5, 2.)
NORM_MATCH_RTOL = 1e-5
SCALE_REFERENCE = "mapping_scaled_nf4_designed_corpus_not_natural_peak"


class Backend(SourceBackend):
    # Reuse only clean teacher-forced scoring, not operator-matching sampling.
    answer_nll = OperatorBackend.answer_nll

    def __init__(self, precision="bf16", cache_dir=None, device="cuda"):
        if precision != "bf16":
            raise ValueError("Dose ladder requires native BF16, not quantization")
        super().__init__(precision=precision, cache_dir=cache_dir, device=device)

    def _initialize(self, model, tokenizer, state, layer_index, device, metadata, precision):
        super()._initialize(model, tokenizer, state, layer_index, device, metadata, precision)
        try:
            width = self._sae[0].shape[0]
            targets = _ids(protocol.TARGET_IDS, width)
            controls = tuple(_ids(p, width) for p in protocol.CONTROL_PANELS)
            self._panels = (targets,) + controls
            self._scales, self._doses = tuple(protocol.SCALES), tuple(protocol.DOSES)
            if (len(targets) != 3 or len(controls) != 3
                    or any(len(p) != 3 for p in controls)
                    or len({i for p in self._panels for i in p}) != 12
                    or len(self._scales) != 3
                    or any(type(s) not in (int, float) or not math.isfinite(s) or s <= 0
                           for s in self._scales)
                    or self._doses != (.25, .5, .75, 1.)):
                raise ValueError("Invalid dose-ladder protocol geometry")
            self.default_feature_ids = targets
            # Match SourceBackend.vector: resident native columns promoted to
            # FP32. Cache only twelve columns, without a new precision operator.
            decoder = self._sae[2]
            self._columns = tuple(decoder[:, list(p)].to(device=device, dtype=torch.float32)
                                  .contiguous().clone() for p in self._panels)
            self._build_geometry(decoder.dtype)
        except Exception:
            self.close()
            raise

    @torch.inference_mode()
    def _build_geometry(self, source_dtype):
        """Pre-outcome checks for every panel/dose; no model forward or labels."""
        self._vectors, panels = {}, []
        with _fp32_math(self.device):
            weights = torch.tensor(self._scales, device=self.device, dtype=torch.float32)
            _finite("mapping scales", weights)
            bases = [(columns * weights).sum(1) for columns in self._columns]
            norms = [torch.linalg.vector_norm(v) for v in bases]
            for norm in norms:
                if not torch.isfinite(norm) or norm.item() <= 0:
                    raise ValueError("Zero or nonfinite aggregate decoder norm")
            for index, (ids, columns, norm) in enumerate(zip(self._panels, self._columns, norms)):
                _finite("FP32 decoder columns", columns)
                gram = columns.T @ columns
                _finite("decoder Gram matrix", gram)
                gram_norm = torch.sqrt(weights @ gram @ weights).item()
                if not math.isfinite(gram_norm) or not math.isclose(
                        gram_norm, norm.item(), rel_tol=NORM_MATCH_RTOL, abs_tol=0.):
                    raise ValueError("Gram and aggregate vector norm mismatch")
                multiplier = (norms[0] / norm).item()
                if not MULTIPLIER_BOUNDS[0] <= multiplier <= MULTIPLIER_BOUNDS[1]:
                    raise ValueError("Aggregate normalization multiplier outside bounds")
                doses = []
                for dose in self._doses:
                    nominal = torch.tensor([dose * s for s in self._scales],
                                           device=self.device, dtype=torch.float32)
                    actual = nominal * multiplier
                    # One scalar normalizes the aggregate, never individual columns.
                    vector = (columns * nominal).sum(1) * multiplier
                    target = (self._columns[0] * nominal).sum(1)
                    _finite("normalized weights", actual)
                    _finite("normalized aggregate vector", vector)
                    requested_norm, target_norm = vector.norm().item(), target.norm().item()
                    error = abs(requested_norm - target_norm)
                    matched = (target_norm > 0 and math.isfinite(requested_norm)
                               and math.isclose(requested_norm, target_norm,
                                                rel_tol=NORM_MATCH_RTOL, abs_tol=0.))
                    if not matched:
                        raise ValueError("Requested aggregate norm match failed")
                    self._vectors[index, dose] = vector
                    doses.append({"dose": dose, "nominal_weights": nominal.cpu().tolist(),
                                  "actual_weights": actual.cpu().tolist(),
                                  "target_norm": target_norm, "requested_norm": requested_norm,
                                  "absolute_norm_error": error,
                                  "relative_norm_error": error / target_norm,
                                  "norm_match": matched, "requested_norm_matched": matched})
                panels.append({"panel": "target" if index == 0 else f"control{index}",
                               "feature_ids": list(ids), "gram": gram.cpu().tolist(),
                               "gram_norm": gram_norm, "nominal_norm": norm.item(),
                               "multiplier": multiplier, "doses": doses})
        self._geometry = {"schema": "berg_dose_ladder_geometry_v1", "test_only": bool(
            self.metadata.get("test_only", False)), "scale_reference": SCALE_REFERENCE,
            "scales": list(self._scales), "doses": list(self._doses),
            "decoder_source_dtype": str(source_dtype), "arithmetic_dtype": "torch.float32",
            "decoder_source": "resident_bf16_promoted_fp32" if self.dtype == torch.bfloat16
            else "test_resident_fp32", "tf32": False,
            "sae_id": self.metadata.get("sae_id"),
            "sae_revision": self.metadata.get("sae_revision"),
            "sae_sha256": self.metadata.get("sae_sha256"),
            "normalization": "target_weighted_sum_norm/control_weighted_sum_norm",
            "vector_formula": "sum(decoder_columns * nominal_weights) * multiplier",
            "multiplier_bounds": list(MULTIPLIER_BOUNDS),
            "norm_match_rtol": NORM_MATCH_RTOL, "norm_match_atol": 0.,
            "norm_match": True, "requested_norm_matched": True, "panels": panels}

    def geometry_receipt(self):
        """Deterministic JSON-ready FP32 geometry, with no behavioral information."""
        self._assert_resident()
        return deepcopy(self._geometry)

    @torch.inference_mode()
    def qualify(self):
        result = super().qualify()
        result["geometry"] = self.geometry_receipt()
        return result

    def _spec(self, intervention):
        if intervention is None:
            return None
        if not isinstance(intervention, Mapping):
            raise ValueError("Intervention must be a mapping or None")
        fields = set(intervention)
        if fields not in ({"feature_ids", "coefficient"}, {"feature_ids", "coefficient", "weights"}):
            raise ValueError("Unknown dose-ladder intervention fields")
        if not isinstance(intervention["feature_ids"], (list, tuple)):
            raise ValueError("feature_ids must be an ordered list or tuple")
        ids = _ids(intervention["feature_ids"], self._sae[0].shape[0])
        sign = intervention["coefficient"]
        if type(sign) not in (int, float) or sign not in (-1, 0, 1):
            raise ValueError("coefficient must be sign -1, 0, or +1")
        if "weights" not in intervention:
            if sign != 0:
                raise ValueError("Only legacy scalar zero is supported")
            return None
        if ids not in self._panels:
            raise ValueError("Feature IDs must match an ordered protocol panel")
        weights = intervention["weights"]
        if (not isinstance(weights, (list, tuple)) or len(weights) != len(ids)
                or any(type(w) not in (int, float) or not math.isfinite(w) for w in weights)):
            raise ValueError("weights must be finite numbers matching feature_ids")
        index = self._panels.index(ids)
        if sign == 0:
            if any(w != 0 for w in weights):
                raise ValueError("Zero sign requires exactly zero weights")
            return index, 0, 0., list(weights)
        for dose in self._doses:
            if tuple(weights) == tuple(sign * dose * s for s in self._scales):
                return index, int(sign), dose, list(weights)
        raise ValueError("Weights must equal sign * frozen dose * mapping scales")

    @torch.inference_mode()
    def vector(self, intervention):
        self._assert_resident()
        spec = self._spec(intervention)
        if spec is None or spec[1] == 0:
            return torch.zeros(self.model.config.hidden_size, device=self.device, dtype=torch.float32)
        index, sign, dose, _ = spec
        vector = self._vectors[index, dose] * sign
        _finite("additive vector", vector)
        return vector

    def _readout_ids(self, feature_ids):
        ids = _ids(feature_ids, self._sae[0].shape[0])
        return tuple(dict.fromkeys(self._panels[0] + ids))

    def _forward(self, token_ids, feature_ids, intervention=None, **kwargs):
        # The inherited hook uses intervention independently of readout IDs.
        return super()._forward(token_ids, self._readout_ids(feature_ids), intervention, **kwargs)

    def _telemetry(self, ids, batches, intervention=None):
        result = super()._telemetry(ids, batches, intervention)
        result["readout_feature_ids"] = list(self._readout_ids(ids))
        result["reencoding_interpretation"] = "native_coordinate_observation_not_semantic_ablation"
        spec = self._spec(intervention)
        if spec is not None:
            index, sign, dose, nominal = spec
            panel = self._geometry["panels"][index]
            row = next((r for r in panel["doses"] if r["dose"] == dose), None)
            result.update({"schema": "berg_dose_ladder_additive_v1", "weights": nominal,
                "nominal_weights": nominal, "actual_weights": [sign * w for w in row["actual_weights"]]
                if row else [0.] * len(nominal), "dose": dose, "panel": panel["panel"],
                "coefficient_semantics": "sign_only_see_per_feature_weights",
                "scale_reference": SCALE_REFERENCE, "normalization": {
                    "method": self._geometry["normalization"], "multiplier": panel["multiplier"],
                    "nominal_unit_norm": panel["nominal_norm"],
                    "target_unit_norm": self._geometry["panels"][0]["nominal_norm"],
                    "requested_norm": row["requested_norm"] if row else 0.,
                    "target_norm": row["target_norm"] if row else 0.,
                    "relative_norm_error": row["relative_norm_error"] if row else 0.,
                    "norm_match": True, "requested_norm_matched": True,
                    "norm_match_rtol": NORM_MATCH_RTOL,
                    "norm_match_atol": 0., "multiplier_bounds": list(MULTIPLIER_BOUNDS)}})
        return result

    def close(self):
        self._columns, self._vectors = (), {}
        super().close()
