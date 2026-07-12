# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately — do **not** open a public issue.

- Email: **security@sponge-theory.io**
- Or use GitHub's [private vulnerability reporting](https://github.com/ezeeFlop/oriflux/security/advisories/new) on this repository.

You can expect an acknowledgement within 72 hours. Please include reproduction
steps and the affected component (ingest, api, workers, web, SDKs, deploy).

## Scope

- The Oriflux server (ingest / api / workers), dashboard, and deploy manifests.
- The published SDKs (`oriflux.js`, `oriflux-sdk` on PyPI).

## Supported versions

Only the latest released version (`latest` image tag / current `main`) receives
security fixes.

## What we care about most

Oriflux's value proposition is privacy: cookieless visitor hashing with a daily
destroyed salt, IPs resolved to geo at ingestion then discarded, strict
multi-tenant isolation (`org_id` scoping, hashed API keys), SSRF protection on
outbound connectors, and encrypted connector secrets. Reports touching any of
these guarantees are treated as highest severity.
