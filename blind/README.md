# Blind Discovery Agent

This runner creates a reproducible local boundary for official blind discovery. The normal ML
Engineer works in the repository and may see generator internals; that identity/session is never
eligible to execute a blind run. A Blind Discovery Agent starts fresh in a container that mounts
only an allowlist-built workspace outside the checkout. Blindness cannot be restored retroactively.

## Workflow

```sh
make blind-prepare RUN=run-001
make blind-verify RUN=run-001
make blind-shell RUN=run-001 AGENT=external-cli
make blind-freeze RUN=run-001
make blind-status RUN=run-001
```

Runs default to `/tmp/policy-blind-runs`; set `BLIND_RUNS_ROOT` to another directory outside the
checkout. `prepare` refuses reuse, copies only regular files matched by `blind/allowlist.yaml`,
hashes them, and records manifest, provenance, state, and append-only events. `verify` rejects
missing, changed, additional, hidden, forbidden, Git, or symlink paths. `launch` verifies first,
starts a new CLI process in Docker, and never resumes a session. `freeze` schema-validates the
three required outputs, records hashes, copies them read-only to `frozen/`, and closes the state.
Evaluation is a separate trusted process and is not mounted or implemented here.

The container image named by `BLIND_AGENT_IMAGE` must contain the selected agent CLI, Python,
Polars, and Pydantic. The default launcher disables networking. For an API-backed CLI, set
`BLIND_NETWORK=provider` and the matching `PROVIDER_A_API_KEY` or `PROVIDER_B_API_KEY`; Docker passes
only that variable and never mounts the host CLI home/history. Docker's bridge network cannot
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

This is credible, reproducible local-development isolation, not absolute security against a host
administrator. Keep the run directory and evaluator-owned ADR-008 receipt together for audit.
