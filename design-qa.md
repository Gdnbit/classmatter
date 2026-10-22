# Desktop chrome design QA

## Target and evidence

Source visual truth: owner-selected P2 desktop header, retained only as a local attachment (not published). Scope is its integrated titlebar/navigation/menu treatment, not Codex's product tabs or content.

Implementation screenshot: `apps/desktop/.build/evidence/packaged-home.png`; local-only full page. Viewport and density: `apps/desktop/.build/evidence/viewport.json`. Original P2 is a 1586 × 114 px top strip with unspecified OS scaling; implementation capture is a different full-window viewport at local Windows scaling. Comparison uses the focused top strip and logical 44px titlebar, not pixel-exact font-size claims across unknown density. Both source and implementation were opened together for visual comparison. Native Windows caption controls are not included in renderer-only screenshots; the overlay visibility is separately asserted in integration tests.

Measured implementation: 1382 × 816 CSS px, devicePixelRatio 1.25; screenshot 1728 × 1020 px. The top strip is evaluated separately from ClassMatter's intentionally different content. No rescaling of private source imagery is published.

## Findings and comparison history

- Earlier P1: separate OS title row plus a second menu row split the application chrome. Fixed using Electron hidden titlebar/native control overlay and one integrated toolbar. Revised capture has one shallow, continuous pale bar, functional navigation/menu entries and rounded white content below; no remaining P1 mismatch in the agreed scope.
- Earlier P2: adding the toolbar reduced the available app height and clipped the sidebar footer. Fixed by sizing app/main to viewport minus toolbar and sidebar to parent height. Revised capture shows the footer; integration asserts exact app/sidebar bottom alignment.
- Typography: existing system font and Lucide icons retained; compact neutral-weight menus follow the reference hierarchy. No raster assets or fabricated brand marks added.
- Spacing/layout: one 44px top strip, reserved native caption area, separate click/drag regions, content corner and aligned sidebar; existing business layout preserved intentionally.
- Colors: pale blue-grey chrome/side rail, white main canvas; no heavy divider or second menu band.
- Assets: no new illustrative assets required; navigation uses existing icon dependency, native window controls remain OS-owned.
- Content: ClassMatter synthetic context retained intentionally; no Codex label, tab system or repository actions copied.

## Verification and limits

Real packaged Electron tests cover titlebar visibility, drag/no-drag CSS, fixed bridge surface, sidebar toggle, back/forward, navigation/reload, minimum-size/maximized composer layout, network denial, single instance and process exit. Web typecheck includes its existing 32 tests. No page errors in the passing packaged regression. Native drag/Snap and the visual appearance of OS popup menus still merit human spot-check; they use standard Electron/Windows behavior rather than custom window-control logic. This is not an assertion of pixel-identical Codex chrome.

## Follow-up polish

P3: automatically disabling history arrows at the bounds could improve affordance; current arrows safely no-op at the bounds. No actionable P0/P1/P2 issue remains within the selected header-only scope.

## Targeted frontend acceptance follow-up

The later whole-frontend audit found issues outside the original header-only comparison: drawer/header overlap, menu overflow, static history and incorrect fixed seat previews. These are not covered by the earlier header-only pass. The corrective implementation and executable acceptance map are in `docs/frontend-demo-acceptance.md`.

Current local renderer evidence: `apps/desktop/.build/evidence/acceptance/01-menu-minimum.png`, `02-detail-boundary.png`, `03-correct-preview.png`; all ignored runtime artifacts. These captures were opened and inspected: minimum-window menu remains accessible, drawer heading/close action are below the native toolbar, and the seat preview contains the requested 01/02 identities with six-column topology. No new graphic assets were introduced; original typography/palette retained. Functional tests additionally cover shared counts, memory-only application, focus, IME, draft isolation and honest capability states. Remaining service integrations and broader accessibility/OS validation are explicitly out of scope, not silently passed.

final result: passed
