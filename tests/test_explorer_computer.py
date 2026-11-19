#!/usr/bin/env python3
"""Use both real Computer entry points and a labelled, temporary lab mount."""
import argparse
from pathlib import Path
import time

from PIL import Image

from lab import VM, clipboard, executable, explorer_identity, install, kwin_script, shot, toggle, user, vmctl, wait_for
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


def start_computer(out, scale, exe):
    click((round(28 * scale), 800 - round(20 * scale)))
    top = 800 - round((44 + 461) * scale)
    name = tuple(round(p * scale) for p in (263, 251, 394, 283))
    menu = capture(out, 'start-menu')
    assert 'Computer' in words(menu, (name[0], top + name[1], name[2], top + name[3])), 'Start Computer item was not shown'
    click((round(310 * scale), top + round(267 * scale)))
    wait_for(lambda: len(captions()) == 1, 'Classic Start launched Explorer')
    title, = captions()
    arrange(scale, title)
    identity(out, 'start-executable', exe)
    return title, capture(out, 'start-computer')


def identity(out, label, exe):
    folder = out / label
    folder.mkdir(exist_ok=True)
    explorer_identity(int(user('pgrep -x win7-explorer')), exe, folder)


def run(out, scale, base, exe):
    user(f'systemd-run --user --collect -q {exe} {base}/Ordinary')
    wait_for(lambda: captions() == ['Ordinary'], 'ordinary folder')
    identity(out, 'pane-executable', exe)
    arrange(scale, 'Ordinary')
    pt = area(scale)
    click(pt(68, 310))  # Computer pane row
    wait_for(lambda: captions() == ['Computer'], 'pane Computer in the same window')
    browse = capture(out, 'pane-computer')
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: not captions(), 'pane Explorer closed')
    start_title, start = start_computer(out, scale, exe)
    for name, title, image in (('pane', 'Computer', browse), ('Start', start_title, start)):
        heading = words(image, pt(176, 94) + pt(400, 120)).strip()
        print(f'{name}: {title=}, overview heading OCR={heading!r}', flush=True)
    assert start_title == 'Computer'
    for image in (browse, start):
        assert 'Storage volumes' in words(image, pt(176, 94) + pt(400, 120)), 'Computer reached a directory instead of storage overview'
    click(pt(665, 42))
    vmctl.type_text(VM, 'W7VOLUME')
    single = capture(out, 'filtered-real-volume')
    label = words(single, pt(225, 118) + pt(430, 176))
    assert 'W7VOLUME' in label, label
    total, free = map(int, user(f"df -B1 --output=size,avail {base}/Mount | tail -1").split())
    assert 0 < free < total
    expected = f'{free / 2**20:.2f} MiB free of {total / 2**20:.2f} MiB'
    assert expected in label, (expected, label)
    print(f'actual capacity: df available={free}, total={total}; rendered {expected}', flush=True)
    # The only remaining tile's meter has both the Classic ink and its white unfilled section.
    meter = single.crop(pt(233, 141) + pt(406, 150))
    assert (255, 255, 255) in meter.get_flattened_data() and (10, 36, 106) in meter.get_flattened_data(), label
    click(pt(210, 143))
    if 'Computer' in captions():  # keep activation independent of KDE's single-click preference
        key('KEY_ENTER')
    wait_for(lambda: captions() == ['Mount'], 'genuine mounted folder opened')
    assert 'Proof.txt' in words(capture(out, 'mounted-folder'), pt(297, 193) + pt(399, 215))
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Computer'], 'Back returns to overview')
    assert 'Storage volumes' in words(capture(out, 'back-computer'), pt(176, 94) + pt(400, 120))
    key('KEY_LEFTALT', 'KEY_RIGHT')
    wait_for(lambda: captions() == ['Mount'], 'Forward opens mounted folder again')
    key('KEY_LEFTALT', 'KEY_LEFT')
    wait_for(lambda: captions() == ['Computer'], 'back to Computer for F5')
    guest_root(f'umount {base}/Mount')
    key('KEY_F5')
    click(pt(665, 42))
    vmctl.type_text(VM, 'W7VOLUME')
    absent = capture(out, 'unmounted-volume')
    assert set(absent.crop(pt(180, 118) + pt(421, 175)).get_flattened_data()) == {(255, 255, 255)}, 'unmounted tile still painted'
    guest_root(f'mount -o loop {base}/volume.img {base}/Mount')
    key('KEY_F5')
    assert 'W7VOLUME' in words(capture(out, 'remounted-volume'), pt(225, 118) + pt(430, 176))
    address('file:///', 'File System')
    root = capture(out, 'explicit-root')
    assert 'Storage volumes' not in words(root, pt(176, 94) + pt(400, 120))
    key('KEY_LEFTALT', 'KEY_D')
    key('KEY_LEFTCTRL', 'KEY_C')
    assert clipboard() == '/', 'the location is not the filesystem root'
    print('typed file:/// reached File System; live address edit copied literal /', flush=True)
    address(f'{base}/Ordinary', 'Ordinary')
    capture(out, 'ordinary-folder')
    key('KEY_LEFTCTRL', 'KEY_W')
    wait_for(lambda: not captions(), 'pane Explorer closed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--scale', type=float, choices=(1, 1.5), default=1)
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--packaged', action='store_true', help='use only the system package')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not (args.installed or args.packaged):
        install(reset=False)
    exe = executable('win7-explorer', args.packaged)
    output = output_name()
    toggle('current', packaged=args.packaged)
    before = user('xdg-mime query default inode/directory')
    base = user('mktemp -d /tmp/w7-volumes.XXXXXX')
    user(f'mkdir {base}/Mount {base}/Ordinary; kscreen-doctor output.{output}.scale.{args.scale}')
    try:
        guest_root(f'chmod 755 {base}; truncate -s 48M {base}/volume.img; '
                   f'mkfs.ext4 -q -F -L W7VOLUME {base}/volume.img && mount -o loop {base}/volume.img {base}/Mount && '
                   f'touch {base}/Mount/Proof.txt && chmod a+r {base}/Mount/Proof.txt')
        toggle('windows', packaged=args.packaged)
        run(args.out, args.scale, base, exe)
        toggle('current', packaged=args.packaged)
        assert user('xdg-mime query default inode/directory') == before
        open_folder(f'file://{base}/Ordinary')
        wait_for(lambda: 'Ordinary — Dolphin' in captions('org.kde.dolphin'), 'current opens the same fixture in stock Dolphin')
        assert not captions(), 'current launched Classic Explorer'
        capture(args.out, 'current-dolphin')
        key('KEY_LEFTALT', 'KEY_F4')
    finally:
        toggle('current', packaged=args.packaged)
        user(f'pkill -x win7-explorer || true; kscreen-doctor output.{output}.scale.1')
        guest_root(f'if mountpoint -q {base}/Mount; then umount {base}/Mount || exit 1; fi; rm -rf {base}')


if __name__ == '__main__':
    main()
