# Deployment interface

The provider is intentionally undecided. CI builds and verifies both images with immutable `${GITHUB_SHA}` tags. Once a registry/host is selected, staging deployment from `main` must consume those exact digests; production promotion is a manual protected-environment action that promotes the same digest rather than rebuilding it.

Provider decisions still required: registry, managed PostgreSQL, object storage, TLS/domain, secret manager, migration runner, log/metric destination, backups, regional/data-residency constraints, and rollback mechanism. Do not add credentials or pretend deploy steps until those decisions are made.

Deploy order: backup/readiness checks → backward-compatible migration job → API → web → smoke checks. Rollback application images independently; forward-fix schema when a migration is not safely reversible.
