#!/usr/bin/env python3
"""
Run SAE Experiment on Modal (serverless GPU).

Usage:
    pip install modal
    modal token new  # First time only
    modal run run_on_modal.py

This will:
1. Spin up an A100 GPU
2. Install dependencies
3. Run the experiment
4. Save results locally
5. Shut down automatically (you only pay for what you use)
"""

import modal

# Define the container image with all dependencies
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "torch>=2.0",
    "transformers>=4.40",
    "nnsight==0.3.0",
    "huggingface_hub",
    "tqdm",
    "pandas",
    "accelerate",
)

app = modal.App("sae-experiment", image=image)

# Mount the experiment code
experiments_mount = modal.Mount.from_local_dir(
    ".",  # Current directory
    remote_path="/root/experiments",
    condition=lambda path: not path.startswith(".") and not path.startswith("__"),
)


@app.function(
    gpu="A100",  # Use A100-40GB. Options: "T4", "A10G", "A100", "H100"
    timeout=3600,  # 1 hour max
    mounts=[experiments_mount],
)
def run_sae_experiment(
    model_size: str = "8b",
    n_trials: int = 10,
    experiment_type: str = "basic",
    steering_values: list = None,
):
    """Run the SAE steering experiment on Modal."""
    import subprocess
    import sys
    import os
    
    os.chdir("/root/experiments")
    
    # Build command
    cmd = [
        sys.executable,
        "replicate_exp2_goodfire_sae.py",
        "--model", model_size,
        "--device", "cuda",
        "--n-trials", str(n_trials),
        "--experiment", experiment_type,
    ]
    
    if steering_values:
        cmd.extend(["--steering-values"] + [str(v) for v in steering_values])
    
    print(f"Running: {' '.join(cmd)}")
    
    # Run experiment
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    # Return results file path
    return result.returncode


@app.local_entrypoint()
def main(
    model: str = "8b",
    trials: int = 10,
    experiment: str = "basic",
):
    """Local entrypoint - run from command line."""
    print(f"Starting SAE experiment on Modal...")
    print(f"  Model: {model}")
    print(f"  Trials: {trials}")
    print(f"  Experiment: {experiment}")
    print()
    
    # Run on remote GPU
    returncode = run_sae_experiment.remote(
        model_size=model,
        n_trials=trials,
        experiment_type=experiment,
    )
    
    if returncode == 0:
        print("\n✓ Experiment completed successfully!")
    else:
        print(f"\n✗ Experiment failed with code {returncode}")


# Alternative: Run as a one-off without the app
if __name__ == "__main__":
    print("Run with: modal run run_on_modal.py")
    print("Options:")
    print("  modal run run_on_modal.py --model 8b --trials 10 --experiment basic")
    print("  modal run run_on_modal.py --model 8b --trials 10 --experiment full")

