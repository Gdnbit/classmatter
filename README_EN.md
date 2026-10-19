# ClassMatter — Teacher Workflow & Follow-up Workspace

Every class matter matters.

An AI-assisted workspace for class records, follow-up tasks, timelines, and traceable decisions. **Pre-alpha; synthetic data only. Not approved for handling real student records.** Initially designed around the Chinese homeroom-teacher context; international applicability is not established.

## Working slice and boundaries

Owner setup/login → classroom/roster → typed records and tasks → Today/student timeline → correction preview and explicit approval → versioned audit. The optional Pydantic AI adapter provides queries and drafts, not business-write or approval tools. User triage is not organizational assignment or a liability determination. AI inference never automatically becomes a canonical fact.

Windows  + PowerShell 7, Node 22–24, pnpm 11.19.0, Python 3.13, uv 0.11.7 and PostgreSQL 18.6 binaries are required for the persistent local entry point. DPAPI protects local secrets; this is not a production or portable cross-host deployment template. See the [Chinese installation commands](README.md), [backend guide](backend/README.md) and [engineering map](docs/ENGINEERING_OVERVIEW.md).

Real-provider quality, representative teacher research, full lifecycle/recovery and formal release admission remain incomplete. Passing synthetic tests does not approve real data or production use.

Project-owned code is licensed under [Apache-2.0](LICENSE), Copyright 2026 Gdnbit; see [NOTICE](NOTICE). The owner confirms redistribution rights for the project and imported prototype. Third-party components retain their own terms; this confirmation is not an independent legal clearance.

This is an isolated **private** publication candidate with one history-free initial commit. Its first Windows and Ubuntu GitHub Actions checks passed, but **public visibility and a GitHub Release are not authorized**. Synthetic engineering checks are not formal R1, production, or real-student-data approval. See [third-party notices](THIRD_PARTY_NOTICES.md) and [readiness](docs/OPEN_SOURCE_READINESS.md). No private interviews, personal screenshots, original Git history, operational databases or credentials are included. Do not archive the whole working directory: only the reviewed public manifest belongs in a release.
