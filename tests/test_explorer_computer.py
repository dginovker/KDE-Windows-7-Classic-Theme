#!/usr/bin/env python3
"""Use both real Computer entry points and a labelled, temporary lab mount."""
import argparse
from pathlib import Path
import time

from PIL import Image

from lab import VM, install, kwin_script, shot, toggle, user, vmctl, wait_for
from test_explorer import EXPLORER, captions, click, key, open_folder
from test_explorer_command_menus import words
from test_upgrade import output_name


def guest_root(command):
    rc, out, error = vmctl.run(VM, command, 60)
    assert rc == 0, (command, out, error)


def area(scale):
    x, y = (256, 120) if scale == 1 else (42, 45)
    return lambda a, b: (round(scale * (x + a)), round(scale * (y + b)))


def arrange(scale, title):
    x, y = area(scale)(0, 0)
    kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{EXPLORER}" && w.caption == "{title}") '
                f'{{ w.frameGeometry={{x:{round(x/scale)},y:{round(y/scale)},width:768,height:405}}; workspace.activeWindow=w; }}')


def capture(out, name):
    vmctl.pointer(VM, 1170, 712)
    time.sleep(.5)
    path = out / f'{name}.png'
    shot(path)
    return Image.open(path).convert('RGB')


def address(path, expected):
    key('KEY_LEFTALT', 'KEY_D')
    vmctl.type_text(VM, path + '\n')
    wait_for(lambda: expected in captions(), expected)


def run(out, scale, base):
    user(f'systemd-run --user --collect -q ~/.local/bin/win7-explorer {base}/Ordinary')
    wait_for(lambda: 'Ordinary' in captions(), 'ordinary folder')
    arrange(scale, 'Ordinary')
    pt = area(scale)
    click(pt(68, 310))  # Computer pane row
    wait_for(lambda: captions() == ['Computer'], 'pane Computer in the same window')
    browse = capture(out, 'pane-computer')
    assert 'Storage volumes' in words(browse, pt(176, 94) + pt(400, 120))
    click(pt(665, 42))
    vmctl.type_text(VM, 'W7VOLUME')
    single = capture(out, 'filtered-real-volume')
    label = words(single, pt(225, 118) + pt(430, 176))
    assert 'W7VOLUME' in label and 'free of' in label, label
    # The only remaining tile's meter has both the Classic ink and its white unfilled section.
    meter = single.crop(pt(233, 141) + pt(406, 150))
    assert (255, 255, 255) in meter.get_flattened_data() and (10, 36, 106) in meter.get_flattened_data(), label
    click(pt(210, 143))
    if 'Computer' in captions():  # keep activation independent of KDE's single-click preference
        key('KEY_ENTER')
    wait_for(lambda: captions() == ['Mount'], 'genuine mounted folder opened')
    assert 'Proof' in words(capture(out, 'mounted-folder'), pt(172, 185) + pt(285, 240))
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Computer'], 'Back returns to overview')
    capture(out, 'back-computer')
    key('KEY_LEFTALT', 'KEY_RIGHT')
    wait_for(lambda: captions() == ['Mount'], 'Forward opens mounted folder again')
    address('file:///', 'File System')
    assert 'Storage volumes' not in words(capture(out, 'explicit-root'), pt(176, 94) + pt(400, 120))
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: not captions(), 'pane Explorer closed')
    click((28, 780))
    # Start is 461 logical px high and its Computer item begins 251px down.
    click((round(310 * scale), 800 - round((44 + 461 - 267) * scale)))
    wait_for(lambda: captions() == ['Computer'], 'Classic Start launches the scheme handler')
    arrange(scale, 'Computer')
    assert 'Storage volumes' in words(capture(out, 'start-computer'), pt(176, 94) + pt(400, 120))
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: not captions(), 'Start Explorer closed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.installed:
        install(reset=False)
    output = output_name()
    toggle('current')
    before = user('xdg-mime query default inode/directory')
    base = user('mktemp -d /tmp/w7-volumes.XXXXXX')
    user(f'mkdir {base}/Mount {base}/Ordinary; kscreen-doctor output.{output}.scale.{args.scale}')
    try:
        guest_root(f'chmod 755 {base}; truncate -s 48M {base}/volume.img; '
                   f'mkfs.ext4 -q -F -L W7VOLUME {base}/volume.img && mount -o loop {base}/volume.img {base}/Mount && '
                   f'touch {base}/Mount/Proof.txt && chmod a+r {base}/Mount/Proof.txt')
        toggle('windows')
        run(args.out, args.scale, base)
        toggle('current')
        assert user('xdg-mime query default inode/directory') == before
        open_folder(f'{base}/Ordinary')
        wait_for(lambda: 'Ordinary' in captions('org.kde.dolphin'), 'current opens the same fixture in stock Dolphin')
        assert not captions(), 'current launched Classic Explorer'
        capture(args.out, 'current-dolphin')
    finally:
        toggle('current')
        user(f'pkill -x win7-explorer || true; kscreen-doctor output.{output}.scale.1')
        guest_root(f'if mountpoint -q {base}/Mount; then umount {base}/Mount || exit 1; fi; rm -rf {base}')


if __name__ == '__main__':
    main()
