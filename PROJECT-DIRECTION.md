# Direction

## User-confirmed goals

1. Build from scratch.
2. Use genuine Windows 7 as the visual reference.
3. Maintain a GitHub issue queue.
4. Live-toggle between the current and Windows UIs.

“From scratch” still needs an implementation boundary. The earlier AeroShell comparison is evidence, not a selected architecture.

## Proposed boundaries

Own the Classic layer on stock Plasma/KWin; reuse platform APIs instead of rebuilding window management, application indexing, audio or networking.

- Preserve applications, unsaved work and independently edited UI profiles.
- Provide terminal recovery; never silently half-apply a mode.
- Adopt components independently; separate browser, login/lock and boot work.
- Inventory essential shortcuts, workspaces, tray and display behavior.
- Require reference screenshots, interaction tests and restoration checks per issue.
- Package files cleanly; test upgrades/removal and verify asset rights.

## Proposed first milestone

VM-only panel/launcher switching with an unsaved editor, terminal task and dialog open. Test repeated switches, profile edits and controlled failure recovery. Deliver a recording plus current/Classic/restored screenshots before expanding scope.
