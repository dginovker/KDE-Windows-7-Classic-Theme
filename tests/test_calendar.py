#!/usr/bin/env python3
"""Issue #33 smoke test for the disposable Plasma lab VM; never opens the time KCM."""
from pathlib import Path
import json
import sys
import time

from PIL import Image

from lab import VM, install, shot, toggle, user, vmctl, wait_for

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-calendar-test')
BLACK = (0, 0, 0)
FACE = (212, 208, 200)
WHITE = (255, 255, 255)
BLUE = (10, 36, 106)


def snapshot(name):
    path = OUT / f'{name}.png'
    shot(path)
    with Image.open(path) as image:
        return image.convert('RGB')


def geometry(image, scale):
    return image.width - round(331 * scale), image.height - round((44 + 243) * scale)


def is_open(image, scale):
    x, y = geometry(image, scale)
    # At 150%, the compositor can round a logical edge by a physical pixel.
    return (any(all(image.getpixel((p, y + dy)) == BLACK for p in range(x + 8, image.width, 16))
                for dy in range(-2, 3))
            and any(image.getpixel((image.width - 1, q)) == BLACK
                    for q in range(y + 20, y + 26))
            and image.getpixel((x + round(5 * scale), y + round(50 * scale))) == WHITE
            and image.getpixel((x + round(45 * scale), y + round(43 * scale))) == BLUE
            and image.getpixel((x + round(5 * scale), image.height - round(47 * scale))) == FACE)


