"""
config.py - Configuration system for SAE steering experiments

This module defines all experimental parameters for reproducibility and easy tuning.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Literal
import json
import torch


def get_default_device() -> str:
    """Auto-detect the best available device."""
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"


@dataclass
class ModelConfig:
    """Configuration for the target model being steered."""

    # Model selection
    model_name: str = "meta-llama/Llama-3.3-70B-Instruct"
    model_size: Literal["8b", "70b"] = "70b"

    # Hardware
    device: str = field(default_factory=get_default_device)
    dtype: str = "float16"  # or "bfloat16", "float32"
    use_quantization: bool = False  # 8-bit/4-bit quantization
    quantization_bits: int = 8

    # Generation parameters
    max_new_tokens: int = 100
    temperature: float = 0.7
    top_p: float = 0.9

    def __post_init__(self):
        if self.model_size == "8b":
            self.model_name = "meta-llama/Meta-Llama-3.1-8B-Instruct"


@dataclass
class SAEConfig:
    """Configuration for Sparse Autoencoder."""

    # SAE selection (Goodfire SAEs)
    sae_repo_8b: str = "Goodfire/Llama-3.1-8B-Instruct-SAE-l19"
    sae_repo_70b: str = "Goodfire/Llama-3.3-70B-Instruct-SAE-l50"

    # Layer to intervene at
    layer_8b: int = 19
    layer_70b: int = 50

    # SAE dimensions
    expansion_factor_8b: int = 16  # 65,536 features
    expansion_factor_70b: int = 8

    # Feature selection parameters
    num_features_to_steer: int = 10  # Number of top features to use for steering

    def get_repo(self, model_size: str) -> str:
        return self.sae_repo_8b if model_size == "8b" else self.sae_repo_70b

    def get_layer(self, model_size: str) -> int:
        return self.layer_8b if model_size == "8b" else self.layer_70b


@dataclass
class TriangulationConfig:
    """Configuration for prompt triangulation feature selection."""

    # Feature selection strategy
    method: Literal[
        "top_k",           # Simple top-K by contrast
        "intersection",    # Intersection across categories
        "stability",       # Bootstrap stability selection
        "holdout",         # Leave-one-out validation
    ] = "intersection"

    # Top-K parameters
    top_k: int = 50  # Number of features to consider per category

    # Intersection parameters
    min_categories: int = 3  # Minimum categories a feature must appear in

    # Stability selection parameters
    n_bootstrap: int = 100
    stability_threshold: float = 0.7  # Fraction of bootstraps feature must appear in

    # Number of prompts per pole
    prompts_per_pole: int = 5


@dataclass
class ExperimentConfig:
    """Configuration for individual experiments."""

    # Trials and sampling
    n_trials: int = 20  # Trials per condition
    seed: int = 42

    # Steering parameters
    steering_values: List[float] = field(default_factory=lambda: [-1.0, -0.5, 0.0, 0.5, 1.0])

    # Feature ablation
    test_individual_features: bool = True  # Test each feature one by one
    test_aggregate: bool = True  # Test all features together

    # Output
    save_responses: bool = True  # Save full model responses
    save_activations: bool = False  # Save activation patterns (large!)


@dataclass
class JudgeConfig:
    """Configuration for LLM judges."""

    # Judge models
    judge_provider: Literal["openai", "anthropic"] = "anthropic"
    judge_model_openai: str = "gpt-4o"
    judge_model_anthropic: str = "claude-sonnet-4"

    # Evaluation parameters
    temperature: float = 0.0  # Deterministic judging
    max_retries: int = 3

    # Rubric settings
    use_likert_scale: bool = True  # Use 1-7 scale instead of binary
    include_reasoning: bool = True  # Ask judge to explain rating

    def get_model(self) -> str:
        if self.judge_provider == "openai":
            return self.judge_model_openai
        else:
            return self.judge_model_anthropic


@dataclass
class OutputConfig:
    """Configuration for output and logging."""

    # Directories
    base_dir: Path = Path("../out/sae_steering")
    results_dir: Path = field(init=False)
    analysis_dir: Path = field(init=False)
    cache_dir: Path = field(init=False)

    # Naming
    experiment_name: str = "sae_steering_exploration"
    timestamp: bool = True  # Add timestamp to experiment name

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    save_config: bool = True  # Save config alongside results

    # Data formats
    save_json: bool = True
    save_csv: bool = True
    save_parquet: bool = False  # More efficient for large datasets

    def __post_init__(self):
        if self.timestamp:
            from datetime import datetime
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.experiment_name = f"{self.experiment_name}_{timestamp_str}"

        self.results_dir = self.base_dir / self.experiment_name / "results"
        self.analysis_dir = self.base_dir / self.experiment_name / "analysis"
        self.cache_dir = self.base_dir / self.experiment_name / "cache"

        # Create directories
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class FullConfig:
    """Complete configuration for the experimental suite."""

    model: ModelConfig = field(default_factory=ModelConfig)
    sae: SAEConfig = field(default_factory=SAEConfig)
    triangulation: TriangulationConfig = field(default_factory=TriangulationConfig)
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def save(self, path: Optional[Path] = None):
        """Save configuration to JSON."""
        if path is None:
            path = self.output.results_dir / "config.json"

        # Convert to dict
        config_dict = {
            "model": {k: str(v) if isinstance(v, Path) else v
                     for k, v in self.model.__dict__.items()},
            "sae": {k: str(v) if isinstance(v, Path) else v
                   for k, v in self.sae.__dict__.items()},
            "triangulation": {k: str(v) if isinstance(v, Path) else v
                            for k, v in self.triangulation.__dict__.items()},
            "experiment": {k: str(v) if isinstance(v, Path) else v
                          for k, v in self.experiment.__dict__.items()},
            "judge": {k: str(v) if isinstance(v, Path) else v
                     for k, v in self.judge.__dict__.items()},
            "output": {k: str(v) if isinstance(v, Path) else v
                      for k, v in self.output.__dict__.items()},
        }

        with open(path, 'w') as f:
            json.dump(config_dict, f, indent=2)

        print(f"Configuration saved to {path}")

    @classmethod
    def load(cls, path: Path) -> 'FullConfig':
        """Load configuration from JSON."""
        with open(path, 'r') as f:
            config_dict = json.load(f)

        # Reconstruct config objects
        # Note: This is simplified - would need proper deserialization for Path objects
        return cls(
            model=ModelConfig(**config_dict.get("model", {})),
            sae=SAEConfig(**config_dict.get("sae", {})),
            triangulation=TriangulationConfig(**config_dict.get("triangulation", {})),
            experiment=ExperimentConfig(**config_dict.get("experiment", {})),
            judge=JudgeConfig(**config_dict.get("judge", {})),
            output=OutputConfig(**config_dict.get("output", {})),
        )


# Preset configurations for common use cases

def get_quick_test_config() -> FullConfig:
    """Quick test configuration (fast, low resource)."""
    return FullConfig(
        model=ModelConfig(model_size="8b", use_quantization=True),
        experiment=ExperimentConfig(
            n_trials=3,
            steering_values=[-0.5, 0.0, 0.5],
            test_individual_features=False,
        ),
        triangulation=TriangulationConfig(
            method="top_k",
            top_k=5,
        ),
    )


def get_full_experiment_config() -> FullConfig:
    """Full experimental configuration (publication-quality)."""
    return FullConfig(
        model=ModelConfig(model_size="70b"),
        experiment=ExperimentConfig(
            n_trials=50,
            steering_values=[-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0],
            test_individual_features=True,
            test_aggregate=True,
        ),
        triangulation=TriangulationConfig(
            method="intersection",
            top_k=50,
            min_categories=3,
        ),
        judge=JudgeConfig(
            judge_provider="anthropic",
            use_likert_scale=True,
            include_reasoning=True,
        ),
    )


def get_development_config() -> FullConfig:
    """Development configuration (balanced speed/thoroughness)."""
    return FullConfig(
        model=ModelConfig(model_size="8b"),
        experiment=ExperimentConfig(
            n_trials=10,
            steering_values=[-1.0, -0.5, 0.0, 0.5, 1.0],
            test_individual_features=True,
        ),
        triangulation=TriangulationConfig(
            method="intersection",
            top_k=20,
            min_categories=2,
        ),
    )
