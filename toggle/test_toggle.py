#!/usr/bin/env python3
"""Acceptance test for the live toggle, run from the host against the lab VM (issues #4, #5)."""
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'vm'))
import vmctl  # noqa: E402

VM = vmctl.VMS['lab']
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-toggle-test')
TEXT = 'unsaved line typed before any switch\n'
FILES = 'plasma-org.kde.plasma.desktop-appletsrc plasmashellrc'


def user(script, timeout=180, check=True):
    code, out, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- bash -c {vmctl.shlex.quote(script)}', timeout)
    if check and code:
        raise AssertionError(f'guest command failed ({code}): {script}\n{out}{err}')
    return out.strip()


def toggle(target, expect_ok=True):
    code, out, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- ~tester/.local/bin/win7-classic {target}', 180)
    if (code == 0) != expect_ok:
        raise AssertionError(f'win7-classic {target} exit {code}:\n{err}')
    return err


def digest():
    return user(f'cd ~/.config && sha256sum {FILES}')


def pids():
    return {name: user(f'pgrep -u tester -nf {pattern!r}') for name, pattern in
            [('kwin', '^/usr/bin/kwin_wayland '), ('kate', '^/usr/bin/kate -n'), ('konsole', '^/usr/bin/konsole'),
             ('loop', '^counter-loop'), ('dialog', '^/usr/bin/kdialog')]}


def counter():
    return int(user('cat /tmp/counter'))


def kwin_script(source):
    vmctl.run(VM, f'cat > /tmp/kwin.js <<"JS"\n{source}\nJS\nchmod 644 /tmp/kwin.js', 30)
    user('id=$(qdbus6 org.kde.KWin /Scripting loadScript /tmp/kwin.js t$RANDOM) && qdbus6 org.kde.KWin /Scripting/Script$id run && sleep 0.5 && qdbus6 org.kde.KWin /Scripting/Script$id stop')


def windows():
    """resourceClass -> caption for every window, read from KWin."""
    since = user('date +%H:%M:%S')
    kwin_script('for (const w of workspace.windowList()) print("WIN\t" + w.resourceClass + "\t" + w.caption + "\t" + (workspace.activeWindow == w));')
    lines = [l.split('WIN\t', 1)[1].split('\t') for l in user(f'journalctl --user --since {since} --no-pager -o cat').splitlines() if 'WIN\t' in l]
    return {cls: (caption, active == 'true') for cls, caption, active in lines}


def activate(resource):
    kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{resource}") workspace.activeWindow = w;')
    assert windows()[resource][1], f'could not focus {resource}'


def shot(name):
    vmctl.virsh('screenshot', VM, str(OUT / f'{name}.png'))


