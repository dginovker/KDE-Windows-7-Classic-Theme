#!/usr/bin/env python3
"""Drive Explorer Frequent through the real lab taskbar, using the installed revision."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, digest, executable, kwin_query, shot, toggle, user, vmctl, wait_for, windows
from explorer_frequent_fixture import TREE, fixture, stash, stop_folder_explorers, unit
from test_upgrade import output_name

APP = 'org.win7classic.explorer'
STATE = '${XDG_STATE_HOME:-$HOME/.local/state}/win7-explorer'
PROFILE = '${XDG_STATE_HOME:-$HOME/.local/state}/win7-classic/profiles/windows'
FACE = (212, 208, 200)
BLACK = (0, 0, 0)
NATIVE = ROOT / 'reference/screenshots/w7-explorer-jumplist.png'


def key(*codes):
    vmctl.keys(VM, *('KEY_' + c for c in codes))


def explorer():
    return windows().get(APP)


def go(folder, caption=None):
    key('LEFTALT', 'D')
    vmctl.type_text(VM, f'{TREE}/{folder}\n')
    wait_for(lambda: (explorer() or ('',))[0] == (caption or folder), f'Explorer navigates to {folder}')


def panel(script):
    source = 'for (const w of panels()[0].widgets()) if (w.type === "org.win7classic.taskbar") { ' \
             'w.currentConfigGroup = ["General"]; ' + script + ' }'
    return user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript ' + shlex.quote(source))


def popup(out, name, n, launcher=False, scale=1, task_left=63, explorer_menu=True, unavailable=False):
    panel_top = 800 - round(44 * scale)
    vmctl.pointer(VM, round((task_left + 22) * scale), 800 - round(22 * scale), 'right')
    time.sleep(.22)  # Let the bounded initial check present before leaving the task.
    vmctl.pointer(VM, 700, 350)
    time.sleep(.18)
    path = out / f'{name}.png'
    shot(path)
    image = Image.open(path).convert('RGB')
    assert image.size == (1280, 800)
    # Match the centered anchor, clamped against the left edge of the stock work area.
    left = round(max(0, task_left + (24 if launcher else 80) - 115) * scale)
    width = round(230 * scale)
    height = (72 if launcher else 94) + (56 + 22 * n if n else 0)
    # Native Explorer with the recent Jump List item limit set to zero.
    if explorer_menu and not n:
        height -= 22
    if unavailable:
        height += 43
    top = panel_top - round(height * scale)
    crop = image.crop((left - 2, top - 2, left + width + 2, panel_top))
    crop.save(out / f'{name}-crop.png')
    if scale == 1:
        assert image.getpixel((left, top)) == BLACK and image.getpixel((left + 100, top)) == BLACK and \
            image.getpixel((left + 101, top + 1)) == FACE, \
            f'{name}: no {height}px jump list at ({left}, {top})'
    else:
        # A physical pixel on either side of each logical edge can be sampled differently by KWin.
        assert image.getpixel((left + 5, top + 3)) == FACE
        assert any(image.getpixel((left + 100, y)) == BLACK for y in range(top - 2, top + 3)), \
            f'{name}: frame does not start at the expected 150% height'
    return image, left, top


def ocr(out, name, image, box):
    crop = image.crop(box)
    path = out / f'{name}-text.png'
    crop.resize((crop.width * 4, crop.height * 4)).save(path)
    return subprocess.check_output(['tesseract', str(path), 'stdout', '--psm', '6'], text=True).split()


def verify_native(out, image, x, y):
    native = Image.open(NATIVE).convert('RGB').crop((78, 518, 308, 756))
    ours = image.crop((x, y, x + 230, y + 238))
    native.save(out / 'native.png')
    ours.save(out / 'lab.png')
    pair = Image.new('RGB', (464, 238), 'white')
    pair.paste(native)
    pair.paste(ours, (234, 0))
    pair.save(out / 'windows-left-lab-right.png')
    diff = ImageChops.difference(native, ours)
    # Local folder icons/names are not native library objects; check those separately below.
    diff.paste(BLACK, (7, 6, 62, 20))
    for i in range(4):
        diff.paste(BLACK, (8, 32 + 22*i, 130, 54 + 22*i))
    for top in (165, 187, 209):
        diff.paste(BLACK, (29, top, 222, top + 12))
    diff.point(lambda v: 255 if v else 0).save(out / 'structure-diff.png')
    assert diff.getbbox() is None, f'Frequent structure differs from genuine Windows: {diff.getbbox()}'
    assert ocr(out, 'heading', ours, (5, 3, 100, 21)) == ['Frequent']
    for i, label in enumerate(('Projects', 'Pictures', 'Music', 'Videos')):
        top = 32 + 22*i
        assert ocr(out, label, ours, (28, top + 2, 145, top + 20)) == [label]
        icon = Image.open(ROOT / 'plasma/icons/Win7-Classic/16x16/places/folder.png').convert('RGBA')
        background = Image.new('RGBA', (16, 16), FACE + (255,))
        background.alpha_composite(icon)
        delta = ImageChops.difference(ours.crop((9, top + 3, 25, top + 19)), background.convert('RGB'))
        assert max(hi for _, hi in delta.getextrema()) <= 1, f'{label}: missing genuine Classic local folder icon'


def own_home_window(restore, what):
    wait_for(lambda: (explorer() or ('',))[0] == 'tester', what)
    rows = kwin_query(f'for (const w of workspace.windowList()) if (w.resourceClass == "{APP}" && '
                      'w.caption == "tester") emit(w.pid);')
    assert len(rows) == 1 and rows[0][0].isdigit(), rows
    pid = rows[0][0]
    identity = user(f'cat /proc/{pid}/stat')
    started = shlex.quote(identity.rsplit(')', 1)[1].split()[19])
    restore.callback(user, f'''state=$(cat /proc/{pid}/stat 2>/dev/null) || exit 0
set -- ${{state##*) }}
if [[ ${{20}} == {started} ]]; then kill {pid}; fi''')


def kate_window(pid, activate=False):
    assert pid.isdigit() and int(pid) > 0
    focus = 'workspace.activeWindow = w;' if activate else ''
    rows = kwin_query(f'for (const w of workspace.windowList()) if (w.pid == {pid} && '
                      f'w.caption.startsWith("work.txt")) {{ {focus} emit(w.caption); }}')
    return rows[0][0] if rows else ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--packaged', action='store_true', help='use the system-installed Explorer')
    args = parser.parse_args()
    out = args.out
    explorer_bin = executable('win7-explorer', args.packaged)
    switch = executable('win7-classic', args.packaged)
    out.mkdir(parents=True, exist_ok=True)
    assert user(f'{switch} status') == 'current'
    output = output_name()
    assert explorer() is None, 'the Explorer task button must belong to the test'
    assert 'org.kde.dolphin' not in windows(), 'Dolphin might reuse an existing instance'
    with fixture('Projects', 'Pictures', 'Music', 'Videos', 'Outside', 'Once') as restore:
        stash(restore, STATE, 'history')
        stash(restore, PROFILE, 'profile')
        restore.callback(lambda: toggle('current', packaged=args.packaged) if user(f'{switch} status') == 'windows' else None)
        restore.callback(user, f'kscreen-doctor output.{output}.scale.1')
        restore.callback(stop_folder_explorers)
        original = digest()
        toggle('windows', packaged=args.packaged)
        panel('w.writeConfig("launchers", ["applications:org.win7classic.explorer.desktop", "applications:org.kde.konsole.desktop"]);')
        wait_for(lambda: 'launchers=applications:org.win7classic.explorer.desktop,applications:org.kde.konsole.desktop' in
                 user('grep "^launchers=" ~/.config/plasma-org.kde.plasma.desktop-appletsrc'), 'test launchers saved')
        popup(out, 'empty-pin', 0, launcher=True)
        key('ESC')
        vmctl.pointer(VM, 85, 778, 'left')
        own_home_window(restore, 'launch real Explorer pin')
        go('Once')
        key('F5')
        key('F5')
        popup(out, 'only-once', 0)
        key('ESC')
        # Most-used first, not merely recent: Projects gets three visits, the newest two-visit folder is Pictures.
        for folder in ('Projects', 'Videos', 'Music', 'Pictures', 'Projects', 'Videos', 'Music', 'Projects', 'Pictures'):
            go(folder)
        image, x, y = popup(out, 'populated', 4)
        verify_native(out, image, x, y)
        print('four repeated local destinations in frequency/recency order; native 230×238 structure and Classic icons match')
        recent_docs = 'cd "${XDG_DATA_HOME:-$HOME/.local/share}"; if test -d RecentDocuments; then ' \
                      'find RecentDocuments -type f -print0 | sort -z | xargs -0r sha256sum; fi'
        recents = user(recent_docs)

        vmctl.pointer(VM, x + 85, y + 43, 'left')
        wait_for(lambda: (explorer() or ('',))[0] == 'Projects', 'Frequent mouse opens the ranked folder in Explorer')
        key('LEFTCTRL', 'W')
        wait_for(lambda: (explorer() or ('',))[0] == 'Pictures', 'opening Frequent keeps the previous window')
        popup(out, 'populated-close', 4)
        key('UP')
        key('ENTER')
        wait_for(lambda: explorer() is None, 'Close window from populated jump list')
        popup(out, 'populated-pin', 4, launcher=True)
        key('DOWN')
        key('DOWN')
        key('ENTER')
        wait_for(lambda: (explorer() or ('',))[0] == 'Pictures', 'Frequently visited folder opens by keyboard from closed pin')
        key('LEFTCTRL', 'W')
        wait_for(lambda: explorer() is None, 'Explorer closed again')
        assert user(recent_docs) == recents, 'opening a Frequent row wrote to KDE shared RecentDocuments'
        popup(out, 'other-app-pin', 0, launcher=True, task_left=113, explorer_menu=False)
        key('ESC')
        popup(out, 'populated-launch', 4, launcher=True)
        key('UP')
        key('UP')
        key('ENTER')
        own_home_window(restore, 'application row still launches Explorer')
        key('LEFTCTRL', 'W')
        wait_for(lambda: explorer() is None, 'launched Explorer closed')
        popup(out, 'populated-unpin', 4, launcher=True)
        key('UP')
        key('ENTER')
        launchers = lambda: user('grep "^launchers=" ~/.config/plasma-org.kde.plasma.desktop-appletsrc')
        wait_for(lambda: 'org.win7classic.explorer.desktop' not in launchers(), 'populated launcher can still be unpinned')
        unit(restore, f'{explorer_bin} trash:/')
        wait_for(lambda: (explorer() or ('',))[0] == 'trash:/', 'Explorer opens the virtual trash location')
        popup(out, 'populated-repin', 4, task_left=113)
        key('UP')
        key('UP')
        key('ENTER')
        wait_for(lambda: 'org.win7classic.explorer.desktop' in launchers(), 'running Explorer can still be pinned')
        key('LEFTCTRL', 'W')
        wait_for(lambda: explorer() is None, 'virtual location closed')
        print('Frequent mouse/keyboard activation avoids shared recents; launch, unpin, pin and Close window still work')

        user(f'touch {TREE}/work.txt')
        kate = unit(restore, f'kate -n {TREE}/work.txt')
        kate_pid = user(f'systemctl --user show {kate} -p MainPID --value')
        wait_for(lambda: kate_window(kate_pid, activate=True), 'Kate fixture window')
        vmctl.type_text(VM, 'unsaved through mode changes')
        wait_for(lambda: '*' in kate_window(kate_pid), 'Kate document has unsaved edits')
        work_pids = user(f'systemctl --user show {kate} -p MainPID --value; pgrep -x kwin_wayland')
        toggle('current', packaged=args.packaged)
        assert digest() == original, 'history or task actions changed the current profile'
        assert user(f'stat -c %a "{STATE}/frequent.json"') == '600'
        data = user(f'cat "{STATE}/frequent.json"')
        assert dict(json.loads(data)) == {f'{TREE}/{folder}': n for folder, n in
                                          [('Once', 1), ('Projects', 4), ('Videos', 2), ('Music', 2), ('Pictures', 3)]}
        for _ in range(2):
            unit(restore, f'dolphin --new-window {TREE}/Outside')
            wait_for(lambda: windows().get('org.kde.dolphin', ('', False))[:2] == ('Outside — Dolphin', True), 'Dolphin opens isolated folder')
            key('LEFTALT', 'F4')
            wait_for(lambda: 'org.kde.dolphin' not in windows(), 'Dolphin closed')
        assert user(f'cat "{STATE}/frequent.json"') == data, 'non-Explorer activity modified Frequent'
        print('exact private aggregate counts; no implicit start, reload, virtual, or Dolphin visits; current profile unchanged')
        user(f'rmdir {TREE}/Music; kscreen-doctor output.{output}.scale.1.5')
        toggle('windows', packaged=args.packaged)
        image, x, y = popup(out, '150-pin-missing-folder', 3, launcher=True, scale=1.5, task_left=113)
        assert ocr(out, '150-rows', image, (x + 42, y + 44, x + 205, y + 140)) == ['Projects', 'Pictures', 'Videos']
        key('DOWN')
        key('ENTER')
        wait_for(lambda: (explorer() or ('',))[0] == 'Projects', 'persisted Frequent activates after switch at 150%')
        print('persisted across panel restart and mode switches; unavailable destination omitted; 150% layout and activation')
        toggle('current', packaged=args.packaged)
        assert digest() == original and user(f'systemctl --user show {kate} -p MainPID --value; pgrep -x kwin_wayland') == work_pids
        assert user(f'test ! -s {TREE}/work.txt && echo unsaved') == 'unsaved'
        assert '*' in kate_window(kate_pid, activate=True)
        key('LEFTCTRL', 'S')
        wait_for(lambda: user(f'cat {TREE}/work.txt') == 'unsaved through mode changes', 'Kate saves exact unsaved text')
        print('current profile bytes, KWin and Kate PIDs, and unsaved Kate text preserved')


if __name__ == '__main__':
    main()
