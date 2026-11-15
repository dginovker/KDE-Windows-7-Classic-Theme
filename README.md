# Windows 7 Classic for KDE Wayland

Build an independently maintained Classic UI with a live return to the user's current desktop. This is research and planning, not an installable theme.

- `PROJECT-DIRECTION.md`: confirmed goals, proposed boundaries and first milestone.
- `reference/gallery.html`: genuine Windows 7 beside the earlier A/B experiments; click images for original pixels.
- `reference/README.md`: measurements, VM provenance and unresolved risks.
- Check the gallery: `python reference/verify.py` (requires Pillow).
- `vm/`: test VMs. `vm/vmctl.py lab start`, then `sh`/`user` (stdin script as root / as the `tester` desktop user), `put`/`get`, `click x y`, `type`, `key`, `shot`. Input never touches the host desktop. `vm/prepare-tester.sh` (run via `vm/vmctl.py lab sh`) recreates `tester` for a pristine stock Plasma 6.8.2 session.

No host theme, session or boot changes are authorized by these artifacts. Preserve unsaved work; Linux authentication and reliable apply/restore remain unverified. Work is tracked in GitHub issues.

## Install and toggle

Arch: `cd packaging && makepkg -si` (needs `wine` at build time for its LGPL Tahoma font; tested with Plasma/KWin 6.8.2 and Qt 6.12). Before removing the package, run `win7-classic current`; removal warns about anyone still in Windows mode. For development, `./install.sh` installs the same files for the current user only. Nothing changes on screen until you switch.

`win7-classic windows|current|toggle|status|restore` swaps the whole Plasma panel/desktop layout and panel theme by restarting only plasmashell; KWin and applications keep running. Each mode keeps its own saved layout under `~/.local/state/win7-classic/`, and every switch is logged there. Colors, fonts, widget style and window decoration are swapped key-by-key (only the keys listed in `toggle/windows/keys/`), so other settings in `kdeglobals`/`kwinrc` stay untouched, and running Qt apps update live. A switch that fails (e.g. a widget plugin is missing) rolls back and stays in the old mode; `restore` brings back the current layout from a terminal even with no panel running. The first switch builds Windows mode from your current panel (`toggle/windows/seed`): the launcher, task manager, clock, show-desktop and spacers become the Classic ones; every other widget (pager, monitors, your own widgets, the tray and its items) keeps its settings and sits before the notification area. `win7-classic rebuild` discards the Windows layout and builds it again from the current one.

## Lock and login screens

Windows mode locks with a Windows 7 logon-style screen (`plasma/lockscreen/`, `plasma/logon/`); current mode keeps Plasma's. Plasma reads the lock screen from its shell package, so Windows mode adds `~/.local/share/plasma/shells/org.kde.plasma.desktop/` (marked by `.win7-classic`): links to the system shell, plus real copies of `lockscreen/` (ours) and `logout/`. If the Windows lock screen fails to load, a plain password field replaces it. If you can't unlock, run `loginctl unlock-sessions` from a TTY.

The package also installs the SDDM theme `win7-classic`. SDDM is system-wide, so it is not toggled; to select it:

```
printf '[Theme]\nCurrent=win7-classic\n' | sudo tee /etc/sddm.conf.d/win7-classic.conf
```

Delete that file to return to your previous login screen. If the theme fails to load, SDDM shows its built-in one.

## What Windows mode has so far

- Classic window frames (`plasma/decoration/`, a KWin QML decoration): active, inactive, maximized and pressed-button states match the reference pixel-for-pixel apart from the app icon and title text.
- Classic colors (Win32 system colors from the reference VM, as a named `Win7Classic` color scheme so nothing of a dark current theme shows through), Tahoma 8.25pt with ClearType-like RGB subpixel text (`fonts/`, limited to the installed Tahoma files), and Qt's Windows widget style for Qt/KDE apps.
- GTK 3 apps: a Classic CSS theme (`plasma/gtk/`) on top of GTK's built-in Adwaita, switched through the `gtk-theme` GSetting so running apps restyle live. GTK 4/libadwaita apps can't be themed this way and keep their own look.
- Classic Start menu (part of the taskbar applet): favorites, All Programs (KDE's categories as folders), search over apps and System Settings, user folders and shortcuts on the right, Shut down (asks for confirmation through KDE's dialog). Opens with Start or the Meta key. Edges, separators and highlights match `reference/screenshots/w7-menu*.png`, `w7-programs.png` and `w7-search.png` pixel-for-pixel.
- Explorer (`explorer/`, `win7-explorer`): Windows 7 Explorer's chrome at the reference's pixel geometry, drawn with Windows' own art, around KDE's KIO file widgets, so copy/paste, trash, undo, rename, Open With, properties and network locations are KDE's own. Back/Forward with history, breadcrumbs with subfolder menus, Include in library (links the folder into a library folder), Share with (properties), view menu, preview pane, help, Ctrl+W. In Windows mode it replaces Dolphin: pinned Dolphin launchers become Explorer, and folders open in it (`toggle/windows/keys/mimeapps.list`). Folder and place icons come from the `Win7-Classic` icon theme (`plasma/icons/`), which inherits Breeze for everything else. A Windows layout built before this release keeps its Dolphin pin until `win7-classic rebuild`.
- Windows art (`explorer/assets/`, `plasma/icons/Win7-Classic/`) is extracted from the reference VM by `reference/tools/extract-assets.py`: icons from imageres/shell32/ExplorerFrame.dll, Back/Forward cropped from reference screenshots because Classic Explorer renders them differently from its bitmaps.
- Classic taskbar (`plasma/`): Start button, Never-combine task buttons, pinned launchers, notification-area frame around the stock system tray, two-line clock and Show Desktop. Task buttons and pinned items can be dragged into any order. Edges match `reference/screenshots/w7-taskbar.png` pixel-for-pixel; icons and text differ.

