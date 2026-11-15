#!/usr/bin/env python3
"""Drive the disposable test VMs: commands, files, input and screenshots stay inside the guest."""
import argparse
import base64
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

VMS = {'lab': 'archlinux-1-1', 'w7': 'win7-classic-reference'}
VIRSH = ['virsh', '-c', 'qemu:///session']
# Commands run as the desktop user need its session bus and Wayland socket.
USER_ENV = 'export XDG_RUNTIME_DIR=/run/user/1001 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus WAYLAND_DISPLAY=wayland-1 QT_QPA_PLATFORM=wayland'


def virsh(*args, **kw):
    return subprocess.run(VIRSH + list(args), check=True, capture_output=True, text=True, **kw).stdout


def agent(vm, execute, arguments):
    data = json.loads(virsh('qemu-agent-command', vm, json.dumps({'execute': execute, 'arguments': arguments})))
    if 'error' in data:
        raise RuntimeError(f'{execute}: {data["error"]}')
    return data['return']


def run(vm, script, timeout):
    pid = agent(vm, 'guest-exec', {'path': '/usr/bin/bash', 'arg': ['-c', script], 'capture-output': True})['pid']
    deadline = time.monotonic() + timeout
    while not (status := agent(vm, 'guest-exec-status', {'pid': pid})).get('exited'):
        if time.monotonic() > deadline:
            raise TimeoutError(f'guest pid {pid} still running after {timeout}s')
        time.sleep(0.5)
    out = base64.b64decode(status.get('out-data', '')).decode(errors='replace')
    err = base64.b64decode(status.get('err-data', '')).decode(errors='replace')
    if status.get('out-truncated') or status.get('err-truncated'):
        raise RuntimeError('guest output truncated; write long output to a guest file')
    return status.get('exitcode', 128 + status.get('signal', 0)), out, err


def transfer(vm, mode, local, remote):
    handle = agent(vm, 'guest-file-open', {'path': remote, 'mode': 'wb' if mode == 'put' else 'rb'})
    try:
        with open(local, 'rb' if mode == 'put' else 'wb') as stream:
            if mode == 'put':
                while chunk := stream.read(48 * 1024):
                    agent(vm, 'guest-file-write', {'handle': handle, 'buf-b64': base64.b64encode(chunk).decode()})
            else:
                while True:
                    part = agent(vm, 'guest-file-read', {'handle': handle, 'count': 256 * 1024})
                    stream.write(base64.b64decode(part.get('buf-b64', '')))
                    if part['eof']:
                        break
    finally:
        agent(vm, 'guest-file-close', {'handle': handle})


def start(vm, timeout=300):
    if virsh('domstate', vm).strip() != 'running':
        virsh('start', vm)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if vm == VMS['w7']:
            # The Windows VM is deliberately agent-free; its autologon desktop is ready once the taskbar is drawn.
            if desktop_drawn(vm):
                return
        else:
            try:
                agent(vm, 'guest-ping', {})
                if run(vm, 'pgrep -x plasmashell', 10)[0] == 0:
                    return
            except (subprocess.CalledProcessError, RuntimeError):
                pass
        time.sleep(2)
    raise TimeoutError(f'{vm} did not reach a running desktop within {timeout}s')


def desktop_drawn(vm):
    from PIL import Image
    with tempfile.NamedTemporaryFile(suffix='.png') as shot:
        virsh('screenshot', vm, shot.name)
        with Image.open(shot.name) as image:
            # Classic taskbar ButtonFace along the bottom row of a 1280x800 desktop.
            return image.size == (1280, 800) and image.convert('RGB').getpixel((900, 790)) == (212, 208, 200)


def screen_size(vm):
    with tempfile.NamedTemporaryFile(suffix='.png') as shot:
        virsh('screenshot', vm, shot.name)
        from PIL import Image
        with Image.open(shot.name) as image:
            return image.size


