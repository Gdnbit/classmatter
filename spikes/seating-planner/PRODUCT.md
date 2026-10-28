# Seating preview experiment

This scoped surface implements contributor task03's synthetic solver and preview
UI. It belongs to the existing ClassMatter visual world, not a new product brand.
Canonical requirements, release and architecture remain at the repository paths;
this brief grants no formal feature or real-data admission.

Mode: Operate. The teacher tests a synthetic classroom layout, unavailable seats,
fixed placements and explicit pairwise nonadjacency, compares candidates and
makes a validated manual move or swap. Success is an explainable candidate with
before/after positions, or an honest infeasible/undetermined result.

Hard constraints cannot be traded against the soft changed-seat count. No health,
grade, behavior or other sensitive inference is accepted. There is no official
assignment, save/commit API, upload, identity model or production persistence.
Refresh discards all state. Mouse drag, click/keyboard move and undo support the
same validation. Changing settings invalidates previous candidates.

The inherited app uses system CJK typography, background #f6f7f4, text #182018,
primary #1e5d50, pale green surfaces and restrained outlines. Keep that world and
an operational split between constraints and classroom preview. At narrow widths
stack them; only the classroom canvas may scroll internally for wide layouts.
