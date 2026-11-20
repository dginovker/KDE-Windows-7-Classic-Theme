#!/usr/bin/env python3
"""Exercise installed packages in the stock lab; supply the Arch package to test."""
import argparse
import base64
import difflib
import json
import re
import shlex
import time
from pathlib import Path

from PIL import Image

from lab import VM, digest, kwin_query, shot, toggle, user, vmctl, wait_for
from test_tray import REFERENCE, ocr

NAME = 'plasma-org.kde.plasma.desktop-appletsrc'
STATE = '~/.local/state/win7-classic'
SAVED = f'{STATE}/profiles/windows/{NAME}'
LIVE = f'~/.config/{NAME}'
NETWORK = b'org.kde.plasma.networkmanagement'
COLD_LAYOUT = Path(__file__).with_name('fixtures') / 'tray-popup-cold-appletsrc'
CLIPBOARD = b'org.kde.plasma.clipboard'
STOCK = 'org.kde.plasma.systemtray'
CLASSIC = 'org.win7classic.tray'


def key(*keys):
    vmctl.keys(VM, *('KEY_' + k for k in keys))


def root(script):
    code, out, err = vmctl.run(VM, 'set -eu\n' + script, 90)
    print(out, err, end='')
    assert code == 0, (script, code)


def install(package):
    vmctl.transfer(VM, 'put', str(package), '/tmp/w62-install.pkg.tar.zst')
    root('sha256sum /tmp/w62-install.pkg.tar.zst; pacman -U --noconfirm /tmp/w62-install.pkg.tar.zst; '
         'pacman -Qkk win7-classic; rm /tmp/w62-install.pkg.tar.zst')


def raw(path):
    return base64.b64decode(user(f'base64 -w0 {path}'))


def profile_hashes():
    return user(f'cd {STATE}/profiles; find current windows -type f -print0 | sort -z | xargs -0 sha256sum')


def groups(data):
    return dict(re.findall(rb'(?m)^(\[[^\n]+\])\n([^\[]*)', data))


def settings(data, plugin):
    all_groups = groups(data)
    group, = [g for g, lines in all_groups.items()
              if re.fullmatch(rb'\[Containments\]\[\d+\]\[Applets\]\[\d+\]\[Applets\]\[\d+\]', g)
              and b'plugin=' + plugin in lines.splitlines()]
    return group + b'[Configuration]', all_groups.get(group + b'[Configuration]', b'')


def sizes(data, plugin):
    return dict(re.findall(rb'(?m)^popup(Width|Height)=([0-9]+)$', settings(data, plugin)[1]))


def panels():
    return user("qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript " + shlex.quote(
        r'const ids = []; for (const p of panels()) for (const w of p.widgets()) ids.push(w.type + ":" + w.id); '
        r'print(ids.join("\n"));')).splitlines()


def popup():
    rows = kwin_query('for (const w of workspace.windowList()) if (w.resourceClass === "org.kde.plasmashell" && '
                      'w.caption === "plasmashell" && !w.popupWindow && !w.notification) { const g = w.frameGeometry; emit(g.x,g.y,g.width,g.height); }')
    assert len(rows) <= 1, rows
    return tuple(map(float, rows[0])) if rows else None


