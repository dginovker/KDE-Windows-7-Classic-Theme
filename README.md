# Windows 7 Classic for KDE Wayland

Build an independently maintained Classic UI with a live return to the user's current desktop. This is research and planning, not an installable theme.

- `PROJECT-DIRECTION.md`: confirmed goals, proposed boundaries and first milestone.
- `reference/gallery.html`: genuine Windows 7 beside the earlier A/B experiments; click images for original pixels.
- `reference/README.md`: measurements, VM provenance and unresolved risks.
- Check the gallery: `python reference/verify.py` (requires Pillow).
- `vm/`: test VMs. `vm/vmctl.py lab start`, then `sh`/`user` (stdin script as root / as the `tester` desktop user), `put`/`get`, `click x y`, `type`, `key`, `shot`. Input never touches the host desktop. `vm/prepare-tester.sh` (run via `vm/vmctl.py lab sh`) recreates `tester` for a pristine stock Plasma 6.8.2 session.

No host theme, session or boot changes are authorized by these artifacts. Preserve unsaved work; Linux authentication and reliable apply/restore remain unverified. Work is tracked in GitHub issues.

## Install and toggle

`./install.sh` installs for the current user (needs `wine` for its LGPL Tahoma font): Plasma applets, the panel theme, the window decoration and `~/.local/bin/win7-classic`. Nothing changes until you switch.

`win7-classic windows|current|toggle|status|restore` swaps the whole Plasma panel/desktop layout and panel theme by restarting only plasmashell; KWin and applications keep running. Each mode keeps its own saved layout under `~/.local/state/win7-classic/`, and every switch is logged there. Colors, fonts, widget style and window decoration are swapped key-by-key (only the keys listed in `toggle/windows/keys/`), so other settings in `kdeglobals`/`kwinrc` stay untouched, and running Qt apps update live. A switch that fails (e.g. a widget plugin is missing) rolls back and stays in the old mode; `restore` brings back the current layout from a terminal even with no panel running. Windows mode is seeded from `toggle/windows/` the first time it is used.

## What Windows mode has so far

- Classic window frames (`plasma/decoration/`, a KWin QML decoration): active, inactive, maximized and pressed-button states match the reference pixel-for-pixel apart from the app icon and title text.
- Classic colors (Win32 system colors from the reference VM), Tahoma 8.25pt with ClearType-like RGB subpixel text (`fonts/`, limited to the installed Tahoma files), and Qt's Windows widget style for Qt/KDE apps.
- GTK 3 apps: a Classic CSS theme (`plasma/gtk/`) on top of GTK's built-in Adwaita, switched through the `gtk-theme` GSetting so running apps restyle live. GTK 4/libadwaita apps can't be themed this way and keep their own look.
- Classic Start menu (part of the taskbar applet): favorites, All Programs (KDE's categories as folders), search over apps and System Settings, user folders and shortcuts on the right, Shut down (asks for confirmation through KDE's dialog). Opens with Start or the Meta key. Edges, separators and highlights match `reference/screenshots/w7-menu*.png`, `w7-programs.png` and `w7-search.png` pixel-for-pixel.
- Classic taskbar (`plasma/`): Start button, Never-combine task buttons, pinned launchers, notification-area frame around the stock system tray, two-line clock and Show Desktop. Edges match `reference/screenshots/w7-taskbar.png` pixel-for-pixel; icons and text differ.

## Tests

Both run from the host against the lab VM and write screenshots to the given directory:

- `python tests/test_toggle.py [outdir]`: real Kate/Konsole/file-dialog work survives 22 switches, per-mode edits persist, configs return byte-identical, failure and restore paths work.
- `python tests/test_frames.py [outdir]`: frame pixels match the Windows references in active/inactive/maximized/pressed states; caption buttons work (releasing off a pressed button cancels it); a running app picks up Tahoma live; switching back restores `kdeglobals`/`kwinrc` exactly.
- `python tests/test_gtk.py [outdir]`: a running GTK 3 app turns Classic (ButtonFace background, raised button bevels, white sunken fields); the GTK theme and font are restored, and after the first switch round trips leave `~/.config/gtk-*/` byte-identical.
- `python tests/test_text.py [outdir]`: Start menu labels against Windows: pixel difference, label widths (up to 3px long, from fractional glyph advances), ClearType-colored pixels; other fonts' rendering unchanged.
- `python tests/test_startmenu.py [outdir]`: menu, hover, All Programs and search views match the references outside icons and labels; search + Enter, arrow keys + Enter, Documents, Esc/Start/Meta, and a cancelled Shut down all work.
- `python tests/test_taskbar.py [outdir]`: taskbar structure matches the Windows reference outside button faces and tray icons; task buttons minimize/restore, launchers launch, Start and Show Desktop work, and it still matches after switching away and back.

## Recovery

Old checkouts, experiments, logs and scripts were removed from the working tree, not discarded. Their complete verified archive and cleanup manifests are outside this project:

`/home/wacket/.local/state/windows7classic-cleanup/20261114T212841Z/`

Restore `original.tar.zst` into a separate directory, never over this project. VMs, installation media, credentials and private fonts were not moved or modified.
