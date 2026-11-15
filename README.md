# Windows 7 Classic for KDE Wayland

Build an independently maintained Classic UI with a live return to the user's current desktop. This is research and planning, not an installable theme.

- `PROJECT-DIRECTION.md`: confirmed goals, proposed boundaries and first milestone.
- `reference/gallery.html`: genuine Windows 7 beside the earlier A/B experiments; click images for original pixels.
- `reference/README.md`: measurements, VM provenance and unresolved risks.
- Check the gallery: `python reference/verify.py` (requires Pillow).

No host theme, session or boot changes are authorized by these artifacts. Preserve unsaved work; Linux authentication and reliable apply/restore remain unverified. Work is tracked in GitHub issues; the live toggle is not implemented yet.

## Recovery

Old checkouts, experiments, logs and scripts were removed from the working tree, not discarded. Their complete verified archive and cleanup manifests are outside this project:

`/home/wacket/.local/state/windows7classic-cleanup/20261114T212841Z/`

Restore `original.tar.zst` into a separate directory, never over this project. VMs, installation media, credentials and private fonts were not moved or modified.