## Tests

All run from the host against the lab VM and write screenshots to the given directory:

- `python tests/test_toggle.py [outdir]`: real Kate/Konsole/file-dialog work survives 22 switches, per-mode edits persist, configs return byte-identical, failure and restore paths work.
- `python tests/test_frames.py [outdir]`: frame pixels match the Windows references in active/inactive/maximized/pressed states; caption buttons work (releasing off a pressed button cancels it); a running app picks up Tahoma live; switching back restores `kdeglobals`/`kwinrc` exactly.
- `python tests/test_widgets.py [outdir]`: a pager on two desktops and a custom widget are carried into the Classic taskbar with byte-identical config; the pager switches desktops; `rebuild` picks up later changes.
- `python tests/test_upgrade.py [outdir]`: upgrading from the taskbar-only release while in Windows mode, then switching both ways; Start menu anchored above Start at 100% and 150% scaling.
- `python tests/test_package.py [outdir]`: builds and installs the Arch package in the VM, switches modes using only packaged files, removes it; no packaged file remains, nothing else under /usr or /etc changes, current-mode config is byte-identical.
- `python tests/test_gtk.py [outdir]`: a running GTK 3 app turns Classic (ButtonFace background, raised button bevels, white sunken fields); the GTK theme and font are restored, and after the first switch round trips leave `~/.config/gtk-*/` byte-identical.
- `python tests/test_text.py [outdir]`: Start menu labels against Windows: pixel difference, label widths (up to 3px long, from fractional glyph advances), ClearType-colored pixels; other fonts' rendering unchanged.
- `python tests/test_startmenu.py [outdir]`: menu, hover, All Programs and search views match the references outside icons and labels; search + Enter, arrow keys + Enter, Documents, Esc/Start/Meta, and a cancelled Shut down all work.
- `python tests/test_lock.py [outdir]` and `tests/test_login.py`: Windows lock screen and SDDM theme with the tester's real password. Field placement matches `w7-lock.png`/`w7-login.png`; a wrong password shows the error and stays locked; the right one unlocks or logs in; current mode keeps Plasma's lock screen; a broken theme still unlocks.
- `python tests/test_explorer.py [outdir]`: the pinned Dolphin becomes Explorer and folders open in it; copy/paste, back, F2 rename, Delete to trash, Ctrl+Z, search, New folder, right-click menu, opening a file, Details view, Properties and Ctrl+W work with mouse and keyboard; current mode opens Dolphin again with `mimeapps.list` and the icon theme restored.
- `python tests/test_taskbar.py [outdir]`: taskbar structure matches the Windows reference outside button faces and tray icons; task buttons minimize/restore, launchers launch, Start and Show Desktop work, it still matches after switching away and back, and dragging a button reorders it and saves the pinned order.
- `python tests/test_light.py [outdir]`: with Breeze Dark as the current theme, Windows mode leaves no dark colors, selects the Win7Classic scheme, makes the desktop portal prefer light and draws an inactive Dolphin toolbar light; switching back restores Breeze Dark exactly.

## Recovery

Old checkouts, experiments, logs and scripts were removed from the working tree, not discarded. Their complete verified archive and cleanup manifests are outside this project:

`/home/wacket/.local/state/windows7classic-cleanup/20261114T212841Z/`

Restore `original.tar.zst` into a separate directory, never over this project. VMs, installation media, credentials and private fonts were not moved or modified.
