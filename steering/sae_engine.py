"""
sae_engine.py - SAE loading, profiling, and steering engine

This module handles:
- Loading Goodfire SAEs from HuggingFace
- Loading Llama models with nnsight
- Profiling feature activations
- Applying steering interventions during generation
"""

import gc
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, asdict

import torch
import torch.nn as nn
from tqdm import tqdm

from config import ModelConfig, SAEConfig


# =============================================================================
# MEMORY MANAGEMENT
# =============================================================================

def get_gpu_memory_info() -> Dict[str, float]:
    """Get current GPU memory usage in GB."""
    if not torch.cuda.is_available():
        return {"allocated": 0, "reserved": 0, "free": 0, "total": 0}

    allocated = torch.cuda.memory_allocated() / 1e9
    reserved = torch.cuda.memory_reserved() / 1e9
    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    free = total - reserved

    return {
        "allocated": allocated,
        "reserved": reserved,
        "free": free,
        "total": total,
    }


def log_memory(label: str):
    """Log GPU memory usage with a label."""
    if not torch.cuda.is_available():
        return

    info = get_gpu_memory_info()
    print(f"[MEM] {label:40s} | Alloc: {info['allocated']:6.2f}GB | "
          f"Rsrvd: {info['reserved']:6.2f}GB | Free: {info['free']:6.2f}GB")


def force_cleanup():
    """Force garbage collection and CUDA cache clearing."""
    for _ in range(3):
        gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()


# =============================================================================
# SAE CLASS (Sparse Autoencoder)
# =============================================================================

