# Blind Discovery Agent

This runner creates a reproducible local boundary for official blind discovery. The normal ML
Engineer works in the repository and may see generator internals; that identity/session is never
eligible to execute a blind run. A Blind Discovery Agent starts fresh in a container that mounts
only an allowlist-built workspace outside the checkout. Blindness cannot be restored retroactively.

## Workflow

```sh
# Evaluator/coordinator identity, from the trusted checkout:
make blind-key-init RUN=run-001
make blind-image
PROVIDER_API_KEY=<secret> BLIND_AGENT_MODEL=<approved-provider-model-id> make blind-provider-preflight
PROVIDER_API_KEY=<secret> BLIND_AGENT_MODEL=<approved-provider-model-id> make blind-rehearsal
make blind-issue RUN=run-001 BLIND_AGENT_MODEL=<approved-provider-model-id>
make blind-verify RUN=run-001
PROVIDER_API_KEY=<secret> make blind-shell RUN=run-001 \
  BLIND_AGENT_MODEL=<approved-provider-model-id> BLIND_NETWORK=provider
make blind-freeze RUN=run-001
make blind-status RUN=run-001
```

Runs default to `/tmp/policy-blind-runs`; set `BLIND_RUNS_ROOT` to another directory outside the
checkout. The signing key defaults to `/tmp/policy-blind-evaluator/signing.key`, outside both the
checkout and run tree. `blind-key-init` creates it once with mode `0600`; it is evaluator-owned and
must never be sent to Discovery. `issue` refuses reuse, copies only regular files matched by
`blind/allowlist.yaml`, hashes them, and writes an evaluator-signed `BLIND_MANIFEST.json` into the
workspace. `verify` requires the external key and rejects an invalid signature as well as
missing, changed, additional, hidden, forbidden, Git, or symlink paths. `launch` verifies first,
rejects source/allowlist drift since issuance, requires the exact signed immutable image digest,
starts a new CLI process in Docker, and never resumes a session. `freeze` validates output schema
v1.1.0 and its signed dataset/contracts/splits/provenance/timing/language acceptance fields, records
hashes, copies them read-only to `frozen/`, and closes the state.
Evaluation is a separate trusted process and is not mounted or implemented here.

The fresh actor is a bounded provider tool-calling loop, not a chat editor. It can list/read public
workspace files and execute Python without a shell. Docker mounts the workspace read-only and
overlays only `/workspace/output` as writable. The actor rejects symlinks, nested output paths,
and every artifact name except `candidates.json`, `discovery_metrics.json`, and `run_report.md`.
Any launch failure or freeze acceptance failure permanently transitions the run to `FAILED`.
`read_file` uses 1-based inclusive `line_start`/`line_end` pagination and permits at most 250
lines per call. Omitted bounds start at line 1 and use one maximum-size page. Pagination resolves
through the same safe-relative regular-file check, so traversal and symlinks remain forbidden.
Provider requests use the fixed non-secret User-Agent
`policy-blind-agent/1.0 blind-benchmark`. HTTP error bodies are length-capped, whitespace-normalized,
and redact both the active key and generic Bearer tokens before the actor writes a single-line
error to stderr.
Each request caps completion at 1,024 tokens and serialized conversation context at 18,000
characters. Tool outputs are capped at 4,000 characters, only the six most recent turn groups are
retained, and oversized executed arguments are replaced by a non-secret placeholder. HTTP 429 is
retried at most three times using capped `Retry-After`/exponential delays of at most 30 seconds.
Preflight requires two sequential paginated `read_file` turns under these same limits.
The literal `search(path, query)` tool scans at most 100 regular files and 2,000,000 bytes,
returns at most 50 matches and 4,000 characters, and never follows symlinks. Provider HTTP 400
`tool_use_failed` responses receive at most two corrective turns that restate the exact tool
allowlist and schemas; exhaustion fails the run.

