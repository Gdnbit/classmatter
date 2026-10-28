# Excel/CSV import

Status: TODO
Owner: unassigned
PR: pending
Accepted SHA: pending

## Objective
Parse synthetic rosters and exam sheets; preview headers, map fields, validate types, show row errors and conflict candidates. No formal DB writes.

## Before coding
Read AGENTS.md, CONTRIBUTING.md, docs/ENGINEERING_OVERVIEW.md and relevant requirements. Audit existing code and tests first. Implement one minimal independent slice without duplicating existing features.

## Acceptance
Empty file, duplicates, invalid values, deterministic preview.
Deliver working code, tests, usage instructions, limitations and a PR from a fork.

## Constraints
Synthetic data only. No real student data, production credentials, paid model calls, formal release changes, schema migrations, gateway bypasses, or weakening security checks. Future concepts are not authorized production features. Follow publication review and secret scanning rules.

## Checklist
- [ ] Code and spec audit
- [ ] Working implementation
- [ ] Tests and validation
- [ ] PR opened
- [ ] Maintainer accepted and merged

Only the maintainer changes status to DONE after acceptance.