class SparseAutoencoder(nn.Module):
    """
    Sparse Autoencoder for interpreting model activations.
    
    Matches Goodfire's SAE format which uses standard nn.Linear layers:
    - encoder_linear: Linear(d_model -> d_sae) + ReLU
    - decoder_linear: Linear(d_sae -> d_model)

    Architecture:
        encode: h -> ReLU(encoder_linear(h))
        decode: f -> decoder_linear(f)
    """

    def __init__(
        self,
        d_model: int,
        d_sae: int,
        device: str = "cpu",
        dtype: torch.dtype = torch.float16,
    ):
        super().__init__()
        self.d_model = d_model
        self.d_sae = d_sae

        # Goodfire's format uses standard Linear layers
        self.encoder_linear = nn.Linear(d_model, d_sae)
        self.decoder_linear = nn.Linear(d_sae, d_model)
        
        self.to(device=device, dtype=dtype)

    def encode(self, h: torch.Tensor) -> torch.Tensor:
        """
        Encode hidden states to sparse features.

        Args:
            h: Hidden states [..., d_model]

        Returns:
            f: Sparse feature activations [..., d_sae]
        """
        # Cast to SAE dtype to avoid MPS dtype mismatch
        h = h.to(dtype=self.encoder_linear.weight.dtype)
        return torch.relu(self.encoder_linear(h))

    def decode(self, f: torch.Tensor) -> torch.Tensor:
        """
        Decode sparse features back to hidden states.

        Args:
            f: Sparse feature activations [..., d_sae]

        Returns:
            h_reconstructed: Reconstructed hidden states [..., d_model]
        """
        f = f.to(dtype=self.decoder_linear.weight.dtype)
        return self.decoder_linear(f)

    def forward(self, h: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Full forward pass (encode then decode).

        Args:
            h: Hidden states [..., d_model]

        Returns:
            h_reconstructed: Reconstructed hidden states [..., d_model]
            f: Sparse feature activations [..., d_sae]
        """
        f = self.encode(h)
        h_reconstructed = self.decode(f)
        return h_reconstructed, f

    @classmethod
    def from_pretrained(
        cls,
        repo_id: str,
        device: str = "cpu",
        dtype: torch.dtype = torch.float16,
    ) -> 'SparseAutoencoder':
        """
        Load a pre-trained SAE from HuggingFace (Goodfire format).

        Args:
            repo_id: HuggingFace repo ID (e.g., "Goodfire/Llama-3.1-8B-Instruct-SAE-l19")
            device: Device to load on
            dtype: Data type

        Returns:
            Loaded SAE model
        """
        from huggingface_hub import hf_hub_download

        print(f"Downloading SAE from {repo_id}...")
        # Goodfire SAEs use .pth extension
        sae_name = repo_id.split('/')[-1]
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=f"{sae_name}.pth",
        )

        print(f"Loading SAE weights from {local_path}...")
        # Load to CPU first, then move to device
        state_dict = torch.load(local_path, map_location="cpu", weights_only=True)

        # Infer dimensions from weights
        # Goodfire format: encoder_linear.weight is (d_sae, d_model)
        d_sae = state_dict["encoder_linear.weight"].shape[0]
        d_model = state_dict["encoder_linear.weight"].shape[1]

        print(f"Creating SAE: d_model={d_model}, d_sae={d_sae}")
        sae = cls(d_model=d_model, d_sae=d_sae, device="cpu", dtype=dtype)
        
        # Convert weights to target dtype before loading
        for key in state_dict:
            if state_dict[key].dtype in [torch.bfloat16, torch.float32, torch.float16]:
                state_dict[key] = state_dict[key].to(dtype)
        
        sae.load_state_dict(state_dict)
        sae.to(device=device)
        sae.eval()

        print(f"SAE loaded: d_model={d_model}, d_sae={d_sae}")
        return sae

    def get_decoder_directions(self) -> torch.Tensor:
        """Get decoder weight matrix for steering (d_model, d_sae)."""
        # decoder_linear.weight is (d_model, d_sae) for Linear(d_sae -> d_model)
        return self.decoder_linear.weight

    def get_feature_norms(self) -> torch.Tensor:
        """Get the L2 norms of decoder directions."""
        return torch.norm(self.decoder_linear.weight, dim=0)


# =============================================================================
# MODEL LOADER
# =============================================================================

class SAEModelWrapper:
    """
    Wrapper for a language model with SAE steering capabilities.

    Uses nnsight for activation interventions.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        sae_config: SAEConfig,
    ):
        self.model_config = model_config
        self.sae_config = sae_config

        self.model = None
        self.sae = None
        self.tokenizer = None

        self._load_model()
        self._load_sae()

    def _load_model(self):
        """Load the base language model with nnsight."""
        try:
            from nnsight import LanguageModel
        except ImportError:
            raise ImportError("nnsight not installed. Run: pip install nnsight==0.3.0")

        print(f"Loading model: {self.model_config.model_name}")
        print(f"  Device: {self.model_config.device}")
        log_memory("Before model load")

        # Device-specific loading
        device = self.model_config.device
        
        if device == "mps":
            # MPS requires different loading - no device_map, load to device after
            print("  Using MPS (Apple Silicon) - loading with auto device_map then moving")
            self.model = LanguageModel(
                self.model_config.model_name,
                device_map="auto",  # Let HuggingFace handle initial placement
                torch_dtype=getattr(torch, self.model_config.dtype),
                dispatch=True,
            )
        elif device == "cpu":
            print("  Using CPU - this will be slow!")
            self.model = LanguageModel(
                self.model_config.model_name,
                device_map="cpu",
                torch_dtype=torch.float32,  # CPU often needs float32
                dispatch=True,
            )
        else:
            # CUDA - standard loading
            self.model = LanguageModel(
                self.model_config.model_name,
                device_map=device,
                torch_dtype=getattr(torch, self.model_config.dtype),
                dispatch=True,
            )

        self.tokenizer = self.model.tokenizer

        log_memory("After model load")
        print(f"Model loaded: {self.model_config.model_name}")

    def _load_sae(self):
        """Load the SAE for the current model."""
        repo_id = self.sae_config.get_repo(self.model_config.model_size)

        print(f"Loading SAE: {repo_id}")
        log_memory("Before SAE load")

        self.sae = SparseAutoencoder.from_pretrained(
            repo_id=repo_id,
            device=self.model_config.device,
            dtype=getattr(torch, self.model_config.dtype),
        )

        log_memory("After SAE load")
        print(f"SAE loaded from {repo_id}")

    def get_layer_hook_name(self) -> str:
        """Get the layer hook name for interventions."""
        layer_idx = self.sae_config.get_layer(self.model_config.model_size)
        return f"model.layers.{layer_idx}"

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 100,
        temperature: float = 0.7,
        steering_vectors: Optional[Dict[int, float]] = None,
    ) -> str:
        """
        Generate text with optional SAE steering.

        Args:
            prompt: Input prompt
            max_new_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            steering_vectors: Dict mapping feature indices to steering strengths
                             e.g., {12: 0.5, 34: -0.3} means add 0.5 * d_12 - 0.3 * d_34

        Returns:
            Generated text
        """
        # Tokenize
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model_config.device)

        # Get underlying HuggingFace model (nnsight wraps it)
        hf_model = self.model._model if hasattr(self.model, '_model') else self.model
        
        if steering_vectors is None or len(steering_vectors) == 0:
            # No steering - vanilla generation
            with torch.no_grad():
                outputs = hf_model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=(temperature > 0),
                )
            return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        else:
            # Steering - use nnsight intervention
            return self._generate_with_steering(
                inputs=inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                steering_vectors=steering_vectors,
            )

    def _generate_with_steering(
        self,
        inputs: Dict,
        max_new_tokens: int,
        temperature: float,
        steering_vectors: Dict[int, float],
    ) -> str:
        """
        Generate with SAE steering using nnsight hooks.

        This applies steering by adding weighted SAE decoder directions to activations.
        """
        # Compute steering vector (sum of weighted decoder columns)
        # Get decoder weight matrix for steering directions
        decoder_weight = self.sae.get_decoder_directions()  # (d_model, d_sae)
        steering_vec = torch.zeros(self.sae.d_model, device=decoder_weight.device, dtype=decoder_weight.dtype)

        for feature_idx, weight in steering_vectors.items():
            # Add weighted decoder direction
            steering_vec += weight * decoder_weight[:, feature_idx]

        # Define hook for intervention
        layer_name = self.get_layer_hook_name()

        def steering_hook(module, input_tensor, output_tensor):
            """Hook to add steering vector to layer output."""
            # output_tensor is (batch, seq, d_model)
            # Add steering vector to all positions
            return output_tensor + steering_vec.unsqueeze(0).unsqueeze(0)

        # Apply hook and generate
        # Get underlying HuggingFace model (nnsight wraps it)
        hf_model = self.model._model if hasattr(self.model, '_model') else self.model
        
        with torch.no_grad():
            layer = dict(hf_model.named_modules())[layer_name]
            handle = layer.register_forward_hook(steering_hook)

            try:
                outputs = hf_model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=(temperature > 0),
                )
            finally:
                handle.remove()

        return self.tokenizer.decode(outputs[0], skip_special_tokens=True)

    def profile_activations(
        self,
        prompts: List[str],
        progress_bar: bool = True,
    ) -> torch.Tensor:
        """
        Profile SAE feature activations on a list of prompts.

        Args:
            prompts: List of text prompts
            progress_bar: Show progress bar

        Returns:
            activation_matrix: (n_prompts, d_sae) tensor of mean activations
        """
        activations = []
        iterator = tqdm(prompts, desc="Profiling activations") if progress_bar else prompts

        layer_name = self.get_layer_hook_name()

        for prompt in iterator:
            with torch.no_grad():
                # Tokenize
                inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model_config.device)

                # Forward pass with hook to extract activations
                activation_holder = []

                def extract_hook(module, input_tensor, output_tensor):
                    """Hook to extract and encode activations."""
                    # output_tensor: (batch, seq, d_model)
                    h = output_tensor[0]  # (seq, d_model)
                    f = self.sae.encode(h)  # (seq, d_sae)
                    activation_holder.append(f.mean(dim=0).cpu())  # Average over sequence

                # Register hook on the underlying HuggingFace model (nnsight wraps it)
                hf_model = self.model._model if hasattr(self.model, '_model') else self.model
                layer = dict(hf_model.named_modules())[layer_name]
                handle = layer.register_forward_hook(extract_hook)

                try:
                    # Forward pass through underlying HuggingFace model
                    _ = hf_model(**inputs)
                finally:
                    handle.remove()

                activations.append(activation_holder[0])

        # Stack into matrix
        activation_matrix = torch.stack(activations)  # (n_prompts, d_sae)

        return activation_matrix

    def compute_feature_contrast(
        self,
        positive_prompts: List[str],
        negative_prompts: List[str],
    ) -> torch.Tensor:
        """
        Compute feature activation contrast between two sets of prompts.

        Args:
            positive_prompts: Prompts for positive pole
            negative_prompts: Prompts for negative pole

        Returns:
            contrast: (d_sae,) tensor of contrast scores (positive - negative)
        """
        print(f"Profiling {len(positive_prompts)} positive prompts...")
        positive_activations = self.profile_activations(positive_prompts)

        print(f"Profiling {len(negative_prompts)} negative prompts...")
        negative_activations = self.profile_activations(negative_prompts)

        # Compute mean activations
        positive_mean = positive_activations.mean(dim=0)
        negative_mean = negative_activations.mean(dim=0)

        # Contrast
        contrast = positive_mean - negative_mean

        return contrast

    def cleanup(self):
        """Clean up model and SAE to free memory."""
        del self.model
        del self.sae
        del self.tokenizer
        self.model = None
        self.sae = None
        self.tokenizer = None
        force_cleanup()


