# Calibration v2 r3 Audit-Only Recovery

Status: prospective technical-recovery redesign after a pre-claim host
compatibility failure, an incomplete `NOT READY` provider review, and a
completed negative v2 provider review, before any recovered audit output is
computed or inspected. This plan is not executable until the separately
authorized final v3 review closes the accepted findings.
This is not a new model run and cannot change the r3 estimand,
prompt panel, directions, doses, layers, thresholds, or claim policy.

## Why recovery is necessary

The r3 model transaction completed atomically as
`calv2-r3-1a16572-20260715T002344Z`. Its `RUN_COMPLETE.json` has canonical
receipt SHA-256
`bab48b452c7e7c5b9db5d09ecc34c7e530813e2f5093aff1b8a8152017e4695d`
and physical SHA-256
`d60e25d13d1b9e30a52114aa954a6c1306ef8e15a8dddd53af1de58c4dcb9fee`.
The 35 manifested raw files total 323,365,550 bytes; with the completion
receipt, the remote ledger contains exactly 36 files. The external raw-ledger
file has physical SHA-256
`7bffb6306b67814d2f4618b6aaf4f243ab2992d7b6b92ebb955a370654e0a20c`.
No target prompt or target feature was used, and no prior outcome row was an
analysis input.

The first independent audit stopped before publication with
`CalibrationAuditError: J-lens map inventory differs`. The failure log has
physical SHA-256
`a5936d0fda01b96f193a1ab40c9d7c52dc751ecdf3686896e26d2d3951cdd86f`.
No compact audit or summary was published.

