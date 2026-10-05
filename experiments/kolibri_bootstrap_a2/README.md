# Kolibri Bootstrap A2

This technical recovery preserves the original and A1 failures. A1 freeze
`c9f0710abe6cced73fa6942c330a74dd346b190c` installed Ninja 1.13.2 but its
sanitized worker PATH omitted the venv bin directory. FlashInfer warmup
failed to spawn `ninja`. The 78 upstream CPU tests and 70 parser checks are
known; CUDA qualification failed and no research generation occurred.

The only worker delta prepends `/workspace/kolibri/venv/bin` to PATH and logs
bounded Ninja, NVCC and C++ discovery/version checks before smoke or server
startup. Ninja must resolve to the exact venv executable, and
`importlib.metadata.version('ninja')` must match the locked distribution
version `1.13.2`. Its nonempty actual executable banner is logged separately,
not compared with the wheel version; each tool version command has a
20-second deadline and must exit successfully.
No package, hardware, kernel, quantization, smoke assertion, sampling setting,
prompt, instrument, inventory or scientific gate changes. Compiler discovery
is not a CUDA pass: the unchanged full tiny qualification must pass.

A1's partial-JSON status handling and three bounded SSH status reads are
reused. Each new role has one durable creation intent under
`out/kolibri-swap-20261004/bootstrap-a2`; both previous pod IDs are forbidden.
Main requires this attempt's bound CUDA pass, verified retrieval and GET404.

Both saved cost bounds remain bound to their original ledgers and retrievals.
Their sum is $0.20653345641250872666666666663. Admission rounds this upward
to $0.20653345641250872666666667, without changing either raw cost receipt.
The cumulative cheap cap remains $1.25, GPU $25 and whole study $75. Carry
counts in per-call guards and whole-main admission. No automatic replacement
or additional spending authority is created.

The parent reviews stdout from
`python -m experiments.kolibri_bootstrap_a2.adapter --build-amendment`, writes
`data/kolibri_bootstrap_a2/plan_v1_20261005/AMENDMENT.json`, then freezes and
pushes. This is not a replacement scientific PLAN. Lifecycle flags are the
same as A1, using `experiments.kolibri_bootstrap_a2.adapter`; local collection
uses `experiments.kolibri_bootstrap_a2.production` with the A2 freeze SHA.
The parent owns all paid dispatch, tunnel, cleanup and publication.
