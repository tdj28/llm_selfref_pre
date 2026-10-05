"""Validate the entire production argv with the installed pinned vLLM parser."""
from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path

from experiments.kolibri_swap import bootstrap, protocol

WHEEL_SHA256 = "09d48617fc2be9c6cdcd5db480651ab0d84817b257204f2cc2e3ecbb70bbb635"
PARSER_SOURCES = {
    "engine/arg_utils.py": "950cb3b650c081d6d36d43d73e3ecd669b44eabd4fe8395b92e399c7a89b8011",
    "entrypoints/launchers/cli_args.py": "7f4388428da9a2b2922153816b8f48f3ed1bca4be1a436c6a6f6e6820291c14c",
    "utils/argparse_utils.py": "3c99367eb8a5462d3cfd1c5f41732279ca977bbb57bd6b50d7f337e849b0941e",
}


def serve_argv():
    return ["/tmp/kolibri-venv/bin/vllm", "serve", bootstrap.MODEL,
        "--revision", bootstrap.MODEL_REVISION, "--tokenizer-revision", bootstrap.MODEL_REVISION,
        "--served-model-name", bootstrap.MODEL, "--host", "127.0.0.1", "--port", "8000",
        "--kv-cache-dtype", "fp8", "--reasoning-parser", "kolibri1", "--generation-config", "vllm",
        "--max-model-len", "16384", "--max-num-seqs", "16", "--gpu-memory-utilization", "0.90",
        "--enforce-eager", "--seed", "20261004", "--no-enable-log-requests"]


def validate_parser(parser, validate):
    """Parse, validate and inspect; never call the server or load a model."""
    argv = serve_argv()
    assert "--no-enable-log-requests" in parser._option_string_actions
    assert "--disable-log-requests" not in parser._option_string_actions
    args = parser.parse_args(argv[2:])
    validate(args)
    expected = {"model_tag": bootstrap.MODEL, "revision": bootstrap.MODEL_REVISION,
        "tokenizer_revision": bootstrap.MODEL_REVISION, "served_model_name": [bootstrap.MODEL],
        "host": "127.0.0.1", "port": 8000, "kv_cache_dtype": "fp8", "reasoning_parser": "kolibri1",
        "generation_config": "vllm", "max_model_len": 16384, "max_num_seqs": 16,
        "gpu_memory_utilization": .90, "enforce_eager": True, "seed": 20261004,
        "enable_log_requests": False}
    assert all(getattr(args, key) == value for key, value in expected.items()), "Parsed production options differ"
    return {"schema": "kolibri-a5-cli-preflight-v1", "status": "passed", "vllm": "0.29.0",
        "argv": argv, "argv_sha256": protocol.digest(argv), "parsed": expected,
        "help_sha256": hashlib.sha256(parser.format_help().encode()).hexdigest(),
        "parser_source_hashes": PARSER_SOURCES, "model_loaded": False, "scientific_generation": False}


def main():
    assert version("vllm") == "0.29.0", "Pinned vLLM distribution differs"
    import vllm
    package = Path(vllm.__file__).parent
    assert all(protocol.sha(package / name) == digest for name, digest in PARSER_SOURCES.items()), "Pinned parser bytes differ"
    from vllm.entrypoints.launchers.cli_args import make_arg_parser, validate_parsed_serve_args
    from vllm.utils.argparse_utils import FlexibleArgumentParser
    parser = make_arg_parser(FlexibleArgumentParser(prog="vllm serve"))
    print(protocol.canonical(validate_parser(parser, validate_parsed_serve_args)), flush=True)


if __name__ == "__main__":
    main()
