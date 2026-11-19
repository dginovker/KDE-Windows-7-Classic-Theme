#!/usr/bin/env python3
"""Extract only observed Classic tray states, without adding icon-theme aliases."""
import argparse
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
CROP = (1100, 756, 1280, 800)
FACE = (212, 208, 200)
SHA = {
    'target': '14abfc991a2d24882678d71d1dfb7be6f39bb3647e584d95d49342f61fc2db5b',
    'initial': '001eaff093dd3d8b7efae8f6fe53d143e033dbaec3542a71de0417152e92ffb4',
    'low': '803dd69d08d19b4d770e04fb4d99d08eca27da335736429eab7bf7c64dd315c3',
    'high': '6ee4f01cbd80a5c13ff805a8c57935286f451e20994b2b9b50e304688570ff7c',
    'muted': '41d34e23d03ee15636c3a61296ace3be5f0e6a09bde7827a32f890b398ffb02f',
}


def capture(name, path):
    if sha256(path.read_bytes()).hexdigest() != SHA[name]:
        raise ValueError(f'Unrecognized {name} reference: {path}')
    with Image.open(path) as png:
        assert png.mode == 'RGB'
        return png.copy() if name == 'target' else png.crop(CROP)


def extract(source, box, out, name):
    tile = source.crop(box)
    rgba = tile.convert('RGBA')
    # Do not reverse-engineer alpha: preserve the observed composited pixels on ButtonFace.
    rgba.putalpha(Image.frombytes('L', tile.size, bytes(0 if rgb == FACE else 255 for rgb in tile.get_flattened_data())))
    layered = Image.new('RGBA', tile.size, (*FACE, 255))
    layered.alpha_composite(rgba)
    assert layered.convert('RGB').tobytes() == tile.tobytes(), name
    rgba.save(out / f'{name}.png')
    return rgba


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backlog', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--zero', required=True, type=Path, help='Genuine 1280×800 zero-volume capture')
    args = parser.parse_args()
    target = capture('target', ROOT / 'reference/screenshots/w7-notification-area.png')
    panes = {name: capture(name, args.backlog / f'w7-{name}.png') for name in SHA if name != 'target'}
    speaker = (77, 15, 93, 31)
    assert all(panes[name].crop(speaker).tobytes() == target.crop(speaker).tobytes() for name in ('initial', 'low', 'high'))
    assert speaker[0] - 53 == 53 - 29 == 24
    args.output.mkdir(parents=True, exist_ok=True)
    normal = extract(target, speaker, args.output, 'speaker-unmuted')
    muted = extract(panes['muted'], speaker, args.output, 'speaker-muted')
    assert normal.tobytes() != muted.tobytes()
    if sha256(args.zero.read_bytes()).hexdigest() != 'ffb403d72a2bb483bc37617096d28ec9b8e93eebb16604ab8d7f6770e02b1b54':
        raise ValueError('Unrecognized zero-volume reference')
    with Image.open(args.zero) as png:
        zero = extract(png.convert('RGB'), (1177, 771, 1193, 787), args.output, 'speaker-zero')
    assert zero.tobytes() not in (normal.tobytes(), muted.tobytes())
    ethernet = (53, 15, 69, 31)
    assert all(p.crop(ethernet).tobytes() == target.crop(ethernet).tobytes() for p in panes.values())
    extract(target, ethernet, args.output, 'ethernet-disconnected')
    marker = extract(target, (13, 17, 18, 25), args.output, 'show-hidden')
    assert marker.size == (5, 8) and marker.getbbox() == (0, 0, 5, 8)
    assert set(marker.get_flattened_data()) - {(*FACE, 0)} == {(0, 0, 0, 255)}
    print('Verified genuine 24 px cells, 5×8 marker, identical unmuted speaker across volume samples, distinct mute, and disconnected Ethernet')


if __name__ == '__main__':
    main()
