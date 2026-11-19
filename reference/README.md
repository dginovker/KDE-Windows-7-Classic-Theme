# Reference evidence

Open `gallery.html`; validate links and image dimensions with `python reference/verify.py` from the project root. Historical code, detailed logs and restoration evidence are in the recovery archive listed by the project README.

## Capturing

`python reference/capture.py <scene>` boots the Windows VM if needed, recreates the scene with real clicks/keys, and overwrites `screenshots/w7-<scene>.png`; `--check` instead fails unless the VM still renders that file pixel-for-pixel (clock and tray icons excluded). `menu`, `programs`, `search`, `calendar`, `volume` and `taskbar` reproduce exactly; `close-pressed`, `maximized` and `inactive` are frame states added for issue #9. `explorer` differs by 60 pixels: its reference also shows Start's keyboard-focus rectangle, a state the script doesn't recreate. Add a scene to `SCENES` and run without `--check` to create a new reference.

Scenes need `D:\native-bench.exe`: `reference/tools/make-tools-cd.sh` builds it (mingw-w64) and attaches it to the VM as a CD. Run its metrics collector by hand with `D:\native-bench.exe <new folder>`. `--scene` resets ClearType to contrast 1000. The references used that value, and any other contrast changes every glyph.

`w7-search.png` was recaptured with this script (the earlier file showed only the desktop), and `w7-taskbar.png` is new.

Menu-state scenes `desktop-view-submenu`, `explorer-view-submenu`, `desktop-view-checked-hover` and `explorer-view-radio-hover` capture genuine radio/check rasters, checked-row hover, submenu selection and disabled embossed text. All four were captured and passed `--check` twice each for #17/#18; `menu` and `taskbar` also passed unchanged. Their cleanup dismisses both menu levels even if the screenshot fails. The existing `explorer --check` 60px Start focus-cue limitation described above remains; it does not affect menu or frame comparisons.

`shutdown-menu` is the original issue #29 target (683165a). `shutdown-menu-selected` captures Restart selected by keyboard, with the pointer off the popup; both reproduce with `--check`. The owned popup is 109×142 at (340,607), with 20px rows and two 8px separator blocks. Tests exclude text (Wine Tahoma), the original pointer and the external compositor shadow (#30), not the frame or separator pixels.

For #43, the 16px `imageres.dll` group 3 folder composited on white matches Accessories at (6,479) and Games at (6,497) in `w7-programs.png` exactly. In a fresh capture, click Accessories at (55,487): the expanded folder at (6,299) and nested System Tools at (25,623) use the same art. The Classic applet ships the genuine 16px and 32px images for a 16-logical-pixel slot in its existing 18px rows. Plasma scales the artwork at fractional DPI; the lab's 150% check is not a native pixel comparison. KDE still supplies the groups and apps, and expansion still opens a sublist with Back rather than Windows' inline tree.

For #48, `explorer-jumplist --check` reproduced the 32×32 window icon at (117,763). Classic-demo and its Projects subfolder match `imageres.dll` group 3; Downloads, Computer, Network, Desktop and Libraries use their respective location icons. The closed pin and the jump list's Windows Explorer launch action instead use the blue-stand `explorer.exe` icon (`ICO_MYCOMPUTER`). KWin already gets Explorer's location icon for the window; Plasma 6.8 Wayland TaskManager's `DecorationRole` prefers the desktop-entry icon. The Classic taskbar therefore reads the window icon by compositor UUID only for running Explorer windows, retaining the app icon for launches.

For #41, `w7-explorer-empty-icons.png` and `w7-explorer-empty-details.png` are unchanged crops of the genuine Explorer file pane at (420,210)–(1020,280). Open Classic-demo → Documents (`explorer-back` scene), then use the toolbar View menu to choose Large Icons and Details in turn. At 96 DPI, the first text ink is 17px below the file pane top in Large Icons and 17px below the painted header in Details. A 120px narrower Details window retained the gap and shifted the message 60px left. The 150% Plasma regression checks logical placement, not a native 150% pixel match.

## Native fixture

Windows 7 Ultimate SP1 x64, Classic, 1280×800, 96 DPI, Never combine, large icons:

- Start menu: 405×461; visible taskbar: 44px (outer Win32 window is 46px and extends offscreen).
- Tahoma: 11px / 8.25pt; caption weight 700; ClearType type 2.
- Caption: 19px; frame: 4px; caption buttons: 18×18; favorite icons: 32px.
- ButtonFace: RGB 212,208,200; calendar/volume bodies: white.
- Native/B calendar: 331×243, rectangle (949,513)–(1280,756).
- Calendar focus oracle: `screenshots/w7-calendar-focus-even.png` is the unscaled `(1056,645)–(1079,660)` selected-day crop from genuine Windows 7 Classic at 96 DPI, opened on November 19, 2026. The adjacent November 18 cell produced the opposite phase, also present at `(1102,630)–(1125,645)` in `screenshots/w7-calendar.png`. The native dots have odd desktop `x + y` in both captures.

Control fixture mean absolute RGB difference, including text; lower is closer, not a fidelity percentage:

| Control | Qt Windows | XPlasma |
|---|---:|---:|
| Normal | 5.650 | 5.577 |
| Pressed | 8.151 | 8.445 |
| Disabled | 5.755 | 5.563 |
| Focused | 10.116 | 16.965 |
| Default | 20.311 | 8.304 |
| Edit | 38.188 | 38.489 |
| Combo | 44.075 | 18.975 |
| Scrollbar | 7.498 | 6.370 |

Both Qt fixtures verified focus and effective font/DPI. Qt Windows retains visible keyboard focus; XPlasma wins several samples. Neither is universally correct.

## Scope and risks

A used stock Plasma shell/components and XPlasma decoration; B used full AeroShell/SMOD. These are historical implementations, not the new project's chosen foundation. The Linux lab still contains the modified B stack.

IE8, Firefox/CSS and Geckium are different products. Geckium uses privileged AutoConfig JavaScript. Linux login/lock images are testing previews; native Windows logon/unlock worked. Notification balloons, control states, GTK/boot coverage, runtime warnings and full restoration remain unresolved. No host adoption or upstream submissions occurred. AeroShell prohibits AI contributions; Microsoft-derived images/fonts are not asserted redistributable.

UI sources: https://github.com/aeroshell-desktop/aerothemeplasma and https://github.com/Neo-Kitchenfox/Geckium (full notices archived). Earlier A's avatar was cropped from user966939's screenshot, CC BY-SA 3.0:
https://superuser.com/questions/1088518/glitched-start-menu-in-classic-theme-after-removing-windows-search

## VMs and private material

`qemu:///session`: `win7-classic-reference` (32 GiB sparse; offline, no shares/clipboard) and `archlinux-1-1` (65 GiB). Last verified shut off; Linux next boot uses B. Windows disk/media consumed approximately 10.5 GiB; no snapshots.

Media, credentials and exported fonts remain outside the project under `~/.local/share/libvirt/images/win7-reference-media/`. Never publish/read credential answers or bundle private fonts. No activation bypass; installation is not proof of a perpetual license.

ISO SHA-1: `36ae90defbad9d9539e649b193ae573b77a71c83` (3,320,903,680 bytes), archival copy verified against:
https://www.heidoc.net/php/myvsdump_details.php?id=P1241F46948Ax64Len