The cause is a target-independent compatibility predicate. The authentic,
hash-pinned checkpoint contains maps for source layers 0 through 78. The study
requires and uses only layers 45 through 78. The frozen runtime correctly
accepts the checkpoint when the required set is a subset of the available set;
the frozen auditor incorrectly requires the two sets to be equal. The pinned
checkpoint SHA-256 remains
`335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.

### Pre-claim recovery-host finding

The first prospective recovery host exposed an operational assumption that is
not valid on the provider runtime. Fresh pod `faz2t3bcrdwymn` staged attempt
`calv2-r3-audit-recovery-e0dd9a6-20260715T015420Z`, passed the fresh guest and
cache preflights, and received an authorization bound to the then-frozen
bind-mount design, receipt SHA-256
`e3ece08f712206a9a03c133e79afd62047174025c4d259d42020e95d6accce62`.
Before the audit entry point was invoked, however, the required read-only bind
mount failed with return code 32 and `permission denied`. The container ran as
UID 0 but lacked `CAP_SYS_ADMIN` in both its effective and bounding capability
sets; mount-namespace and user-namespace fallbacks also failed with `Operation
not permitted`. A direct Landlock ABI query on the same host returned ABI 4.

The self-hashed external runtime-block receipt is
`PREEXECUTION_RUNTIME_BLOCK.json`, receipt SHA-256
`bf8ddbb31b3ddab99c2126d1100691f8d0878c1a0d1d4a091776e5d3f2bc207d`.
It records `audit_execute_invoked=false`. Neither the exclusive attempt marker
nor a failure or compact output was created, so no recovered scientific
calculation was started or inspected. The remote attempt metadata was
retrieved before the exact pod was deleted. Its termination-audit,
frozen-termination, and post-delete receipt SHA-256 values are respectively
`a7fa432b64f594926fac22070a59c5081e68e8a4cc230ae4a2ffc0032dd30300`,
`0bc9fd91dc816e70e95809da50b667cb67bc6b0674d7b4c84415b3287bbebbd0`,
and `7d0c31b4830fdedad2e985e28168418a86483241ced2bd415d45ff12eecf1d06`.
The post-delete account inventory contained zero pods; the network volume was
not deleted.

That host and its authorization are now historical failure evidence only. The
authorization is not reused even though it never claimed its marker: the
source, plan, confinement mechanism, review closure, host, command, and output
namespace all change under this re-freeze.

## Exact correction

The immutable r3 plan and its bound `audit.py` remain unchanged. A separate
recovery entry point makes exactly one scientific-compatibility correction:
the J-checkpoint inventory predicate specified below. Its other adaptations
are operational only: fresh audit-host watchdog/publication authority, an
isolated historical-source validator, and a byte-equivalent audit-only tensor
hasher needed to keep the old model runtime out of the executable package.
None may weaken original run-timing checks or touch a scientific calculation.
The corrected loader must:

1. rehash the checkpoint against the frozen SHA-256;
2. verify `n_prompts == 125` and `d_model == 8192`;
3. require every study layer 45 through 78;
4. record the complete available layer inventory and unused extras in the
   recovery-only `recovery_audit.j_checkpoint_inventory` provenance field;
5. reject a missing required layer;
6. expose only the same maps and the frozen J-artifact metadata shape
   (`sha256`, required `map_count=34`, and `revision`) to the unchanged
   downstream audit calculations.

The authentic available inventory is 0 through 78. Extra maps are ignored by
the frozen orientation and transport loops. No metric, threshold, aggregation,
bootstrap, layer role, row inclusion rule, or claim gate may change.

The outcome-blind
`AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.{json,md}` appendix mechanically binds
the frozen plan/source bytes, the transitively called 49-function scientific
audit closure, orientation/validator/tensor-hash semantics, the exact recovery
adapter surface, and an affirmative scientific-field projection. Its synthetic
test joins the old and recovery loaders' selected maps and emitted metadata
into synthetic audit records from the same checkpoint, ignores harmless extra
maps only after recording them in recovery provenance, and requires the full
projected scientific fields—including artifact recomputation metadata and a
selected-map-derived metric field—to remain byte-identical. The
inherited-design manifest distinguishes the J artifact's
`n_prompts=125` fitting metadata from this experiment's eight fixed prompt
units; `prompt_id` is the bootstrap unit, and no prompt-population
generalization or increase in power is claimed.

## Dual provenance and authorization

The recovered audit must validate two independent chains and one intervening
operational record:

- The original ownership, guest, cache, authorization, execution binding,
  raw manifest, and completion receipt establish provenance of the r3 model
  transaction.
- A fresh receipt-owned one-B200 guest in `US-CA-2` on network volume
  `bv9gb9j32y`, plus fresh guest/cache receipts, establishes provenance of the
  audit-only computation.
- The first recovery host's runtime-block, retrieval, and termination receipts
  establish why the bind-mount authority was abandoned. They are historical
  evidence, not authority for the next host and not a scientific input.

Before execution, an audit-recovery authorization must bind:

- this re-frozen plan's physical hash;
- the committed Landlock launcher, recovery source, and focused tests;
- the direct no-site confined bootstrap, its focused tests, the exact external
  Python-import-root manifest, and the complete byte/path inventories of every
  approved active/dependency root and ordered `sys.path` entry;
- the scientific-equivalence extractor, machine/human appendices, focused
  equivalence test, and independent offline verifier/test;
- the clean local, tracking, and live remote Git commit;
- the new bounded Pro review evidence for this material redesign and its
  explicit adjudication;
- the original run ID, raw namespace, completion receipt hashes, 36-file
  ledger hash, failed-audit-log hash, and original receipt chain;
- the first recovery host evidence identities recorded by the bound plan and
  review closure;
- the fresh audit host's ownership, guest, and cache receipt hashes;
- the self-hashed pre-authorization Landlock probe receipt, including its
  separate protected/output canary outcomes, the closed NVIDIA character-device
  allowlist and inode/device identities, and the post-confinement CUDA
  compatibility result;
- a short audit-only deadline and conservative spend ceiling;
- an exact 60-minute, $6.00 provider-creation-bound ceiling at the frozen
  conservative $6.00/hour rate, starting from the fresh audit host's provider
  creation time;
- an authorization-issuance gate requiring at least 30 minutes to remain in
  that envelope after staging, pinned dependency setup, the full public-cache
  rehash, and the Landlock/CUDA probe; and
- zero model forwards, zero target renders, zero target feature vectors, and
  an empty *external-or-prior* outcome-input list for the fresh audit host.

Both the old execution authorization and the superseded first recovery
authorization are historical provenance, not authority for the next fresh
pod. A wholly new authorization, attempt ID, output namespace, canonical
command, receipt chain, deadline, and budget are required. The new
authorization cannot permit a model forward. The recovery must begin and
publish inside its new audit-only budget. The expired or superseded r3
operational clock remains historical execution provenance and is never
presented as authority for the fresh host. The recovery entry point may replace
the original operational watchdog with the new receipt-bound watchdog, but
may not alter the original run-timing validation or any scientific
calculation. A missed recovery window stops recovery rather than changing a
clock or deadline.

The recovered audit preserves the original top-level
`campaign_started_at_unix`, `campaign_deadline_at_unix`, and
`hourly_price_usd` fields byte-semantically as historical r3 fields. Fresh
authority is recorded only under a distinct `recovery_execution_campaign`
object. The recovery-specific atomic publication marker binds
`recovery_deadline_at_unix`; it does not repurpose the historical campaign
deadline.

The 60-minute/$6.00 value is a hard worst-case envelope, not an expected spend
or a retention target. The external controller terminates the exact pod as
soon as success or failure evidence is retrieved. The prior 30-minute envelope
left only about 22 minutes after live4's ordinary staging and cache preflight;
it is superseded prospectively because the new probe must not permit an
authorization with an unusably short remaining audit window.

Zero-forward status is enforced at four levels: the fresh guest receipt must
begin at zero; the recovery entry point must install a process-local guard that
raises on any `torch.nn.Module` call and on the base Transformers model-loader
families; forbidden runner/runtime modules are denied by an import guard; and
the exact executable package must contain no 70B model construction or runner
entry point. The original source bytes required to validate the historical
authorization are present only in a separately inventoried, write-confined,
non-importable provenance tree. They are never on `PYTHONPATH`. The only audit
dependency formerly imported from the model runtime is `tensor_sha256`; it is
supplied by a small audit-only shim whose outputs are mechanically compared to
the frozen implementation across dtypes and non-contiguous tensors. The
recovery receipt records that all guards fired zero times. Tokenizer loading,
safetensor reads, direct tensor arithmetic, and loading only
final-normalization/LM-head weights remain allowed.

The authorization binds one commit-scoped attempt ID, the exact provenance
root, model/J paths, one durable regular-filesystem output leaf, the separate
disposable `landlock_canary/{protected,output}` subtrees used by the real
launcher, the exact enumerated NVIDIA character-device file exceptions,
Landlock receipt, compact output names, attempt marker, failure receipt, and a
canonical command hash.
Each device exception is bound by canonical path, file type, inode, filesystem
device, and character-device `rdev`/major/minor identity; no wildcard or device
directory is authorized.

The launcher atomically creates the self-hashed Landlock receipt with `O_EXCL`
after confinement is active. Its existence consumes the authorization even if
the subsequent same-PID `execve`, imports, or validation fail before the
attempt marker is claimed. The confined audit atomically creates the attempt
marker with `O_EXCL`; either exclusive receipt prevents authorization reuse.
No second durable publication directory or retry can be selected inside the
same authority. The disposable canary output is an enforcement self-test
exception only and must be empty after that test.

## Execution and stopping rules

The next recovery uses a frozen Linux Landlock ABI-4 filesystem policy, not a
mount or namespace claim. It must never be described as a read-only mount. The
host must report Landlock ABI 4 or newer, but the launcher handles and claims
only the explicit ABI-4 rights below and records the observed ABI. Any
unavailable or older ABI, ruleset error, unexpected syscall result, or
inability to prove the exact policy is a pre-claim stop condition requiring a
new review and authorization; there is no unconfined fallback.

Before a new authorization is issued, a disposable subprocess on the new host
must exercise the exact prospective ABI-4 policy. Its durable receipt/cache
leaf is `attempt_root/preflight/output`; a separate
`attempt_root/preflight/canary/{protected,output}` pair supplies a protected
canary containing known files and directories and an initially empty output
canary. Neither canary is inside the r3 raw or historical-provenance tree.
Before restriction, the launcher must prove that the protected canary is
ordinary writable storage for its UID by opening `seed.txt` write-only without
writing, creating and removing a scratch file, and creating and removing a
scratch directory. Only then may post-restriction `EACCES` outcomes be
attributed to the Landlock domain rather than DAC or a read-only filesystem.
The probe's two `0x1b2` output-directory rules cover only its durable output
leaf and its canary-output leaf. A third exact rule on `/proc/self/task` grants
only `WRITE_FILE|TRUNCATE` (`0x4002`), which CUDA needs to write each new
thread's virtual `comm` name; it grants no `MAKE_*`, remove, or `REFER` right.
Because Landlock path-beneath rules cannot select a future dynamic TID's
`comm` filename, those two rights apply to all existing procfs descendants
beneath `/proc/self/task`, not only `comm`. This exception reaches process
metadata only and does not overlap the raw, provenance, repository, model, or
output trees.
Under the handled filesystem
mask `0x7ff2`, the protected canary must deny write-open, truncate, creation,
removal, linking, and rename operations while remaining byte- and
path-identical. The output canary receives exactly `0x1b2` and must permit
directory and regular-file creation, write plus `fsync`,
same-directory rename, unlink, and directory removal; it must deny `O_TRUNC`
and cross-directory linking, symlink, FIFO, and Unix-socket creation because
their corresponding handled rights are not allowed there. The restricted
child empties the output canary, the controller verifies that the protected
canary is unchanged. The controller preserves the entire probe root at its
authorization-bound path through recovery, retrieval, and offline verification;
it may remove that root only after the complete recovery evidence is retained.

The same probe resolves a closed, explicitly enumerated set of NVIDIA
character-device files. Each is required to be a character device and is
bound by canonical path, `st_dev`, `st_ino`, and `st_rdev` (including major and
minor numbers). The policy adds one file rule per enumerated device granting
only `WRITE_FILE` (`0x2`), never a rule for `/dev` or a device directory.

The probe sets `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`, and
`CUDA_CACHE_DISABLE=1`, forces
Hugging Face and Transformers offline/local-only operation, and places
`HOME`, `TMPDIR`, `HF_HOME`, `TRANSFORMERS_CACHE`, `XDG_CACHE_HOME`,
`TORCH_HOME`, `PIP_CACHE_DIR`, `NUMBA_CACHE_DIR`, `CUDA_CACHE_PATH`,
`TRITON_CACHE_DIR`, `TORCHINDUCTOR_CACHE_DIR`, and `PYTHONPYCACHEPREFIX`
under the allowed probe-output subtree. `PYTHONHOME`, `PYTHONPATH`,
`PYTHONPLATLIBDIR`, `PYTHONINSPECT`, `PYTHONSTARTUP`, `PYTHONUSERBASE`,
`LD_PRELOAD`, and `LD_AUDIT` must be absent
from the launcher environment. Before either confined child starts, a
stdlib-only staging operation inventories every regular file and directory in
the final active root and approved Python dependency anchors, rejects symlinks,
hardlinks, or special files, and exclusively writes a canonical self-hashed
root manifest outside every inventoried root. The manifest binds the canonical
Python binary, bootstrap source, complete file/directory inventories, and the
only ordered `sys.path` entries that may be installed. Neither roots nor
manifest may change afterward.

The authorization validator exact-matches the launcher receipt's complete
preflight child command—including interpreter, direct bootstrap, manifest path
and physical hash, active root, receipt/canary/output paths, and ordered device
arguments—and the child receipt binds the committed recovery closure and the
bootstrap's process-lifetime attestation. After confinement, the direct
`python -B -E -s -S` bootstrap rehashes every approved import-root byte before
setting `sys.path`. It installs deny/loader guards before any project or ML
import, forbids `site`, `sitecustomize`, and `usercustomize` for the process
lifetime, and patches Torch module-call plus Transformers model-load boundaries
before importing the recovery entry point. It then imports the exact pinned
Torch, Transformers, NumPy, and Safetensors packages and
performs a small BF16 transfer to `cuda:0`, a raw tensor matrix
multiplication, a finite-value reduction that must pass, and
`torch.cuda.synchronize(0)`. This is a runtime-compatibility check only: it
loads no model, invokes no `torch.nn.Module`, renders no prompt, and performs
zero model forwards. Failure of an import or numeric/CUDA check, any write
outside the probe output, a device identity change, or a need for any
additional device or filesystem right is a pre-authorization stop.

The probe touches neither scientific inputs nor outputs. Its self-hashed
receipt chain records the provider pod identity, observed Landlock ABI, exact
masks, distinct canary identities and syscall outcomes, enumerated device identities and
rules, exact environment/cache confinement, imported dependency versions,
BF16 transfer/matmul/finite-reduction/synchronization results, zero-forward
status, root-manifest/guard attestation, and source hash. That receipt is
reviewed and bound into the new
authorization. The probe process exits after restriction because Landlock
cannot be relaxed.

Real execution is a two-phase, same-PID transition. The minimal launcher is
invoked by its absolute, hash-bound script path with the exact interpreter
startup form `python -B -E -s -S /absolute/path/to/landlock_launcher.py`; package
module (`-m`) invocation is forbidden. Before parsing execution arguments it
requires `no_site`, disabled bytecode writes, an empty project/ML-module import
set, and direct-script package state. This prevents `sitecustomize` or package
initializers from executing before confinement. The launcher therefore runs
before project, Torch, Transformers, CUDA, tokenizer, or audit imports. It
resolves and validates all authorization-bound roots, verifies
that `/proc/self/task` contains exactly its own thread, and audits every
inherited descriptor in `/proc/self/fd`. Any inherited file-backed shared
mapping is rejected even when its current protection lacks `PROT_WRITE`, as is
an inherited `io_uring` descriptor. Any descriptor resolving into the raw
or provenance tree stops execution, as does every inherited writable
regular-file or directory descriptor, including one already opened inside the
durable output leaf. Every inherited
descriptor whose target matches the closed NVIDIA-device grammar is rejected,
whether or not that device was enumerated, as is every non-stdio writable
character- or block-device descriptor; no descriptor into either canary
subtree may be inherited. The receipt inventories the allowed standard
streams and other non-filesystem descriptors. No raw or provenance file is
opened before confinement.

While still single-threaded, the launcher creates a ruleset handling the full
frozen ABI-4 filesystem mutation mask `0x7ff2`: `WRITE_FILE`, `REMOVE_DIR`,
`REMOVE_FILE`, every `MAKE_*` right, `REFER`, and `TRUNCATE`. It sets
`PR_SET_NO_NEW_PRIVS`, then grants
`WRITE_FILE|REMOVE_DIR|REMOVE_FILE|MAKE_DIR|MAKE_REG` (`0x1b2`) through two
exact directory rules: the authorization-bound durable `attempt_root/output`
leaf and the disposable `attempt_root/landlock_canary/output` self-test leaf.
The sibling `attempt_root/landlock_canary/protected` subtree receives no rule.
One additional exact path-beneath rule grants only `WRITE_FILE|TRUNCATE`
(`0x4002`) on `/proc/self/task`, permitting CUDA's thread-name writes to
dynamic virtual `task/<tid>/comm` files without granting any handled create,
remove, link, or rename right. The two rights apply to all existing procfs
descendants of that task root; no broader `/proc` rule exists.
The launcher also grants only `WRITE_FILE` (`0x2`) through one file rule for
each exact authorization-bound NVIDIA character-device inode, after
revalidating its canonical path, character-device type, `st_dev`, `st_ino`,
and `st_rdev`. There is no `/dev` directory rule and no wildcard rule. The
launcher then calls `landlock_restrict_self`.

All other filesystem locations are default-denied for every handled
operation. The two allowed output directories receive no permission for the
other handled rights, `/proc/self/task` receives only the two disclosed
thread-name rights, and the enumerated NVIDIA device files receive no
handled right other than the write-open access CUDA requires. The disposable
canary output is used only for the repeated enforcement test and is empty
afterward. The marker, failure receipt, compact bundle, and every necessary
regular-file temporary, cache, and runtime file must be inside the durable
output leaf. Actual execution uses `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONNOUSERSITE=1`, `CUDA_CACHE_DISABLE=1`, Hugging
Face/Transformers offline-local-only settings,
and `TMPDIR` and all cache roots below that durable leaf. No repository, raw,
provenance, model/J artifact, home, general temporary-directory, or
device-directory write allowance exists. Any attempt to open an unenumerated
or identity-changed NVIDIA device for writing fails closed.

After restriction, the launcher first repeats the protected-denial and
output-allow/deny matrix against the independent, authorization-bound
`attempt_root/landlock_canary/{protected,output}` subtrees. The protected
canary must remain byte- and path-identical and the output canary must be empty
at the end. It then performs only non-destructive checks on real protected
files. `O_WRONLY|O_CLOEXEC|O_NOFOLLOW` opens without `O_TRUNC` or a subsequent
write must return `EACCES` for raw `RUN_COMPLETE.json`, historical provenance
`r3/plan_manifest.json`, and the recovery authorization outside the output
leaves. No create, remove, truncate, or rename is attempted in the raw or
provenance trees. The launcher then atomically writes an exclusive self-hashed
Landlock receipt under the durable output leaf. That receipt binds the PID,
ABI, exact handled and output-allowed masks, all three path rules, exact
device-file rules and identities, resolved roots, thread inventory, descriptor
audit, real-tree and repeated-canary checks, pre-authorization probe receipt
and dependency/CUDA result, authorization, command, and source hashes.

The launcher immediately same-PID `execve`s the hash-bound direct bootstrap as
`python -B -E -s -S /absolute/active/.../confined_bootstrap.py`, never `-m`.
The child command binds its mode, active root, external root-manifest path and
physical SHA-256, then the recovery arguments. The Landlock domain and
`no_new_privs` state are inherited before the bootstrap revalidates the Python
binary, its own source, every approved import-root byte/directory, and the
ordered `sys.path`. Only after process-lifetime import/model guards are active
does it import and dispatch `execute-confined`. That phase validates the
exclusive Landlock receipt, same PID, bound roots/manifest/command, fresh
namespace, and live authorization window. Only then may it claim the exclusive
attempt marker and open raw or provenance inputs for the audit. If the Landlock
receipt exists but `execve`, bootstrap validation/import, or pre-marker
validation fails, the authorization remains consumed and a fresh authorization
is required.

The frozen ABI-4 Landlock policy has explicit limits. It does not retroactively
mediate already-open file descriptors, which is why the inherited-descriptor
audit and no-protected-open ordering are mandatory. Its filesystem rights also
do not mediate metadata-only operations such as `chmod`, `chown`, timestamp
changes, or extended attributes. ABI 4 has no handled device-`ioctl` right;
after the exact character-device `WRITE_FILE` open is allowed, NVIDIA driver
`ioctl` operations and their device-side effects are outside Landlock's
filesystem-content/topology claim. CUDA requires that exception. The closed
device list, exact identities, post-confinement dependency/BF16 CUDA probe, and
this unhandled-`ioctl` limitation are disclosed, but they do not make device
operations filesystem output.

CUDA initialization also requires `WRITE_FILE|TRUNCATE` on the virtual
`/proc/self/task/<tid>/comm` thread-name files. The exact `/proc/self/task`
path-beneath rule is therefore a disclosed process-metadata exception to the
default-deny filesystem policy, and its two rights apply to all existing
procfs descendants beneath that root rather than only `comm`. It does not grant
handled creation, removal, linking, or rename rights, and it does not broaden
the raw/provenance immutability claim.

The reviewed executable closure must contain no metadata-only operation
against a protected tree. Exact pre- and post-audit raw and provenance
byte/path inventories remain mandatory and detect content or namespace drift;
these hashes supplement Landlock but do not turn it into kernel read-only
mount semantics, prove continuous immutability between the two observations,
exclude a sibling process or another NFS client, or by themselves prove
absence of metadata-only change. They establish endpoint equality immediately
before and after the confined audit. The
precise claim is that the audit process and descendants can perform handled
regular-filesystem content/topology mutations only under the durable output
leaf and the separate disposable self-test output leaf, with only the
enumerated NVIDIA character-device `WRITE_FILE` exception beyond those two
directories. It is not a claim that device `ioctl` effects are mediated. These
limitations are disclosed in every recovered audit receipt and claim.

Once confined, execution rehashes the complete raw tree against both
`RUN_COMPLETE.json` and the externally preserved 36-file ledger and validates
the historical provenance inventory. It then runs the unchanged r3 prompt,
tensor, arithmetic, orientation, final-norm/LM-head, transport, bootstrap,
gate, and summary logic. It does not construct the 70B model and performs no
model forward.

The zero-forward evidence is explicitly scoped to this approved recovery
process and closure. It is the conjunction of: the hash-bound import roots;
static exclusion of model runner/runtime entry points; process-lifetime denial
of `site` customization and forbidden runner imports; patched Torch
`Module`-call and Transformers `from_pretrained` boundaries installed before
project imports; the narrower inner-audit guards; and the target-free raw CUDA
probe. Receipts separately record bootstrap-installation, preflight, guarded
audit, and post-dispatch phases plus every covered counter. This is not an
OS-wide detector for arbitrary bespoke native callables, sibling processes, or
device `ioctl` effects.

After all metrics are computed but before any success publication, the full
raw tree and historical provenance tree are rehashed again against their
frozen inventories. Only then may compact output be atomically published in
the one authorization-bound durable output leaf. The audit and summary must
disclose the correction identity, old failure-log hash, original and both
recovery-host receipt chains, recovery source/plan/review hashes, exact
Landlock policy and limitations, full available J inventory, required
inventory, and unused extras. The raw and provenance pre/post inventories must
be identical.

Stop without retry or *success* publication if:

- any raw byte or manifest entry differs;
- any required J map is missing;
- the pinned J artifact or metadata differs;
- the proposed correction reaches beyond the inventory predicate;
- either receipt chain fails;
- any target/outcome input or model forward is introduced;
- the source/review/Git closure differs;
- either two-canary enforcement test, exact device identities/rules, confined
  dependency imports and BF16 CUDA arithmetic/synchronization,
  single-thread/descriptor audit, real-tree checks, Landlock receipt, same-PID
  transition, or durable-output-plus-disposable-canary-output-plus-enumerated-
  device policy differs; or
- either audit deadline or spend ceiling is crossed.

The fresh receipt-owned pod is terminated after the compact bundle, Landlock
receipt, logs, and lifecycle evidence are retrieved, or after any failure and
all retrievable failure evidence is preserved. The external controller records
the exact pod deletion and a zero-pod post-delete account inventory. An
uncatchable host loss or retrieval failure still triggers exact-pod termination
before the deadline. Persistent network volume `bv9gb9j32y` and the retained
r3 raw namespace are never deleted; the fresh guest receipt records and binds
the provider-observed volume size rather than relying on a console label.
Every catchable failure after the one-shot marker is claimed writes an
exclusive canonical operational failure receipt containing the attempt,
authorization, command, source, error, and compact-publication state. The
external stderr log, pod receipt chain, and termination proof are also
preserved; failure cannot create or relabel a compact scientific success
bundle. An uncatchable process or host loss still leaves the exclusive marker
and external provider/log evidence and cannot be retried under that authority.
A failure after the exclusive Landlock receipt but before the marker similarly
leaves the authorization consumed and is recorded externally; it cannot be
retried under that authority.

The r3 raw outputs are the primary subject of this audit and therefore are not
misdescribed as forbidden "outcome inputs." The forbidden set is external or
prior scientific outcomes used to adapt, select, pool, or judge this recovery;
that set remains exactly empty.

## Review disclosure

Two provider reviews are historical failure evidence and neither is approval.
The earlier plan-only response ended incomplete before seeing the later
executable. The subsequent exact six-file Landlock packet was submitted once
to `gpt-5.6-sol` Pro as response
`resp_076355ae1eba8bf5016a570d939bcc819ba1a5412f83532777`; it ended
`status=incomplete`, reason `max_output_tokens`, and visibly returned `NOT READY
TO FREEZE`. The helper's exact input preflight was 67,535 tokens with a
$1.41976875 reserve estimate, but provider aggregate usage was 302,642 input
and 30,896 output tokens (13,711 reasoning), reconstructing to $2.44009 at the
frozen rates and exceeding the $1.80 authorization estimate. The raw response,
failure manifest, self-hashed budget-incident receipt, and structured
adjudication are preserved. No silent replacement call was authorized from
that failed attempt; each later call required separate explicit authority.
The canonical machine-readable adjudication is
`reviews/AUDIT_RECOVERY_LANDLOCK_GPT_PRO_ADJUDICATION.json`; its physical
SHA-256 is
`96fad9342ebe064357ac6e06fd26de1fb11209aa713e12805180f81316bced1a`
and its internal receipt SHA-256 is
`91735ff2937f85a4c4e0320eeb480c0f9fb8b6ae946b9d8ddda6ce800e4927e0`.
It maps B01–B04 and I01–I06 to accepted prospective changes while retaining
the historical final decision `NOT_READY_TO_EXECUTE`.

Every visible finding is accepted prospectively. B01 is addressed by the
scientific-equivalence appendix and inherited-design manifest. B02 is addressed
by the direct no-site hash-bound bootstrap and complete Python import-root
inventory. B03 preserves the exact historical campaign fields and records
fresh authority separately. B04 implements the literal required-layer subset
predicate without an exact release-inventory whitelist. I01–I06 narrow the
zero-forward/endpoint/reproduction claims, require structured adjudication and
test receipts, and distinguish the eight prompt units from J-artifact fitting
metadata. Because these fixes change reviewed packet files, the incomplete
response cannot become READY by adjudication.

Before any recovery authorization, the material redesign therefore requires a
separately budget-authorized, completed latest-flagship Pro review of the final
immutable packet: this plan, bounded runtime context, scientific-equivalence
appendix, bootstrap/launcher/recovery/verifier surfaces, focused tests, and the
historical reviews and adjudications. The user explicitly authorized one final
v3 call with a bounded increase for the expanded prior-review and qualification-
receipt packet: producer and verifier share the exact $25 preflight ceiling,
with a 1.2-million-character/400,000-estimated-token input guard and the same
20,000-output-token request cap; expected spend is lower, and no silent retry
is permitted. The exact call must
use the corrected aggregate-input/output reserve guard and a fresh output
directory. A completed response's visible text must equal the raw provider
output, and a machine-readable adjudication must give every stable finding a
blocking flag, disposition, rationale, and changed-path set. Blockers may be
fixed or technically rejected but never deferred; any accepted blocker that
changes a reviewed file requires another separately authorized review.

The final completed review artifacts, adjudication, source/test inventories,
hashes, and exactly two self-hashed test inputs -- `LOCAL_TEST_RECEIPT.json` and
`TARGET_HOST_TEST_RECEIPT.json` -- must be authorization-bound. The target
qualification additionally includes the byte-identical provider-derived
`TARGET_QUALIFICATION_OWNERSHIP.json` receipt. Each test receipt
records the code-freeze commit, exact source/test byte inventory, exact command
and argv, interpreter, platform, complete installed-distribution inventory,
collected/pass/fail/skip/not-run node IDs and counts, UTC start/completion, and
exit status. The local receipt requires its observed HEAD to equal the
code-freeze commit. Local macOS Linux/Landlock skips remain disclosed and are
not relabeled as target-host passes.

The target receipt is a qualification of a disposable host, not a receipt from
the later recovery pod. It requires US-CA-2 volume `bv9gb9j32y`, one B200,
Linux, Landlock ABI at least 4, the pinned dependency versions, and an actual
pass (never a skip) for the designated live same-PID Landlock test. It also
binds byte-for-byte copies of that host's provider-derived
`TARGET_QUALIFICATION_OWNERSHIP.json`,
`TARGET_QUALIFICATION_LANDLOCK_ENFORCEMENT.json`, and
`TARGET_QUALIFICATION_LANDLOCK_CUDA_PREFLIGHT.json` through both physical and
self-receipt hashes. The provider's host-created UTC is preserved with
fractional seconds when supplied; probe completion, test start/completion, and
elapsed host ages are recorded. These qualification timings inform operational
feasibility only. The distinct fresh recovery pod must still repeat its own
same-host Landlock/CUDA preflight, and authorization still requires at least 30
minutes left in its independent one-hour publication window.

Run-specific receipts cannot be members of the Git commit whose tests they
attest. The circularity is resolved explicitly: first commit the receipt
schema/producer/verifier and all source/test bytes as `code_freeze_commit`; run
the local and disposable-target qualifications against that freeze; then copy
the receipts and their three target-qualification support files
byte-identically into the review-input/evidence commit. Later evidence/review-only
commits are admissible
only while the code freeze remains an ancestor and `git diff --quiet` proves
that every bound `experiments/` and `tests/` byte is unchanged. Authorization
rehashes the current source/test closure, both receipts, and all three target
qualification files, requires the two receipts to name the same code freeze and source/test
inventory, requires the qualification pod to differ from the recovery pod, and
places byte-identical copies under the attempt's `evidence/tests/` directory.
The offline verifier repeats those checks. No authorization is issued and no
recovered audit is claimed ready until this closure exists.

## Claim boundary

A successful result is an explicitly disclosed post-run technical recovery of
the prospectively frozen r3 raw collection. It is not described as the
original same-pod r3 audit. Scientific claims remain unavailable until the
corrected audit publishes and its compact receipts pass independent validation.
If recovery fails for any data-, metric-, or required-map reason, a separately
frozen fresh model execution is required.