def network_cell(out, scale):
    # The connected lab uses KDE network artwork. Locate the genuine speaker and the preceding tray cell.
    tile = Image.open(REFERENCE).convert('RGB').crop((77, 15, 93, 31))
    w = h = round(16*scale)
    horizontal = tile.resize((w, 16), Image.Resampling.BOX)
    # Fractional placement can give either vertical sampling phase, but every row must match.
    artwork = {tile.tobytes()} if scale == 1 else {
        b''.join(horizontal.crop((0, j, w, j+1)).tobytes()
                 for j in ((2*y+phase)//3 for y in range(h))) for phase in (0, 1)
    }
    path = out / 'tray.png'
    shot(path)
    image = Image.open(path).convert('RGB')
    hits = [(x+w//2, y+h//2) for x in range(1100, 1190) for y in range(750, 777)
            if image.crop((x, y, x+w, y+h)).tobytes() in artwork]
    assert len(hits) == 1, hits
    x, y = hits[0]
    print(f'genuine speaker tile at {(x,y)} matches every pixel at {scale}')
    return x-round(24*scale), y


def move_and_release(x, y, button):
    width, height = vmctl.screen_size(VM)
    assert 0 <= x < width and 0 <= y < height
    # Send physical motion and release in the same QEMU input report, with no settling interval.
    events = [{'type': 'abs', 'data': {'axis': axis, 'value': round((v + 0.5) * 32768 / limit)}}
              for axis, v, limit in (('x', x, width), ('y', y, height))]
    events.append({'type': 'btn', 'data': {'button': button, 'down': False}})
    vmctl.virsh('qemu-monitor-command', VM, json.dumps({'execute': 'input-send-event', 'arguments': {'events': events}}))


def set_meta(down):
    vmctl.virsh('qemu-monitor-command', VM, json.dumps({'execute': 'input-send-event', 'arguments': {'events': [
        {'type': 'key', 'data': {'key': {'type': 'qcode', 'data': 'meta_l'}, 'down': down}}
    ]}}))
    time.sleep(0.12)


def resize_check(out, scale, before):
    toggle('windows', packaged=True)
    point = network_cell(out, scale)

    def open_network():
        assert popup() is None
        vmctl.pointer(VM, *point, 'left')
        wait_for(popup, 'real network popup')
        return popup()

    def close_network():
        key('ESC')
        wait_for(lambda: popup() is None, 'Escape closes the real network popup')

    initial = open_network()
    path = out / 'opened.png'
    shot(path)
    x, y, w, _ = initial
    crop = tuple(round(v*scale) for v in (x, y, x+w, y+115))
    words = {word for word, _ in ocr(Image.open(path).convert('RGB'), crop)}
    assert {'Connected', 'Wired', 'Disconnect'} <= words, words
    close_network()
    toggle('current', packaged=True)
    saved = raw(SAVED)
    (out / 'windows-after-dismiss.ini').write_bytes(saved)
    assert_size_only(before, saved)
    print(f'ordinary dismissal uses AppletPopup save-on-hide: {initial}, {sizes(saved, NETWORK)}')

    for name, button, distance in (('left-edge', 'left', 55), ('right-edge', 'right', -40), ('kwin-modifier', 'right', 45)):
        toggle('windows', packaged=True)
        geom = open_network()
        x, y, w, h = geom
        modifier = name == 'kwin-modifier'
        # KWin's stock Meta+right Resize starts from the interior; the other two
        # use Plasma's own top-left corner hit test.
        px, py = (x+w/4, y+h/4) if modifier else (x+2, y+2)
        px, py = round(px*scale), round(py*scale)
        vmctl.pointer(VM, px, py)
        if modifier:
            set_meta(True)
        try:
            vmctl.button(VM, button, True)
            for delta in (10, 30):
                dx = round((delta if distance > 0 else -delta)*scale)
                vmctl.pointer(VM, px-dx, py-dx)
            delta = round(distance*scale)
            move_and_release(px-delta, py-delta, button)
        finally:
            vmctl.button(VM, button, False)
            if modifier:
                set_meta(False)

        def reached_target():
            final = popup()
            return final if final and all(abs(new-old-distance) < 2
                                          for old, new in zip(geom[2:], final[2:])) else None

        wait_for(reached_target, f'KWin applies the final {name} move')
        resized = reached_target()
        assert resized, (name, geom, popup())
        shot(out / f'{name}-resized.png')
        close_network()
        toggle('current', packaged=True)
        after = raw(SAVED)
        (out / f'windows-after-{name}.ini').write_bytes(after)
        assert_size_only(before, after)
        assert sizes(saved, NETWORK) != sizes(after, NETWORK), (name, sizes(after, NETWORK))
        toggle('windows', packaged=True)
        restored = open_network()
        shot(out / f'{name}-reopened.png')
        assert restored == resized, (name, resized, restored)
        close_network()
        toggle('current', packaged=True)
        assert raw(SAVED) == after, 'reopening without resizing changed the user-set size'
        print(f'{name}: {geom} → {resized}; reopened {restored}, saved {sizes(after, NETWORK)}')
        saved = after


def assert_size_only(before, after):
    group, contents = settings(after, NETWORK)
    assert re.fullmatch(rb'popupHeight=\d+\npopupWidth=\d+\n\n', contents), contents
    assert after.replace(group + b'\n' + contents, b'', 1) == before, 'changed more than the size section'


def main(out, scale, target):
    out.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    assert user('/usr/bin/win7-classic status') == 'current'
    backup = '~/.local/state/w62-test-backup'
    user(f'''set -eu
    test -f {SAVED} && test -d {STATE}/profiles/current
    mkdir {backup}
    cp -a {STATE} {LIVE} ~/.config/plasmashellrc {backup}/
    kscreen-doctor output.1.scale.{scale}
    ''')
    try:
        # Activating a freshly seeded profile or giving the session UI input before
        # the round trip concealed the startup regression. Replay the captured layout.
        activity, = kwin_query('emit(workspace.currentActivity);')
        assert re.fullmatch(r'[0-9a-f-]{36}', activity[0]), activity
        fixture = COLD_LAYOUT.read_bytes().replace(b'@ACTIVITY@', activity[0].encode())
        layout = base64.b64encode(fixture).decode()
        user(f'printf %s {shlex.quote(layout)} | base64 -d > {SAVED}')
        before = raw(SAVED)
        assert before == fixture
        assert not sizes(before, NETWORK)
        assert sizes(before, CLIPBOARD) == {b'Width': b'393', b'Height': b'283'}
        assert settings(before, NETWORK)[0] + b'\n' not in before
        (out / 'windows-before-install.ini').write_bytes(before)
        hashes, current = profile_hashes(), digest()
        (out / 'profiles-before.txt').write_text(hashes + '\n')
        install(target)
        (out / 'windows-after-install.ini').write_bytes(raw(SAVED))
        assert raw(SAVED) == before and profile_hashes() == hashes and digest() == current
        print('installation preserved both profiles and live Current files')
        toggle('windows', packaged=True)
        time.sleep(4)  # Allow the hosted applets' startup and KConfig writes to settle.
        active = raw(LIVE)
        (out / 'windows-live-after-activation.ini').write_bytes(active)
        toggle('current', packaged=True)
        after = raw(SAVED)
        (out / 'windows-after-round-trip.ini').write_bytes(after)
        (out / 'profiles-after.txt').write_text(profile_hashes() + '\n')
        if after != before:
            (out / 'windows.diff').write_bytes(b''.join(difflib.diff_bytes(difflib.unified_diff,
                before.splitlines(True), after.splitlines(True), b'before', b'after')))
        assert after == before, f'untouched saved Windows layout differs at {scale}; see windows.diff'
        assert active == before, f'Windows activation changed live layout at {scale}'
        assert digest() == current and any(w.startswith(STOCK + ':') for w in panels())
        print(f'{scale}: exact saved layout before install, after activation and after an untouched round trip')
        resize_check(out, scale, before)
        assert digest() == current
    finally:
        if user('/usr/bin/win7-classic status') == 'windows':
            toggle('current', packaged=True)
        user(f'''set -eu
        kscreen-doctor output.1.scale.1
        systemctl --user stop plasma-plasmashell
        rm -rf {STATE}
        mv {backup}/win7-classic {STATE}
        mv {backup}/{NAME} {backup}/plasmashellrc ~/.config/
        rmdir {backup}
        systemctl --user reset-failed plasma-plasmashell
        systemctl --user start plasma-plasmashell
        ''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), required=True)
    args = parser.parse_args()
    main(args.outdir, args.scale, args.target)