# =============================================================================
# FEATURE CACHE (to avoid re-profiling)
# =============================================================================

@dataclass
class FeatureCache:
    """Cache for computed feature contrasts."""

    concept_name: str
    model_size: str
    layer: int
    positive_prompts: List[str]
    negative_prompts: List[str]
    contrast: List[float]  # Store as list for JSON serialization
    top_features: List[int]  # Top-K feature indices
    timestamp: str

    def save(self, path: Path):
        """Save cache to JSON."""
        with open(path, 'w') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> 'FeatureCache':
        """Load cache from JSON."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls(**data)


def save_feature_contrast(
    concept_name: str,
    model_size: str,
    layer: int,
    positive_prompts: List[str],
    negative_prompts: List[str],
    contrast: torch.Tensor,
    top_k: int,
    cache_dir: Path,
):
    """Save feature contrast to cache."""
    from datetime import datetime

    # Get top-K features
    top_features = contrast.topk(top_k).indices.tolist()

    cache = FeatureCache(
        concept_name=concept_name,
        model_size=model_size,
        layer=layer,
        positive_prompts=positive_prompts,
        negative_prompts=negative_prompts,
        contrast=contrast.tolist(),
        top_features=top_features,
        timestamp=datetime.now().isoformat(),
    )

    cache_path = cache_dir / f"{concept_name}_{model_size}_l{layer}.json"
    cache.save(cache_path)
    print(f"Feature contrast cached to {cache_path}")


def load_feature_contrast(
    concept_name: str,
    model_size: str,
    layer: int,
    cache_dir: Path,
) -> Optional[FeatureCache]:
    """Load feature contrast from cache if it exists."""
    cache_path = cache_dir / f"{concept_name}_{model_size}_l{layer}.json"

    if not cache_path.exists():
        return None

    cache = FeatureCache.load(cache_path)
    print(f"Loaded cached feature contrast from {cache_path}")
    return cache
