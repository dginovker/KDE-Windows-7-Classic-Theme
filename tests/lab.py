"""Helpers for tests that drive the stock-Plasma lab VM as the `tester` user."""
import io
from pathlib import Path
import shlex
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'vm'))
import vmctl  # noqa: E402

VM = vmctl.VMS['lab']
FILES = 'plasma-org.kde.plasma.desktop-appletsrc plasmashellrc plasmarc'


def user(script, timeout=180, check=True):
    code, out, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- bash -c {shlex.quote(script)}', timeout)
    if check and code:
        raise AssertionError(f'guest command failed ({code}): {script}\n{out}{err}')
    return out.strip()


def toggle(target, expect_ok=True):
    code, out, err = vmctl.run(VM, f'{vmctl.USER_ENV}\nexec runuser -u tester -- ~tester/.local/bin/win7-classic {target}', 180)
    if (code == 0) != expect_ok:
        raise AssertionError(f'win7-classic {target} exit {code}:\n{err}')
    return err


def close_test_apps():
    """Close every app the tests start, so one test's leftovers never show up in another's screenshots."""
    user('pkill -u tester -x kate; pkill -u tester -x kdialog; pkill -u tester -x konsole; pkill -u tester -x dolphin; '
         'pkill -u tester -x gtk3-demo; pkill -u tester firefox; pkill -f "^counter-loop"; '
         'pkill -f "^/usr/bin/python3 /tmp/fixture_window.py"; rm -f /tmp/counter /tmp/kate-proof.txt; true')


def install():
    """Run install.sh from the working tree as tester, then reset to current mode with no saved profiles."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name in ('install.sh', 'fonts', 'plasma', 'toggle'):
            tar.add(ROOT / name, arcname=name, filter=lambda t: None if '__pycache__' in t.name else t)
    Path('/tmp/win7-install.tgz').write_bytes(buffer.getvalue())
    vmctl.transfer(VM, 'put', '/tmp/win7-install.tgz', '/tmp/win7-install.tgz')
    vmctl.run(VM, 'chmod 644 /tmp/win7-install.tgz', 10)
    user('rm -rf /tmp/win7-src && mkdir /tmp/win7-src && tar -xzf /tmp/win7-install.tgz -C /tmp/win7-src && /tmp/win7-src/install.sh')
    close_test_apps()
    if user('~/.local/bin/win7-classic status') != 'current':
        toggle('current')
    user('rm -rf ~/.local/state/win7-classic')


def digest():
    return user(f'cd ~/.config && sha256sum {FILES} 2>&1 || true')


def kwin_script(source):
    vmctl.run(VM, f'cat > /tmp/kwin.js <<"JS"\n{source}\nJS\nchmod 644 /tmp/kwin.js', 30)
    user('id=$(qdbus6 org.kde.KWin /Scripting loadScript /tmp/kwin.js t$RANDOM) && qdbus6 org.kde.KWin /Scripting/Script$id run && sleep 0.5 && qdbus6 org.kde.KWin /Scripting/Script$id stop')


def kwin_query(body):
    """Run KWin script `body`, which reports with emit(...fields); returns the emitted rows.

    Rows are read back from the journal, so a nonce and an end marker make sure all of them have arrived.
    """
    nonce = f'W7Q{time.monotonic_ns()}'
    kwin_script(f'function emit(...fields) {{ print("{nonce}\\t" + fields.join("\\t")); }}\n{body}\nprint("{nonce}\\tEND");')
    for _ in range(40):
        lines = [l.split('\t')[1:] for l in user(f'journalctl --user --since -2min --no-pager -o cat | grep -a {nonce} || true').splitlines()]
        if ['END'] in lines:
            return [l for l in lines if l != ['END']]
        time.sleep(0.25)
    raise AssertionError(f'KWin query produced no end marker: {body}')


def windows():
    """resourceClass -> (caption, active, minimized) for every window."""
    rows = kwin_query('for (const w of workspace.windowList()) emit(w.resourceClass, w.caption, workspace.activeWindow == w, w.minimized);')
    return {cls: (caption, active == 'true', minimized == 'true') for cls, caption, active, minimized in rows}


def activate(resource):
    kwin_script(f'for (const w of workspace.windowList()) if (w.resourceClass == "{resource}") workspace.activeWindow = w;')
    assert windows()[resource][1], f'could not focus {resource}'


def wait_for(predicate, what, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.5)
    raise AssertionError(f'timed out waiting for {what}')


def shot(path):
    vmctl.virsh('screenshot', VM, str(path))
