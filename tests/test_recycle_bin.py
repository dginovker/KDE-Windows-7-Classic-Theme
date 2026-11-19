#!/usr/bin/env python3
"""Run only in the disposable KDE lab: pristine tester, candidate installed via lab.install().

Requires an empty KIO Trash, clear stock Folder View and a single 1280×800 output. The
script seeds once and then reuses the profile at both scales. It removes only its own
fixture; Empty Trash with confirmation is checked separately by hand in the handoff.
"""
import argparse
import json
import re
import time
from functools import cache, partial
from pathlib import Path

from lab import (
    ROOT,
    VM,
    activate,
    digest,
    install,
    kwin_script,
    shot,
    toggle,
    user,
    vmctl,
    wait_for,
    windows,
)
from PIL import Image, ImageChops, ImageStat

APPLETS = '~/.config/plasma-org.kde.plasma.desktop-appletsrc'
MIMES = 'sha256sum ~/.config/mimeapps.list 2>/dev/null || true'
DESKTOP_FILES = ('cd "$(/usr/lib/qt6/bin/qtpaths6 --writable-path DesktopLocation)" && '
                 'find . -mindepth 1 -type f -exec sha256sum -- {} + | sort')
KIO = 'QT_QPA_PLATFORM=offscreen kioclient --noninteractive'
BG = (58, 110, 165, 255)


def instance():
    config = user(f'cat {APPLETS}')
    all_trash = list(re.finditer(r'^plugin=org\.kde\.plasma\.trash$', config, re.MULTILINE))
    if not all_trash:
        return None
    assert len(all_trash) == 1, 'more than one Trash widget'
    group = config[:all_trash[0].start()].rsplit('\n[', 1)[-1].splitlines()[0]
    match = re.fullmatch(r'Containments\]\[(\d+)\]\[Applets\]\[(\d+)\]', group)
    assert match, group
    containment, applet = match.groups()
    body = config.split(f'[Containments][{containment}]\n', 1)[1].split('\n[', 1)[0]
    assert 'plugin=org.kde.plasma.folder' in body, body
    return containment, applet


@cache
def templates(full, scale):
    name = 'user-trash-full' if full else 'user-trash'
    result = []
    for source in (48, 256):
        asset = ROOT / f'plasma/icons/Win7-Classic/{source}x{source}/places/{name}.png'
        # Allow the two genuine source sizes the icon loader can choose at fractional DPI.
        icon = Image.open(asset).convert('RGBA').resize((round(48 * scale),) * 2, Image.Resampling.LANCZOS)
        glyph = Image.alpha_composite(Image.new('RGBA', icon.size, BG), icon).convert('RGB')
        result.append(glyph.crop(tuple(round(v * scale) for v in (10, 8, 38, 38))))
    return result


def art_score(tile, full, scale):
    best = float('inf')
    for expected in templates(full, scale):
        w, h = expected.size
        for y in range(round(8 * scale), round(30 * scale)):
            for x in range(round(13 * scale), round(45 * scale)):
                crop = tile.crop((x, y, x+w, y+h))
                difference = ImageStat.Stat(ImageChops.difference(crop, expected)).mean
                best = min(best, sum(difference) / 3)
    return best


