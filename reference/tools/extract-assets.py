#!/usr/bin/env python3
"""Extract the genuine Windows 7 art the project ships, from the reference VM.

  virt-copy-out --ro -a ~/.local/share/libvirt/images/win7-classic-reference.qcow2 \\
      /Windows/System32/imageres.dll /Windows/System32/shell32.dll /Windows/System32/ExplorerFrame.dll DLLDIR
  python reference/tools/extract-assets.py DLLDIR

Writes explorer/assets/ (Explorer's chrome) and plasma/icons/Win7-Classic/ (the Windows-mode icon theme).
Back/Forward are cropped from reference screenshots because Explorer's Classic look renders them differently from
its raw bitmaps; the hover/pressed captures are taken twice with the pointer on opposite rims and merged.
"""
import io
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / 'reference/screenshots'
ASSETS = ROOT / 'explorer/assets'
THEME = ROOT / 'plasma/icons/Win7-Classic'


def resources(dll, kind, name, out):
    """wrestool-extracted resource file for one resource (kind 14 = icon group, 2 = bitmap)."""
    subprocess.run(['wrestool', '-x', '-t', str(kind), '-n', str(name), '-o', str(out), str(dll)], check=True)
    found = list(Path(out).glob(f'*_{kind}_{name}.*'))
    if len(found) != 1:
        raise SystemExit(f'{dll.name}: resource type {kind} name {name} not found')
    return found[0]


def icon_sizes(path):
    """{size: RGBA image} for every 32-bit (or PNG) image in an .ico; lower bit depths are skipped."""
    data = path.read_bytes()
    count = struct.unpack_from('<H', data, 4)[0]
    sizes = {}
    for i in range(count):
        size, off = struct.unpack_from('<II', data, 6 + 16 * i + 8)
        blob = data[off:off + size]
        if blob[:8] == b'\x89PNG\r\n\x1a\n':
            image = Image.open(io.BytesIO(blob)).convert('RGBA')
        else:
            header, width, height, _, bits = struct.unpack_from('<IiiHH', blob, 0)
            if bits != 32:
                continue
            height //= 2  # the height covers the AND mask too
            image = Image.frombuffer('RGBA', (width, height), blob[header:header + width * height * 4], 'raw', 'BGRA', 0, -1).copy()
        sizes[image.width] = image
    return sizes


def bitmap(path):
    """A 32-bit .bmp keeping its alpha channel, which PIL drops."""
    data = path.read_bytes()
    off = struct.unpack_from('<I', data, 10)[0]
    width, height, _, bits = struct.unpack_from('<iiHH', data, 18)
    if bits != 32:
        raise SystemExit(f'{path.name}: expected a 32-bit bitmap, got {bits}-bit')
    return Image.frombuffer('RGBA', (width, abs(height)), data[off:off + width * abs(height) * 4], 'raw', 'BGRA', 0,
                            -1 if height > 0 else 1).copy()


def shot(name):
    return Image.open(SHOTS / f'w7-{name}.png').convert('RGB')


def without_pointer(name, pointer, other, normal):
    """`name` with the pointer's footprint (tip at `pointer`) filled from `other`, where the pointer was elsewhere.

    From y 171 down, `other` shows its hover tooltip, so that part of the footprint (the button's bottom-right rim
    and the capsule below) comes from `normal`.
    """
    image, fill = shot(name), shot(other)
    x, y = pointer
    box = (x - 1, y - 1, x + 14, 171)
    image.paste(fill.crop(box), box[:2])
    below = (x - 1, 171, x + 14, 177)
    image.paste(shot(normal).crop(below), below[:2])
    return image


# Explorer's Back/Forward strip: x 262-291 is Back, 292-333 Forward plus the recent-pages arrow; rows 145-176.
BACK, FORWARD = (262, 145, 292, 177), (292, 145, 334, 177)
NAV = {
    'back-disabled': (shot('explorer'), BACK),
    'back-normal': (shot('explorer-back'), BACK),
    'back-hot': (without_pointer('explorer-back-hot', (285, 167), 'explorer-back-hot-ul', 'explorer-back'), BACK),
    'back-pressed': (without_pointer('explorer-back-pressed', (285, 167), 'explorer-back-pressed-ul', 'explorer-back'), BACK),
    'forward-disabled': (shot('explorer'), FORWARD),
    'forward-disabled-history': (shot('explorer-back'), FORWARD),
    'forward-normal': (shot('explorer-forward'), FORWARD),
    'forward-hot': (without_pointer('explorer-forward-hot', (313, 167), 'explorer-forward-hot-ul', 'explorer-forward'), FORWARD),
    'forward-pressed': (without_pointer('explorer-forward-pressed', (313, 167), 'explorer-forward-pressed-ul', 'explorer-forward'), FORWARD),
    # Refresh as Classic Explorer draws it inside the address box.
    'refresh': (shot('explorer'), (748, 151, 769, 170)),
}

