# Stage 0 Recovery Notes

This release preserves two technical recovery events. Neither event changed
the frozen calibration plan, candidate pool, telemetry, matching algorithm, or
selected-feature artifact.

## Cache Routing

The first launch began downloading the first model shard into the 30 GB
container cache instead of the mounted workspace. It was stopped before model
load, telemetry, matching, or any output artifact. The partial cache was moved
once to `/workspace/hf-cache`, the default Hugging Face path was symlinked to
that location, and the exact frozen commit was restarted. The first-launch
logs are preserved under `startup_failures/cache_misroute/`.

## Missing SciPy

The restarted job completed all 144 telemetry rows and wrote
`calibration.json`, but the separate frozen audit then failed closed because
the RunPod requirements omitted SciPy. The failed audit log is preserved.

An attempt to install the root lock's `scipy==1.18.0` was also preserved; that
version requires Python 3.12 while the frozen image uses Python 3.10. The audit
was then run unchanged with `scipy==1.15.3`, the version already installed in
the repository's analysis environment and the newest compatible release.

The calibration SHA-256 before and after dependency recovery was identical:

`ed9daed9bc00ebd43f0c8461ef0c2cb2c4b7702953f3a9d2bfb6a8153c3fb9d4`

The remote audit and a byte-identical local re-audit both pass with zero
errors, 144 metric rows, and 24 selected rows. The recovery files are under
`startup_failures/missing_scipy/`.
