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
make blind-issue RUN=run-001
make blind-verify RUN=run-001
make blind-shell RUN=run-001 AGENT=external-cli BLIND_NETWORK=provider
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

`make blind-image` builds the pinned `infra/docker/blind-agent.Dockerfile`, containing external CLI CLI,
Python, Polars, and Pydantic. Build uses a convenience tag, but issuance and launch accept only
`name@sha256:<digest>` and record requested reference plus resolved image ID/digest in signed run
metadata and provenance. The default launcher disables networking. For an API-backed CLI, set
`BLIND_NETWORK=provider` and the matching `PROVIDER_A_API_KEY` or `PROVIDER_B_API_KEY`; Docker passes
only that provider variable and never passes or mounts the evaluator key, host CLI home, or
history. The container has one bind mount (the issued workspace), a read-only root, no Linux
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

## Official TASK-015 issuance

The currently issued workspace is
`/tmp/policy-blind-runs/task-015-official-20260814-006/workspace`. Its run state is `VERIFIED`;
manifest SHA-256 is
`f2981fbc8ff55ba31ba4f4124d3a7bab38d0c844b0024832bdc1e024700d6a10`. Bundle ID is
`4bb19187c3dc2f286e0a2326aacc54bf8c8959461a75d607ef5bdf0b10b1216d`. The signed runtime is
`policy-blind-agent@sha256:f42e3cdaf1e6a766e312e6a28c2a9d377b7137bb8643379dcf3588a01398cf1d`.
The coordinator starts the
fresh Discovery actor with this exact command (Discovery does not run it from the full checkout):

```sh
make blind-shell RUN=task-015-official-20260814-006 \
  AGENT=external-cli BLIND_NETWORK=provider
```

The coordinator supplies `PROVIDER_A_API_KEY` only for that launch. It does not supply
`BLIND_EVALUATOR_KEY_FILE` or the key bytes to the container. Do not reuse an existing external CLI
session and do not launch the repository-scoped ML agent; either invalidates blindness.
external CLI runs with its supported non-interactive flags, an ephemeral session, ignored user config,
and no Git-checkout requirement. A failed launch permanently closes that run ID; issue a new run
rather than retrying it.

This is credible, reproducible local-development isolation, not absolute security against a host
administrator. Keep the run directory and evaluator-owned ADR-008 receipt together for audit.
