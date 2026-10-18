# Contributing to ClassMatter

Project-owned code uses Apache-2.0; Copyright 2026 Gdnbit. Third-party components retain their terms. This remains a local Pre-alpha candidate, not an approved public release. Do not submit real student records or credentials.

Use Python 3.13/uv, Node 22–24/pnpm 11.19.0 and PowerShell 7. Follow [AGENTS](AGENTS.md). Keep requirements → architecture/domain → contracts → eval → task → release traceability. Use synthetic, reproducible fixtures, preserve gateway boundaries, and run relevant verification before review.

Added or changed public content requires explicit manifest review and `python scripts/public_guard.py`; do not regenerate manifests just to silence a failure. CI has no deployment or release authority. Security issues must not be reported with raw data in public threads; see [SECURITY](SECURITY.md).