def capture(out, name, scale, full):
    path = out / f'{name}.png'
    shot(path)
    image = Image.open(path).convert('RGB')
    assert image.size == (1280, 800), image.size
    tile = image.crop((0, 0, round(80 * scale), round(80 * scale)))
    tile.save(out / f'{name}-crop.png')
    actual, other = (art_score(tile, state, scale) for state in (full, not full))
    if actual < 22 and actual + 5 < other:
        print(f'{name} at {scale:g}x: correct art distance {actual:.1f}; other state {other:.1f}')
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    oracle = ROOT / 'reference/screenshots/w7-desktop-context.png'
    Image.open(oracle).crop((0, 0, 80, 80)).save(out / 'genuine-1x-empty-crop.png')
    install(reset=False)
    assert user('~/.local/bin/win7-classic status') == 'current'
    user('test ! -e ~/.local/state/win7-classic/profiles/windows')
    assert user(f'{KIO} ls trash:/') == '.', 'test requires a pristine, empty KIO Trash'
    user('mkdir -p -- "$(/usr/lib/qt6/bin/qtpaths6 --writable-path DesktopLocation)"')
    assert not instance(), 'current already has a Trash widget'
    output = json.loads(user('kscreen-doctor -j'))['outputs']
    assert len(output) == 1, output
    output = output[0]
    sid = f'output.{output["name"]}.scale'
    fixture = user('mktemp "$HOME/w7-bin-XXXXXX.txt"')
    name = Path(fixture).name
    assert re.fullmatch(r'w7-bin-[a-zA-Z0-9]+\.txt', name), name

    user('systemd-run --user --collect -q kate -n')
    wait_for(lambda: 'org.kde.kate' in windows(), 'Kate opens')
    activate('org.kde.kate')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_N')
    vmctl.type_text(VM, 'unsaved recycle bin test')
    assert '*' in windows()['org.kde.kate'][0], 'work fixture was not edited'
    pid = user('pgrep -x kwin_wayland; pgrep -x kate')
    kwin_script('for (const w of workspace.windowList()) if (w.resourceClass == "org.kde.kate") w.minimized = true;')
    assert windows()['org.kde.kate'][2], 'Kate was not minimized'
    seeded = None
    try:
        for scale in (1, 1.5):
            user(f'kscreen-doctor {sid}.{scale}')
            time.sleep(2)
            folder = out / f'{scale:g}x'
            folder.mkdir(exist_ok=True)
            current = (digest(), user(MIMES), user(DESKTOP_FILES))
            shot(folder / 'current-before.png')
            toggle('windows')
            assert instance(), 'fresh Windows desktop contains no stock Trash widget'
            if seeded is None:
                seeded = instance()
            assert instance() == seeded, 'Windows Trash widget was replaced or duplicated'
            vmctl.pointer(VM, 520, 400)
            wait_for(partial(capture, folder, 'empty', scale, False), 'correct empty icon')
            user(f'set -e; printf "disposable fixture\\n" > {fixture}; {KIO} move {fixture} trash:/; test ! -e {fixture}')
            trashed = user(f'{KIO} ls trash:/ | grep -F -- {name}')
            assert trashed == f'0-{name}', trashed
            wait_for(partial(capture, folder, 'full', scale, True), 'correct full icon')
            vmctl.pointer(VM, round(40 * scale), round(25 * scale), 'left')
            wait_for(lambda: 'Trash' in windows().get('org.kde.dolphin', ('',))[0],
                     'desktop widget opens real Dolphin Trash')
            shot(folder / 'real-trash.png')
            vmctl.keys(VM, 'KEY_LEFTALT', 'KEY_F4')
            wait_for(lambda: 'org.kde.dolphin' not in windows(), 'Dolphin closes')
            user(f'{KIO} remove trash:/{trashed}')
            wait_for(partial(capture, folder, 'empty-again', scale, False), 'live return to empty icon')
            toggle('current')
            assert not instance(), 'Trash widget leaked into current mode'
            assert (digest(), user(MIMES), user(DESKTOP_FILES)) == current, 'current config or Desktop changed'
            assert user('pgrep -x kwin_wayland; pgrep -x kate') == pid, 'work/compositor process restarted'
            assert '*' in windows()['org.kde.kate'][0], 'unsaved Kate document lost'
            shot(folder / 'current-after.png')
    finally:
        toggle('current')
        user(f'kscreen-doctor {sid}.{output["scale"]}; rm -f -- {fixture}')
    print('Both scales: real Trash and live artwork, one persistent Windows widget, current and work intact.')


if __name__ == '__main__':
    main()