# (dll, icon group) -> Explorer asset name; all sizes are kept so high-DPI screens get real pixels.
ICONS = {
    ('imageres', 3): 'folder', ('imageres', 1024): 'favorites', ('imageres', 110): 'desktop',
    ('imageres', 184): 'downloads', ('imageres', 117): 'recent-places', ('imageres', 1023): 'libraries',
    ('imageres', 1002): 'library-documents', ('imageres', 1004): 'library-music', ('imageres', 1003): 'library-pictures',
    ('imageres', 1005): 'library-videos', ('imageres', 109): 'computer', ('imageres', 25): 'network',
    ('imageres', 99): 'help', ('shell32', 16757): 'preview-pane',
    ('shell32', 63001): 'view-extra-large', ('shell32', 63008): 'view-large', ('shell32', 63009): 'view-medium',
    ('shell32', 63010): 'view-small', ('shell32', 63011): 'view-list', ('shell32', 62998): 'view-details',
}

# Windows-mode icon theme: freedesktop names -> asset. KDE apps elsewhere keep Breeze for everything else.
THEME_ICONS = {
    'folder': 'folder', 'inode-directory': 'folder', 'folder-open': 'folder', 'user-home': 'folder',
    'folder-documents': 'folder', 'folder-music': 'folder', 'folder-pictures': 'folder', 'folder-videos': 'folder',
    'folder-templates': 'folder', 'folder-publicshare': 'folder', 'folder-download': 'downloads',
    'folder-downloads': 'downloads', 'user-desktop': 'desktop', 'folder-desktop': 'desktop',
    'document-open-recent': 'recent-places', 'computer': 'computer', 'network-workgroup': 'network',
}


def main():
    dlls = Path(sys.argv[1])
    shutil.rmtree(ASSETS, ignore_errors=True)
    shutil.rmtree(THEME, ignore_errors=True)
    ASSETS.mkdir(parents=True)
    for name, (image, box) in NAV.items():
        image.crop(box).save(ASSETS / f'{name}.png')

    icons = {}
    with tempfile.TemporaryDirectory() as tmp:
        for (dll, group), name in ICONS.items():
            sizes = icon_sizes(resources(dlls / f'{dll}.dll', 14, group, tmp))
            if 256 in sizes and 96 not in sizes:
                sizes[96] = sizes[256].resize((96, 96), Image.LANCZOS)  # Explorer's Large Icons size
            icons[name] = sizes
            for size, image in sizes.items():
                image.save(ASSETS / f'{name}-{size}.png')
        # Search button: ExplorerFrame bitmaps 307 (normal) and 308 (hot), first 21x21 tile.
        for number, state in ((307, 'normal'), (308, 'hot')):
            bitmap(resources(dlls / 'ExplorerFrame.dll', 2, number, tmp)).crop((0, 0, 21, 21)).save(ASSETS / f'search-{state}.png')

    sizes = sorted({size for name in set(THEME_ICONS.values()) for size in icons[name]})
    THEME.mkdir(parents=True)
    (THEME / 'index.theme').write_text(
        '[Icon Theme]\nName=Windows 7 Classic\nComment=Windows 7 folder and place icons; everything else comes from Breeze\n'
        'Inherits=breeze,hicolor\nDirectories=' + ','.join(f'{s}x{s}/places' for s in sizes) + '\n'
        + ''.join(f'\n[{s}x{s}/places]\nSize={s}\nType=Fixed\nContext=Places\n' for s in sizes))
    for icon, asset in THEME_ICONS.items():
        for size, image in icons[asset].items():
            (THEME / f'{size}x{size}/places').mkdir(parents=True, exist_ok=True)
            image.save(THEME / f'{size}x{size}/places/{icon}.png')
    (ASSETS / 'assets.qrc').write_text('<RCC><qresource prefix="/explorer">\n' + ''.join(
        f'  <file>{p.name}</file>\n' for p in sorted(ASSETS.glob('*.png'))) + '</qresource></RCC>\n')
    print(f'{len(list(ASSETS.glob("*.png")))} Explorer assets, {len(list(THEME.rglob("*.png")))} theme icons')


if __name__ == '__main__':
    main()
