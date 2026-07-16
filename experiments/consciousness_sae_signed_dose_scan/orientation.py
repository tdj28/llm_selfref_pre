"""Study-bound facade over the proven target-free J-orientation checks."""

from __future__ import annotations

from typing import Any

from experiments.consciousness_sae_target_blind_calibration import (
    orientation as _impl,
)

from . import protocol


OrientationError = _impl.OrientationError


def _bind() -> None:
    _impl.protocol = protocol
    # The predecessor materialized these values at import time. Rebind all of
    # them so no predecessor seed namespace can leak into this fresh study.
    _impl.FIXTURE_COUNT = int(protocol.J_ORIENTATION_SPEC["fixture_count_per_layer"])
    _impl.SEED_NAMESPACE = str(
        protocol.J_ORIENTATION_SPEC["fixture_seed_namespace"]
    )
    _impl.EXPECTED_ROW_COUNT = len(protocol.J_LAYERS) * _impl.FIXTURE_COUNT


def execute(*args: Any, **kwargs: Any) -> Any:
    _bind()
    return _impl.execute(*args, **kwargs)


def validate(*args: Any, **kwargs: Any) -> Any:
    _bind()
    return _impl.validate(*args, **kwargs)
