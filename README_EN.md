# ClassMatter · 班事有谱

**Every class matter matters.**

[简体中文](README.md) · [What works](#what-works-today) · [Quick start](#quick-start) · [Architecture](#engineering-boundaries)

> **Open-source Pre-alpha · Synthetic data only.** This is a runnable engineering prototype, not a school-ready product. **Do not process real student, parent, or teacher personal data.**

## The problem

A homeroom teacher's day is more than a spreadsheet: observations become scattered, follow-up tasks are easy to lose, and reconstructing why something happened can require going back through messages and notes.

**ClassMatter is an external working memory and follow-up workspace for class affairs.** It connects structured records, tasks and a timeline so work can be revisited with context instead of being held entirely in someone's head.

Initially designed for the Chinese homeroom-teacher context; effectiveness in other education systems has not been established.

## What works today

| Need | Implemented slice |
| --- | --- |
| Set up a class | Local single-owner setup/login, classroom and student roster |
| Capture structured information | Typed business records with stable identifiers |
| Keep track of follow-ups | Tasks, Today view and Student Timeline |
| Correct mistakes carefully | Preview, explicit approval when required, record versions and audit trail |
| Use AI as an assistant | Replaceable Pydantic AI adapter for queries and drafts; **no autonomous business write or approval** |

A typical path is **record → associated task → Today follow-up → timeline review → correction and audit where needed**. These are verified engineering behaviors, **not evidence of measurable teacher workload reduction**.

## Engineering boundaries

- **Web:** React 19, TypeScript, Vite, Tailwind CSS.
- **Backend:** Python 3.13, FastAPI, PostgreSQL 18; layered domain rules, application gateways and infrastructure adapters.
- **Write safety:** QG for read-only queries; strict validated commands, risk-appropriate preview/approval and BCG transactional writes with idempotent receipts and audit; ISB governs identity.
- **AI boundary:** Model text can suggest or draft, not approve, alter schema or become canonical fact automatically.
- **Publication safeguards:** Exact SHA-256 allowlist in [PUBLIC_MANIFEST.json](PUBLIC_MANIFEST.json), secret scanning, contract checks and [synthetic CI](.github/workflows/synthetic-ci.yml).

Internal `class_os` identifiers are retained for compatibility, not as a public-facing brand. See the [engineering overview](docs/ENGINEERING_OVERVIEW.md).

## Quick start

The supported persistent local entry point requires **Windows and DPAPI**, plus PowerShell 7, Node 22–24, pnpm **11.19.0**, Python **3.13**, uv **0.11.7** and PostgreSQL **18.6** binaries.

```powershell
cd apps/web
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build

cd ../../backend
uv sync --frozen
uv run --frozen python local.py init --pg-root '<PostgreSQL18 installation directory>'
uv run --frozen python local.py start
uv run --frozen python local.py bootstrap
uv run --frozen python local.py serve
```

Open **http://127.0.0.1:8000**. Keep generated passwords and recovery codes out of Git; stop the owned database with `uv run --frozen python local.py stop`. Existing instances require an explicit migration. Do not copy `.local-runtime/` between machines. A standalone Vite mock (`VITE_CLASS_OS_DEMO=true`) is not the persistent service.

## Verification and limits

```powershell
python scripts/public_guard.py --require-license
pwsh ./scripts/verify.ps1 -Suite all -PostgresRoot '<PostgreSQL18 installation directory>'
```

The full local suite requires disposable PostgreSQL, browser and spike dependencies; Windows and Ubuntu synthetic CI passed on the [published main-branch run](https://github.com/Gdnbit/classmatter/actions/runs/39185506327). Passing engineering checks does **not** authorize production, real student records, formal R1, real-provider quality or cross-host recovery.

Capture automation, proactive reminders, complex scheduling, multi-role workflows, complete lifecycle and representative teacher trials remain incomplete or unproven. Linux CI does not imply a supported cross-platform persistent installer.

## Contribute and security

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Public audit summary](docs/PUBLIC_AUDIT.md) · [Backend](backend/README.md) · [Release scope](docs/specs/class-os-v1/release-1-manifest.md)

Project-owned code is available under [Apache-2.0](LICENSE), Copyright 2026 Gdnbit; see [NOTICE](NOTICE) and [third-party notices](THIRD_PARTY_NOTICES.md). This public repository is a clean, independently exported history that excludes private interviews, original source history, personal screenshots, secrets, runtime databases and archives. Review any change to the public allowlist before pushing; never upload local runtime or private research material.