"""Reuse the frozen 512-token generator, including its unmodified cap flags."""
from experiments.berg_dose_window.backend import Backend as WindowBackend


class Backend(WindowBackend):
    pass