def check_popup(scale):
    tag = f'{scale:g}x'
    before = snapshot(f'{tag}-closed')
    x, y = geometry(before, scale)

    def click(dx, dy):
        vmctl.pointer(VM, x + round(dx * scale), y + round(dy * scale), 'left')

    def click_clock(dy=30):
        vmctl.pointer(VM, before.width - round(50 * scale), before.height - round(dy * scale), 'left')

    def wait_state(opened, name):
        wait_for(lambda: is_open(snapshot(f'{tag}-probe'), scale) == opened, f'{tag} calendar {name}')
        return snapshot(f'{tag}-{name}')

    click_clock()
    opened = wait_state(True, 'opened-from-time')
    month = (x + round(44 * scale), y + round(46 * scale), x + round(147 * scale), y + round(62 * scale))
    seconds = (x + round(188 * scale), y + round(178 * scale), x + round(311 * scale), y + round(189 * scale))
    hands = (x + round(198 * scale), y + round(54 * scale), x + round(301 * scale), y + round(157 * scale))
    time.sleep(2)
    ticked = snapshot(f'{tag}-tick')
    assert opened.crop(seconds) != ticked.crop(seconds), 'digital seconds did not advance'
    assert opened.crop(hands) != ticked.crop(hands), 'analogue hands did not advance'
    click(30, 54)
    previous = wait_state(True, 'previous-month')
    assert opened.crop(month) != previous.crop(month), 'previous month did not change heading'
    click(160, 54)
    returned = wait_state(True, 'next-month')
    assert opened.crop(month) == returned.crop(month), 'next month did not restore heading'
    click(95, 54)
    years = wait_state(True, 'month-grid')
    assert years.crop(month) != returned.crop(month), 'month heading did not reveal the month grid'
    click(95, 54)
    decade = wait_state(True, 'year-grid')
    assert decade.crop(month) != years.crop(month), 'year heading did not reveal the year grid'
    click(95, 54)
    century = wait_state(True, 'decade-grid')
    assert century.crop(month) != decade.crop(month), 'decade heading did not reveal the decade grid'
    click(95, 54)
    assert snapshot(f'{tag}-top-level').crop(month) == century.crop(month), 'century heading should stop zooming out'

    # A different decade must keep the selected year's last digit (e.g. 2026 -> 2046).
    year, month_number = map(int, user('date "+%Y %m"').split())
    start = year // 100 * 100
    target = start + (40 if year // 10 % 10 != 4 else 60)

    def period_cell(index, dx=20, dy=18):
        return 15 + 40 * (index % 4) + dx, 68 + 36 * (index // 4) + dy

    def selected(image, index):
        px, py = period_cell(index, 5, 5)
        return image.getpixel((x + round(px * scale), y + round(py * scale))) == BLUE

    click(*period_cell((target - start) // 10 + 1))
    drilled = wait_state(True, 'pointer-decade-drill')
    digit = year % 10
    assert selected(drilled, digit + 1), f'{target + digit} was not selected in the destination year grid'
    step = -1 if digit == 9 else 1
    vmctl.keys(VM, 'KEY_LEFT' if step < 0 else 'KEY_RIGHT')
    assert selected(wait_state(True, 'keyboard-year-move'), digit + 1 + step), 'year grid lost keyboard focus after the click'
    vmctl.keys(VM, 'KEY_ENTER')
    months = wait_state(True, 'keyboard-year-drill')
    assert months.crop(month) != drilled.crop(month) and selected(months, month_number - 1), 'Enter did not drill into the selected year'
    month_step = -1 if month_number == 12 else 1
    vmctl.keys(VM, 'KEY_LEFT' if month_step < 0 else 'KEY_RIGHT')
    assert selected(wait_state(True, 'keyboard-month-move'), month_number - 1 + month_step), 'month grid lost keyboard focus after Enter'
    vmctl.keys(VM, 'KEY_ENTER')
    assert wait_state(True, 'keyboard-month-drill').crop(month) != months.crop(month), 'Enter did not drill into the selected month'
    for _ in range(3):
        click(95, 54)
    vmctl.keys(VM, 'KEY_RIGHT')
    vmctl.keys(VM, 'KEY_ENTER')
    assert selected(wait_state(True, 'keyboard-decade-drill'), digit + 1 + step), 'keyboard decade drill changed the year digit'
    vmctl.keys(VM, 'KEY_ESC')
    wait_state(False, 'escape')
    click_clock(13)
    wait_state(True, 'opened-from-date')
    click_clock(13)
    wait_state(False, 'toggled-closed')
    # A second snapshot catches a clock click that closes on press but reopens on release.
    time.sleep(0.5)
    assert not is_open(snapshot(f'{tag}-after-toggle'), scale)
    click_clock()
    wait_state(True, 'reopened')
    vmctl.pointer(VM, before.width // 2, before.height // 3, 'left')
    wait_state(False, 'outside-click')
    click_clock()
    wait_state(True, 'before-panel-click')
    vmctl.pointer(VM, before.width // 2, before.height - round(20 * scale), 'left')
    wait_state(False, 'panel-click')
    vmctl.pointer(VM, before.width // 2, before.height // 3)
    neighbors = (0, before.height - round(44 * scale), before.width - round(84 * scale), before.height)
    assert snapshot(f'{tag}-panel-after').crop(neighbors) == before.crop(neighbors), 'neighboring panel changed'

    def desktop_shown():
        return user('qdbus6 org.kde.KWin /KWin org.kde.KWin.showingDesktop') == 'true'

    showing = desktop_shown()
    for expected in (not showing, showing):
        vmctl.pointer(VM, before.width - round(11 * scale), before.height - round(21 * scale), 'left')
        wait_for(lambda: desktop_shown() == expected, 'Show Desktop')
        assert not is_open(snapshot(f'{tag}-show-desktop-{expected}'), scale)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vmctl.start(VM)
    install()
    toggle('windows')
    output = json.loads(user('kscreen-doctor -j'))['outputs'][0]
    name, original_scale = output['name'], output['scale']
    try:
        for scale in (1, 1.5):
            user(f'kscreen-doctor output.{name}.scale.{scale}')
            time.sleep(3)
            check_popup(scale)
    finally:
        user(f'kscreen-doctor output.{name}.scale.{original_scale}')
        toggle('current')
    print(f'Calendar popup smoke checks passed; screenshots: {OUT}')


if __name__ == '__main__':
    main()
