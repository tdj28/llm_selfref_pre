"""Reuse native additive hooks, replacing only vector construction."""
import math
import torch

from experiments.berg_source_replication.backend import Backend as SourceBackend
from experiments.sae_assay_diagnostic.backend import _ids


class Backend(SourceBackend):
    def vector(self, intervention):
        # The inherited true-zero qualification uses the original scalar schema.
        if intervention is None or set(intervention) == {"feature_ids", "coefficient"}:
            if intervention is not None and intervention["coefficient"] != 0:
                raise ValueError("Scalar nonzero edits are not ensemble treatments")
            return super().vector(intervention)
        if set(intervention) != {"feature_ids", "coefficient", "weights"}:
            raise ValueError("Unknown weighted intervention fields")
        ids = _ids(intervention["feature_ids"], self._sae[0].shape[0])
        weights, sign = intervention["weights"], intervention["coefficient"]
        if (isinstance(sign, bool) or sign not in (-1, 0, 1) or len(weights) != len(ids)
                or any(isinstance(w, bool) or not isinstance(w, (float, int)) or not math.isfinite(w)
                       or (w != 0 if sign == 0 else not .4 <= sign*w <= .6) for w in weights)):
            raise ValueError("Weights outside frozen signed range")
        w = torch.tensor(weights, device=self.device, dtype=torch.float32)
        return (self._sae[2][:, list(ids)].float() * w).sum(1)

    def _telemetry(self, ids, batches, intervention=None):
        result = super()._telemetry(ids, batches, intervention)
        if intervention is not None and "weights" in intervention:
            result["weights"] = list(intervention["weights"])
            result["coefficient_semantics"] = "sign_only_see_per_feature_weights"
        return result
