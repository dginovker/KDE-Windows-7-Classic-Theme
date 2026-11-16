# Classic raster boundary

`ClassicPrimitives` is the single integer painter used by the QML module, Windows proxy style and Explorer. The palette uses explicit native roles: ButtonFace and 3DLight are separately named even though both are #d4d0c8. Never derive bevel shades from face brightness.

Supported DrawEdge subset: raised/sunken outer and inner borders, EDGE_RAISED/SUNKEN/ETCHED/BUMP, BF_LEFT/TOP/RIGHT/BOTTOM, BF_RECT/SOFT/FLAT/MIDDLE/ADJUST. Unsupported/contradictory flags terminate with the exact edge/flags. Coordinates use logical 96-DPI pixels and half-open fill bounds. Each selected side consumes one logical pixel per ring; the returned rectangle is the remaining content area. QPainter applies the device transform once; the QML item disables antialiasing. This preserves existing 100% goldens; it is **not** a claim of a 144-DPI native match (no genuine 144-DPI oracle is available).

Profiles intentionally differ:
- outer window/menu frame: EDGE_RAISED, face then highlight;
- soft push/caption button: EDGE_RAISED + BF_SOFT, highlight then face;
- client edge: EDGE_SUNKEN, shadow then dark shadow;
- notification area: BDR_SUNKENOUTER only (one pixel, never an extra dark ring);
- flat edit: black WS_BORDER equivalent, opt-in `classicFlatBorder` property, not a global QLineEdit change.

Focus dots have explicit origin parity. Check/radio raster and caption glyphs are measured from committed genuine 96-DPI references, not antialiased Qt paths. Text continues to use Wine Tahoma; Microsoft fonts are not shipped. Shell assets are reproducible with `python reference/tools/extract-shell-art.py`; the user picture content is independent of its native frame.

The style wraps Qt Windows explicitly; only proven differences are overridden. Unmodified controls inherit Windows style behavior, with the complete native application palette. The application/system palette is enforced while this style is active, including late KDE palette notifications; unpolish restores the destination palette. Explicit widget palettes and widgets with their own painting are not forcibly rewritten. GTK3 remains its separate CSS theme; GTK4, libadwaita, browser-rendered content and non-Qt renderers do not consume this Qt layer.

## Discovery and diagnosis

Qt discovers style plugins from startup library paths. Therefore `Win7Classic` is **system-wide only** (`/usr/lib/qt6/plugins/styles/libwin7classicstyle.so`), installed by the package. No environment injection or session restart is used. Development installation refuses a missing style and names `cd packaging && makepkg -si`. VM tests atomically replace that plugin with the current build through the lab root agent. The QML module is user-local or packaged next to the theme data and imported by relative package path, including by KWin (no global QML import environment).

`win7-classic-probe --available` instantiates the style before any switch. After appearance is applied the probe verifies effective style and every palette role/group, logging JSON with Qt, DPR, font and colors to `~/.local/state/win7-classic/switch.log`. A failed effective check follows the normal rollback path. Older saved Windows profiles cannot select the old generic Windows style.

`tests/test_classic_widgets.py` compares actual live-switched Qt widgets against `controls-native-client.png` with label-only masks, saving original crops and binary differences. Existing Start, taskbar and frame tests exercise the same renderer through actual Plasma/KWin package imports. See issue #29 for the intentionally retained KDE confirmation on the shutdown arrow. Additional native atlases (unused edge/state combinations, pressed shutdown halves, disabled caption glyphs, 144 DPI and like-for-like inactive file selection) still need genuine reference captures; do not invent goldens from our output.

Mixed (indeterminate) checkboxes are a distinct state: GrayText tick on Classic stipple, not the enabled checked raster. The supplied native benchmark has no mixed-state control, so the regression asserts distinction/roles only; it is not a genuine mixed-state golden. The full normal horizontal scrollbar crop (end buttons, thumb and track) is now compared unmasked against that benchmark; its 17px control paints a 16px face with a shared leading thumb/button column.
