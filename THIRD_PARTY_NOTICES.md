# ClassMatter third-party notices

Project-owned code uses Apache-2.0, Copyright 2026 Gdnbit. The owner confirms redistribution rights for project/prototype code. This is an ownership assertion, not an independent legal clearance; dependency components retain their own licenses and notices.

Dependencies are installed from frozen lockfiles, not vendored executable binaries. Exact installed-package license metadata and copied upstream license texts are inventoried under `third_party/` when generated. Public upstream copyright holders must retain their notices; do not anonymize legal attribution.

Important components: React/Vite/Tailwind/Lucide (generally permissive), Pydantic AI (MIT), FastAPI/SQLAlchemy/Alembic (MIT), OpenAI SDK (Apache-2.0), Psycopg (LGPL-3.0), and signature-spike cryptography/in-toto components. These descriptions are orientation, not a complete transitive-license verdict. The generated inventory is authoritative for exact installed versions and available notices; unknown/missing terms require review.

The installed scope also includes MPL-2.0 components such as certifi/pathspec, and PSF/BSD/ISC terms. No such dependency is relabeled Apache-2.0. Some wheels omit notices: exact-tag upstream notices supplement logfire-api and the native Rolldown binding; source URLs and checksums are in `third_party/supplemental-license-review.json`. `review_required=[]` means the installed metadata/notice collection has no unresolved entry, not universal distribution-law approval.

Psycopg binary wheels can include native libpq/OpenSSL/other notices; source-only distribution with separately installed dependencies is different from bundling a desktop image, container or binary. Do not claim full binary-distribution compliance from Python metadata. PostgreSQL binaries, Node, Python, browsers and scanning executables are not shipped in this candidate.

No external fonts, personal screenshots, logos or archive exports are included. Future packaged releases require a separate binary SBOM/license and corresponding-source/notice review where applicable. Vulnerability scans and license checks are independent.

Optional local desktop Demo: Electron (MIT plus its bundled Chromium/FFmpeg/other third-party notices), Electron Packager (BSD-2-Clause), and Playwright Core (Apache-2.0) are pinned in `apps/desktop/pnpm-lock.yaml`. The older `third_party/dependency-licenses.json` does not inventory this new build/test scope. The local bundle retains Electron's LICENSE/LICENSES.chromium.html, project notices, and generated exact installed Web production-dependency notices inside its application archive. This is a local unsigned Demo, not an approved public binary release or a complete binary-distribution compliance verdict; see [desktop boundaries](docs/desktop-demo.md).