class Recorder(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.running, self.frames = True, 0

    def run(self):
        while self.running:
            vmctl.virsh('screenshot', VM, str(OUT / 'frames' / f'{self.frames:05}.png'))
            self.frames += 1
            time.sleep(0.2)


def install():
    for name in ('win7-classic', 'windows-layout.js'):
        vmctl.transfer(VM, 'put', str(ROOT / name), f'/tmp/{name}')
    vmctl.run(VM, '''set -e
d=/home/tester/.local/share/win7-classic
install -D -o tester -g tester -m755 /tmp/win7-classic $d/win7-classic
install -D -o tester -g tester -m644 /tmp/windows-layout.js $d/windows-layout.js
install -d -o tester -g tester /home/tester/.local/bin
ln -sfn ../share/win7-classic/win7-classic /home/tester/.local/bin/win7-classic''', 30)
    # Start every run from current mode with no saved profiles, so Windows mode is seeded fresh.
    toggle('current')
    user('rm -rf ~/.local/state/win7-classic; pkill -f ^counter-loop; pkill -u tester -x kate; pkill -u tester -x kdialog; pkill -u tester -x konsole; rm -f /tmp/counter /tmp/kate-proof.txt ~/oof.txt; true')


def open_work():
    user('systemd-run --user --collect -q kate -n')
    time.sleep(4)
    activate('org.kde.kate')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_N')
    time.sleep(1)
    vmctl.type_text(VM, TEXT)
    time.sleep(0.5)
    caption = windows()['org.kde.kate'][0]
    assert caption.startswith('Untitled') and '*' in caption, f'Kate has no modified document: {caption!r}'
    user("systemd-run --user --collect -q konsole -e bash -c 'exec -a counter-loop bash -c \"i=0; while :; do echo \\$i > /tmp/counter; echo running \\$i; i=\\$((i+1)); sleep 0.5; done\"'")
    user('systemd-run --user --collect -q kdialog --title "Open dialog under test" --getopenfilename /home/tester')
    time.sleep(4)


def assert_work_alive(expected, label, unsaved=True):
    now = pids()
    assert now == expected, f'{label}: processes changed {expected} -> {now}'
    caption = windows()['org.kde.kate'][0]
    assert not unsaved or (caption.startswith('Untitled') and '*' in caption), f'{label}: Kate document lost: {caption!r}'
    first = counter()
    time.sleep(1.2)
    assert counter() > first, f'{label}: Konsole job stopped counting'


def main():
    (OUT / 'frames').mkdir(parents=True, exist_ok=True)
    # Stale artifacts from an earlier run must never be mistaken for this run's evidence.
    for old in [*OUT.glob('*.png'), *(OUT / 'frames').glob('*.png'), *OUT.glob('*.mp4'), *OUT.glob('*.log')]:
        old.unlink()
    vmctl.start(VM)
    install()
    open_work()
    work = pids()
    assert all(work.values()), work
    shot('1-current-with-work')

    recorder = Recorder()
    recorder.start()
    toggle('windows')
    time.sleep(2)
    shot('2-windows')
    # A user edit in each mode must survive leaving and returning to that mode.
    user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "panels()[0].height = 46"')
    time.sleep(1)
    toggle('current')
    time.sleep(2)
    recorder.running = False
    recorder.join()
    user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "panels()[0].addWidget(\'org.kde.plasma.panelspacer\')"')
    time.sleep(1)

    for trip in range(1, 11):
        before_current = digest()
        toggle('windows')
        assert user('qdbus6 org.kde.plasmashell /PlasmaShell evaluateScript "print(panels()[0].height)"') == '46', f'trip {trip}: Windows-mode edit lost'
        before_windows = digest()
        toggle('current')
        assert digest() == before_current, f'trip {trip}: current config changed:\n{before_current}\n{digest()}'
        assert 'org.kde.plasma.panelspacer' in user('grep -h plugin= ~/.config/plasma-org.kde.plasma.desktop-appletsrc'), f'trip {trip}: Current-mode edit lost'
        toggle('windows')
        assert digest() == before_windows, f'trip {trip}: windows config changed'
        toggle('current')
        assert_work_alive(work, f'trip {trip}')
        print(f'round trip {trip}/10 ok', flush=True)
    shot('3-current-restored')

    # Save Kate's never-saved buffer now, proving its content survived every switch.
    activate('org.kde.kate')
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_S')
    for _ in range(20):
        if any(c.startswith('Save') for c, _ in windows().values()):
            break
        time.sleep(0.5)
    else:
        raise AssertionError('Kate save dialog did not open')
    time.sleep(1)
    vmctl.keys(VM, 'KEY_LEFTCTRL', 'KEY_A')
    vmctl.type_text(VM, '/tmp/kate-proof.txt\n')
    time.sleep(2)
    assert windows()['org.kde.kate'][0].startswith('kate-proof.txt'), windows()['org.kde.kate']
    saved = user('cat /tmp/kate-proof.txt')
    assert saved == TEXT.strip(), f'Kate buffer content changed: {saved!r}'
    print('Kate buffer intact after 22 switches:', repr(saved))

    # Issue #5: a broken Windows profile must be refused, leaving current mode and work untouched.
    healthy = digest()
    user("sed -i 's/plugin=org.kde.plasma.taskmanager/plugin=org.example.missing/' ~/.local/state/win7-classic/profiles/windows/plasma-org.kde.plasma.desktop-appletsrc")
    log = toggle('windows', expect_ok=False)
    assert 'unknown widgets: org.example.missing' in log, log
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert digest() == healthy, 'failed switch altered current config'
    assert_work_alive(work, 'after failed switch', unsaved=False)
    shot('4-after-failed-switch')

    # Issue #5: with no panel running at all, one command brings current mode back.
    user("sed -i 's/plugin=org.example.missing/plugin=org.kde.plasma.taskmanager/' ~/.local/state/win7-classic/profiles/windows/plasma-org.kde.plasma.desktop-appletsrc")
    toggle('windows')
    user('systemctl --user stop plasma-plasmashell.service')
    toggle('restore')
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert digest() == healthy, 'restore did not bring back current config'
    assert_work_alive(work, 'after restore', unsaved=False)
    shot('5-after-restore')
    (OUT / 'switch.log').write_text(user('cat ~/.local/state/win7-classic/switch.log'))

    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '5', '-i', str(OUT / 'frames' / '%05d.png'),
                    '-vf', 'scale=1280:-2', '-pix_fmt', 'yuv420p', str(OUT / 'round-trip.mp4')], check=True)
    print('ALL TOGGLE CHECKS PASSED; artifacts in', OUT)


if __name__ == '__main__':
    main()
