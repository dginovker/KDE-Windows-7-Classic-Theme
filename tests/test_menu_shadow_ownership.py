#!/usr/bin/env python3
"""Compare inherited non-Classic menus with the installed pre-shadow baseline on stock Wayland."""
import argparse
import json
from pathlib import Path
import re
import shlex
import time

from PIL import Image, ImageChops
from lab import ROOT, VM, kwin_query, kwin_script, shot, user, vmctl, wait_for

TITLE = 'Menu shadow ownership fixture'
SHADOW_REQUEST = r'-> org_kde_kwin_shadow_manager#\d+\.(create|unset)\('


def requests(span):
    return re.findall(SHADOW_REQUEST, span)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--baseline', type=Path, help='compare against this pre-shadow run; omit only to record baseline')
    args = parser.parse_args()
    out = args.out
    out.mkdir(parents=True)
    assert user('~/.local/bin/win7-classic status') == 'current'
    assert json.loads(user('kscreen-doctor -j'))['outputs'][0]['scale'] == 1
    root = user('mktemp -d /tmp/w7-shadow-ownership.XXXXXX')
    unit = Path(root).name
    trace = root + '/wayland.log'
    trigger = root + '/switch'

    def popup_rows():
        return [row for row in kwin_query('for(const w of workspace.windowList()) '
                'emit(w.caption,w.popupWindow,w.frameGeometry,w.pid);') if row[1] == 'true' and row[3] == pid]

    def capture(label, x):
        vmctl.pointer(VM, 790, 480)
        vmctl.pointer(VM, x, 200, 'left')
        wait_for(popup_rows, label)
        rows = popup_rows()
        assert len(rows) == 1, rows
        box = tuple(int(float(v)) for v in rows[0][2].split('(')[1].rstrip(')').split(', '))
        path = out / (label + '.png')
        shot(path)
        return box, Image.open(path).convert('RGB')

    def dismiss():
        vmctl.keys(VM, 'KEY_ESC')
        wait_for(lambda: not popup_rows(), 'Escape dismissed the native menu')

    try:
        vmctl.transfer(VM, 'put', str(ROOT / 'tests/fixture_menu_shadow_ownership.py'), root + '/fixture.py')
        vmctl.run(VM, f'chmod 644 {root}/fixture.py', 10)
        cmd = f'WAYLAND_DEBUG=client python3 {root}/fixture.py {trigger} > {trace} 2>&1'
        user(f'systemd-run --user --collect -q --unit={unit} bash -c {shlex.quote(cmd)}')
        wait_for(lambda: 'PROBE ready' in user(f'grep "PROBE ready" {trace}', check=False), TITLE)
        pid = user(f'sed -n "s/^PROBE ready pid=//p" {trace}')
        assert pid.isdecimal(), pid
        kwin_script(f'for(const w of workspace.windowList()) if(w.caption=="{TITLE}") '
                    '{w.frameGeometry={x:240,y:145,width:560,height:430}; workspace.activeWindow=w;}')
        box, image = capture('inherited', 300)
        x, y, w, h = box
        image.crop((x-6, y-6, x+w+7, y+h+7)).save(out / 'inherited-crop.png')
        (out / 'inherited-box.json').write_text(json.dumps(box))
        dismiss()
        if args.baseline:
            for label in ('classic', 'classic-reopened'):
                (x, y, w, h), direct = capture(label, 499)
                strip = [direct.getpixel((x+w+i, y+h//2)) for i in range(6)]
                assert strip == [(g, g, g) for g in (142,171,212,241,252,255)], (label, strip)
                if label == 'classic':
                    dismiss()
            user(f'touch {trigger}')
            wait_for(lambda: 'PROBE switched fusion' in user(f'grep "PROBE switched" {trace}', check=False), 'live style switch')
            assert user(f'grep "^PROBE switched fusion pid={pid}$" {trace}')
            shot(out / 'switched-to-fusion.png')
            if popup_rows():
                dismiss()
            capture('fusion-reopened', 499)
            dismiss()
    finally:
        user(f'systemctl --user stop {unit}.service', check=False)
        try:
            vmctl.transfer(VM, 'get', str(out / 'wayland.log'), trace)
        finally:
            user(f'rm -r -- {root}')

    log = (out / 'wayland.log').read_text()
    inherited = log.split('PROBE inherited WA_SetStyle=false parent_explicit=Fusion shares_parent_wrapper=true effective_is_Classic=false')[1]
    inherited = inherited.split('PROBE direct', 1)[0]
    assert '.get_popup(' in inherited and 'PROBE hide Inherited' in inherited, 'inherited menu was not mapped and dismissed'
    inherited_requests = requests(inherited)
    print('Inherited create/unset:', inherited_requests, flush=True)
    if args.baseline:
        original = args.baseline
        assert (original / 'inherited-box.json').read_text() == (out / 'inherited-box.json').read_text()
        with Image.open(original / 'inherited-crop.png') as a, Image.open(out / 'inherited-crop.png') as b:
            diff = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
            diff.save(out / 'inherited-diff.png')
            pixel_delta = diff.getbbox()
        print('Inherited crop difference vs baseline:', pixel_delta, flush=True)
        _, first, reopened = log.split('PROBE direct win7classic')
        before, switched = reopened.split('PROBE switch Classic to Fusion with popup visible')
        assert requests(first) == ['create', 'unset'], requests(first)
        assert requests(before) == ['create'], requests(before)
        assert requests(switched) == ['unset'], requests(switched)
        fusion = switched.split('PROBE direct fusion')[1]
        assert '.get_popup(' in fusion and 'PROBE hide Direct' in fusion
        assert not inherited_requests and pixel_delta is None, 'Classic changed the inherited non-Classic popup'
    else:
        assert not inherited_requests, inherited_requests
    print('PASS: inherited non-Classic popup untouched; positive and active style cleanup checked when comparing')


if __name__ == '__main__':
    main()
