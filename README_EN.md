<div align="center">
  <img src="https://repository-images.githubusercontent.com/1424619394/0730fa01-db22-4b12-a757-ab2bddf0e601" width="760" alt="ClassMatter, with the giraffe and notebook mark">

  <h1>ClassMatter · 班事有谱</h1>
  <p><strong>An open-source classroom workbench for teachers</strong></p>
  <p>Record what happened, see what needs attention, and turn finished work into a summary.</p>
  <p>
    <a href="README.md">简体中文</a> ·
    <a href="#everyday-work">Everyday work</a> ·
    <a href="#quick-start">Quick start</a> ·
    <a href="#docs-and-contributing">Docs and contributing</a>
  </p>
  <p>
    <a href="LICENSE"><img alt="Apache-2.0 license" src="https://img.shields.io/badge/License-Apache--2.0-285b4d"></a>
    <a href="https://github.com/Gdnbit/classmatter/actions/workflows/synthetic-ci.yml"><img alt="Windows and Ubuntu CI" src="https://github.com/Gdnbit/classmatter/actions/workflows/synthetic-ci.yml/badge.svg?branch=main"></a>
  </p>
</div>

## Everyday work

Start the day with **Needs my attention**, **Might need a reminder**, and **Waiting on others**. Record an event in chat when it happens. At the end of the week, use the records and follow-ups you already have to draft a summary. The same item is available from chat, the student record, and the work view.

> “Create a follow-up to collect the permission slips by Friday.”
>
> “Swap these two students’ seats and show me the layout first.”
>
> “Draft a summary of the classroom work we finished this week.”

Review the draft or compare the before and after states in chat. Confirm to save, then see the result on the original page.

| Classroom work | How ClassMatter helps |
| --- | --- |
| **Record events and follow through** | Start with a message or voice transcription. Link students, notes, and deadlines, then see progress, waiting items, and student timelines. |
| **Manage classes, grades, and seating** | Use the roster and gradebook in the same workspace. Compare seating layouts before applying a change. |
| **Prepare summaries and documents** | Draft from existing records, request materials from paired colleagues, edit documents, browse revisions, and export to Word or PowerPoint. |
| **Find the source** | Ask a question in chat, search the knowledge library, and follow citations to the source material. |

## Quick start

Build the Windows desktop app from source. You’ll need PowerShell 7, Node.js 22–24, pnpm 11.19.0, Python 3.13, uv, and PostgreSQL 18.6. The commands below start a fresh workspace. To bring an existing workspace forward, follow the [backup and upgrade guide](apps/desktop/README.md).

```powershell
git clone https://github.com/Gdnbit/classmatter.git
cd classmatter/backend
uv sync --frozen
uv run --frozen python local.py prepare-chat --profile conversation-d1 --pg-root '<PostgreSQL 18.6 installation directory>'
uv run --frozen python local.py upgrade-classroom --profile workspace-chat-d3

cd ../apps/web
pnpm install --frozen-lockfile
cd ../desktop
pnpm install --frozen-lockfile
pnpm build
pnpm start
```

Connect and enable your model in desktop settings. Start with a conversation and attach a class when the task calls for it.

## Docs and contributing

- [Desktop setup and upgrades](apps/desktop/README.md) · [Backend development](backend/README.md) · [Documentation index](docs/README.md)
- [Product requirements](docs/specs/class-os-v1/requirements.md) · [Architecture](docs/specs/class-os-v1/architecture.md) · [Implementation and verification](docs/implementation-ledger.md)
- [Contributing](CONTRIBUTING.md) · [Report an issue](https://github.com/Gdnbit/classmatter/issues) · [Security reports](SECURITY.md)

ClassMatter is open source under the [Apache-2.0 license](LICENSE). Copyright © 2026 Gdnbit. [Notices](NOTICE)
