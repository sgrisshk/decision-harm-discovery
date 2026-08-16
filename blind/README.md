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
make blind-rehearsal
make blind-issue RUN=run-001
make blind-verify RUN=run-001
make blind-shell RUN=run-001
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

The official actor is deterministic Python, not a generative model or chat editor. It reads the signed
`BLIND_MANIFEST.json`, public analytical partitions, and allowlisted discovery engine, then writes
the three schema-v1.1.0 artifacts. The manifest supplies dataset identity, feature timing, outcome
metadata, contract versions, method version, seed, and input hashes; the executor has no
dataset-local private manifest and no hard-coded contract version.

Docker mounts the workspace read-only and overlays only `/workspace/output` as writable. The
container has a read-only root, no Linux capabilities, `no-new-privileges`, and network `none`.
Issuance rejects a provider model and launch rejects provider networking. The hard paid-usage
ceiling is zero requests, zero tokens, and zero cost. No provider credential or evaluator key is
passed. The retired provider actor remains only as historical/tested code and is absent from the
official image; its generic child-Python helper also strips known provider API-key variables.

`make blind-image` builds the pinned `infra/docker/blind-agent.Dockerfile` with Python, Polars, and
Pydantic. The allowlisted executor and engine are signed workspace inputs. Issuance and launch
accept only `name@sha256:<digest>` and record the resolved image provenance. Before issuance,
`blind-rehearsal` creates a temporary signed allowlist-only workspace, launches the real executor
through the production Docker boundary, and runs normal freeze validation. It must print
`BLIND_REHEARSAL_VALID`; it neither creates an official run nor opens hidden truth.

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

All earlier provider-backed runs, including verified but unlaunched `…-014`, are immutable
audit-only artifacts and must not be reused after runtime/source drift. The deterministic runtime
is pinned as
`policy-blind-agent@sha256:5632ca11139272623e95a82a9fa24c52f19c16d8edc236dfa500e02cbc9570c0`.
After `make blind-rehearsal` succeeds, the evaluator issues a new unique run and launches:

```sh
make blind-shell RUN=<new-run-id>
```

The coordinator supplies neither `BLIND_EVALUATOR_KEY_FILE` nor any provider credential to the
container. A failed launch permanently closes that run ID; issue a new run rather than retrying it.

This is credible, reproducible local-development isolation, not absolute security against a host
administrator. Keep the run directory and evaluator-owned ADR-008 receipt together for audit.