`make blind-image` builds the pinned `infra/docker/blind-agent.Dockerfile`, containing the minimal
provider tool-calling actor,
Python, Polars, and Pydantic. Build uses a convenience tag, but issuance and launch accept only
`name@sha256:<digest>` and record requested reference plus resolved image ID/digest in signed run
metadata and provenance. `BLIND_AGENT_MODEL` is the exact provider API model ID. Issuance requires
an explicit model; agent and model are
covered by the evaluator signature and launch must match both. Before consuming an immutable run
ID, the coordinator runs `blind-provider-preflight`, which verifies the pinned image, selected
model, network path, `PROVIDER_API_KEY`, and model tool-calling support without mounting a workspace
or printing the secret.
Before issuance, `blind-rehearsal` mounts a temporary truth-free fixture through the production
Docker isolation flags. It deterministically injects one recoverable `tool_use_failed`, then
requires the authenticated model to list files, perform paginated reads, use bounded search,
execute Python, and create exactly three schema-v1.1.0 dummy outputs. Host-side Pydantic validation
must print `BLIND_REHEARSAL_VALID`. This command never creates an official run.
The default launcher disables networking. Provider mode passes only `PROVIDER_API_KEY` and never
passes or mounts the evaluator key, host CLI home, or history. The container has one bind mount
(the issued workspace), a read-only root, no Linux
capabilities, and `no-new-privileges`. Docker's bridge network cannot
distinguish provider traffic from arbitrary web access, so this explicit mode is a documented
residual risk; a reviewed egress proxy is required for a published benchmark.

## Threat model

| Threat | Mitigation | Residual risk |
|---|---|---|
| Accidental ground-truth access | Allowlist-only export plus forbidden-name scan | Misclassified public content |
| Generator reveals patterns | Generator/evaluator paths are absent and forbidden | Information encoded in approved inputs |
| Git recovers private files | No `.git`; standalone copy | Host compromise |
| Parent-directory escape | External run root and container with one mount | Docker/host administrator controls |
| Symlink escape | Source and workspace symlinks rejected | Container/runtime vulnerability |
| Method changed after results | Input hashes and frozen runtime | Agent can choose analysis details allowed by the method |
| Results changed after truth | Read-only frozen copy and SHA-256 provenance; ADR-008 signed receipt remains evaluator-owned | Host admin can rewrite local files; hashes expose it only if audit metadata is retained |
| Forged public issuance | HMAC-signed manifest verified with an external mode-0600 evaluator key before launch/freeze | Evaluator host compromise |
| Mutable or substituted runtime | Digest-only image reference, resolved at issuance and rechecked/recorded before `RUNNING` | Registry/runtime compromise |
| Checkout changed after issuance | Launch compares current allowlist and source hashes to signed snapshot | Deliberate reissuance required for any legitimate source change |
| Structurally incomplete output | Schema v1.1.0 and signed acceptance contract checked before freeze | Statistical validity still belongs to later validation |
| Actor modifies inputs or writes arbitrary files | Read-only workspace plus separate writable `output/` mount and exact output-name enforcement | Container/runtime compromise |

## Official TASK-015 issuance

The external-CLI-backed runs through `task-015-official-20260814-008` are immutable audit-only failed
artifacts and must not be retried. The provider actor runtime is pinned as
`policy-blind-agent@sha256:0d64b3acd49008577216fd79e14c9c242e6c99b52712931ee7ef2392ecae98a2`.
After the human credential owner has revoked the exposed provider key, exported a valid
`PROVIDER_API_KEY`, selected an available provider model ID, and the preflight succeeds, the evaluator
issues a new unique run and gives the fresh Discovery actor only this coordinator-side launch:

```sh
PROVIDER_API_KEY=<secret> make blind-shell RUN=<new-run-id> \
  BLIND_AGENT_MODEL=<same-signed-model-id> BLIND_NETWORK=provider
```

The coordinator supplies `PROVIDER_API_KEY` only for that launch. It does not supply
`BLIND_EVALUATOR_KEY_FILE` or the key bytes to the container. Do not reuse an existing actor
session and do not launch the repository-scoped ML agent; either invalidates blindness.
The actor runs headlessly with an explicit signed model, an ephemeral home, no host config,
and no Git-checkout requirement. A failed launch permanently closes that run ID; issue a new run
rather than retrying it.

This is credible, reproducible local-development isolation, not absolute security against a host
administrator. Keep the run directory and evaluator-owned ADR-008 receipt together for audit.