def pointer(vm, x, y, button=None):
    width, height = screen_size(vm)
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f'({x},{y}) outside {width}x{height} screen')
    # Aim at the pixel centre: guests map the 0-32767 tablet range by truncation, so edges land a pixel off.
    batches = [[{'type': 'abs', 'data': {'axis': a, 'value': min(32767, round((v + 0.5) * 32768 / m))}} for a, v, m in (('x', x, width), ('y', y, height))]]
    if button:
        batches += [[{'type': 'btn', 'data': {'button': button, 'down': d}}] for d in (True, False)]
    for events in batches:
        virsh('qemu-monitor-command', vm, json.dumps({'execute': 'input-send-event', 'arguments': {'events': events}}))
        time.sleep(0.12)


SHIFTED = dict(zip(':"_+()!@#$%^&*{}|?<>~', ['SEMICOLON', 'APOSTROPHE', 'MINUS', 'EQUAL', '9', '0', '1', '2', '3', '4', '5', '6', '7', '8', 'LEFTBRACE', 'RIGHTBRACE', 'BACKSLASH', 'SLASH', 'COMMA', 'DOT', 'GRAVE']))
PLAIN = dict(zip(' .,/\\;\'-=[]`\n', ['SPACE', 'DOT', 'COMMA', 'SLASH', 'BACKSLASH', 'SEMICOLON', 'APOSTROPHE', 'MINUS', 'EQUAL', 'LEFTBRACE', 'RIGHTBRACE', 'GRAVE', 'ENTER']))


def keys(vm, *codes):
    for code in codes:
        if not re.fullmatch('KEY_[A-Z0-9_]+', code):
            raise ValueError(f'not a key code: {code}')
    virsh('send-key', vm, '--holdtime', '30', *codes)
    time.sleep(0.06)


def type_text(vm, text):
    for c in text:
        if c.isascii() and c.isalnum():
            keys(vm, *(['KEY_LEFTSHIFT'] if c.isupper() else []), 'KEY_' + c.upper())
        elif c in PLAIN:
            keys(vm, 'KEY_' + PLAIN[c])
        elif c in SHIFTED:
            keys(vm, 'KEY_LEFTSHIFT', 'KEY_' + SHIFTED[c])
        else:
            raise ValueError(f'cannot type {c!r}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vm', choices=VMS)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('start', help='boot if needed and wait for the desktop')
    for name in ('sh', 'user'):
        p = sub.add_parser(name, help='run stdin as root (sh) or as the desktop user (user)')
        p.add_argument('--timeout', type=int, default=300)
    for name in ('put', 'get'):
        p = sub.add_parser(name)
        p.add_argument('local')
        p.add_argument('remote')
    p = sub.add_parser('shot')
    p.add_argument('path')
    for name in ('click', 'rclick', 'move'):
        p = sub.add_parser(name)
        p.add_argument('x', type=int)
        p.add_argument('y', type=int)
    sub.add_parser('key').add_argument('codes', nargs='+')
    sub.add_parser('type').add_argument('text')
    a = parser.parse_args()
    vm = VMS[a.vm]
    if a.command == 'start':
        start(vm)
    elif a.command in ('sh', 'user'):
        script = sys.stdin.read()
        if a.command == 'user':
            script = f'{USER_ENV}\nexec runuser -u tester -- bash -c {shlex.quote(script)}'
        code, out, err = run(vm, script, a.timeout)
        sys.stdout.write(out)
        sys.stderr.write(err)
        sys.exit(code)
    elif a.command in ('put', 'get'):
        transfer(vm, a.command, a.local, a.remote)
    elif a.command == 'shot':
        virsh('screenshot', vm, a.path)
    elif a.command in ('click', 'rclick', 'move'):
        pointer(vm, a.x, a.y, {'click': 'left', 'rclick': 'right', 'move': None}[a.command])
    elif a.command == 'key':
        keys(vm, *a.codes)
    elif a.command == 'type':
        type_text(vm, a.text)


if __name__ == '__main__':
    main()
