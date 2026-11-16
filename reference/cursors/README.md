# Windows 7 default cursors

Extracted read-only from the offline `win7-classic-reference` VM's Windows/Cursors directory.
The active scheme is Windows default (Scheme Source 2). Its blank IBeam/Crosshair registry entries
use USER32 group cursors 101/103, reconstructed as CUR files with their original hotspots.

`python reference/tools/extract-cursors.py` (Pillow) reproducibly builds
`plasma/cursors/Win7-Classic-Cursors/`. All original 32/48px variants are retained.
ANI sequence, frame rates (in 1/60-second jiffies) and hotspots are preserved;
Xcursor timing rounds to integer milliseconds (wait: 50ms, working: 33ms).

Roles: aero_arrow = normal, aero_busy = wait, aero_working = background work,
aero_link = link, aero_ew/ns/nwse/nesw = resize, aero_move = move,
aero_unavail = prohibited, aero_helpsel = help, aero_pen = handwriting,
aero_up = alternate select, user32-ibeam = text, user32-crosshair = precision.
The converter lists all Xcursor/CSS/Qt/GTK aliases explicitly; Linux-only copy/alias/grab
roles use Windows normal/link/move selection, and zoom uses precision selection.

Xcursor cannot express Windows' background-inverting monochrome pixels. The I-beam/crosshair
therefore use the genuine pixels in black with a one-pixel white rim in adjacent transparent
pixels: pixel-identical on white fields, still visible (but non-inverting) on dark fields.
All Aero artwork uses its original RGBA pixels, converted to Xcursor's premultiplied ARGB.
Microsoft art is included by the project owner's explicit decision; no Microsoft fonts are included.
