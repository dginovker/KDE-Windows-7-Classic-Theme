#!/usr/bin/env python3
"""Exercise the Classic calendar (#33, #56) in the lab without opening the time KCM."""
from pathlib import Path
import json
import sys
import time

from PIL import Image, ImageChops

from lab import ROOT, VM, install, shot, toggle, user, vmctl, wait_for

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/win7-calendar-test')
BLACK = (0, 0, 0)
FACE = (212, 208, 200)
WHITE = (255, 255, 255)
BLUE = (10, 36, 106)
FOCUS = (245, 219, 149)
REFERENCE = ROOT / 'reference/screenshots/w7-calendar.png'
EVEN_FOCUS_REFERENCE = REFERENCE.with_name('w7-calendar-focus-even.png')


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


def points(image, matches):
    return {(x, y) for y in range(image.height) for x in range(image.width)
            if matches(image.getpixel((x, y)))}


def check_days(scale, opened, snap, click):
    x, y = geometry(opened, scale)

    def point(dx, dy):
        return x + round(dx * scale), y + round(dy * scale)

    def cell_origin(index):
        return 15 + index % 7 * 23, 87 + index // 7 * 15

    def selected(image):
        cells = []
        for i in range(42):
            cx, cy = cell_origin(i)
            if image.getpixel(point(cx + 3, cy + 4)) == BLUE:
                cells.append(i)
        assert len(cells) == 1, f'{scale:g}x: expected one navy day, got {cells}'
        return cells[0]

    def cell(image, index):
        cx, cy = cell_origin(index)
        return image.crop((*point(cx, cy), *point(cx + 23, cy + 15)))

    with Image.open(REFERENCE) as ref:
        ref = ref.convert('RGB')
    def ink_box(image):
        return ImageChops.difference(image, Image.new('RGB', image.size, WHITE)).getbbox()

    for i in range(7):
        column = 964 + i * 23
        native = ink_box(ref.crop((column, 582, column + 23, 598)))
        lab = ink_box(opened.crop((*point(15 + i * 23, 69), *point(15 + (i + 1) * 23, 85))))
        assert native and lab, f'weekday column {i} has no label'
        for lo, hi in ((0, 2), (1, 3)):
            # Compare logical ink spans, allowing Wine Tahoma's glyph metrics and scale rounding.
            assert abs((lab[hi] - lab[lo]) / scale - (native[hi] - native[lo])) <= 3, (i, native, lab)
            assert abs((lab[lo] + lab[hi]) / scale - (native[lo] + native[hi])) <= 5, (i, native, lab)
    with Image.open(EVEN_FOCUS_REFERENCE) as even:
        native_cues = [points(ref.crop((1102, 630, 1125, 645)), lambda rgb: rgb == FOCUS),
                       points(even.convert('RGB'), lambda rgb: rgb == FOCUS)]
    assert all(len(cue) == 32 for cue in native_cues) and not native_cues[0] & native_cues[1]

    def check_cue(image, index, focused):
        crop = cell(image, index)
        if scale == 1:
            mask = points(crop, lambda rgb: rgb == FOCUS)
            px, py = point(*cell_origin(index))
            phase = (px + py) % 2
            expected = native_cues[phase] if focused else set()
            assert mask == expected, (index, (px, py), focused, len(mask), len(mask & expected))
        else:
            # Allow fractional compositor resampling. Require the colored spans to stay inset
            # against both horizontal edges of the selected cell, not exact native pixels.
            mask = points(crop, lambda rgb: rgb[0] - rgb[2] > 35 and rgb[1] - rgb[2] > 25)
            for top in (True, False):
                xs = [x for x, y in mask if (y < 4 if top else y >= crop.height - 4)]
                if focused:
                    assert xs and min(xs) <= 5 and max(xs) >= crop.width - 6, (index, crop.size, top)
                else:
                    assert not xs, 'scaled focus cue remained after Tab'

    today = selected(opened)
    check_cue(opened, today, True)
    step = 1 if int(user('date +%d')) == 1 else -1
    vmctl.keys(VM, 'KEY_RIGHT' if step > 0 else 'KEY_LEFT')
    moved = snap('day-arrow-key')
    assert selected(moved) == today + step, 'arrow key did not select the neighboring day'
    check_cue(moved, today + step, True)
    # The separate Today outline is still visible after moving away from today's date.
    today_edge = cell(moved, today).crop((4, 0, 8, 1 if scale == 1 else 3))
    assert any(color == BLUE for _, color in today_edge.getcolors()), 'Today outline disappeared'
    vmctl.keys(VM, 'KEY_TAB')
    blurred = snap('day-grid-blurred')
    assert selected(blurred) == today + step, 'Tab changed the selection'
    check_cue(blurred, today + step, False)
    vmctl.keys(VM, 'KEY_LEFTSHIFT', 'KEY_TAB')
    refocused = snap('day-grid-refocused')
    assert selected(refocused) == today + step, 'Shift+Tab changed the selection'
    check_cue(refocused, today + step, True)
    cx, cy = cell_origin(today)
    click(cx + 11, cy + 7)
    clicked = snap('day-pointer')
    assert selected(clicked) == today, 'click did not select today again'
    check_cue(clicked, today, True)


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
    check_days(scale, opened, lambda name: wait_state(True, name), click)
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
    current_clock = 'plugin=org.kde.plasma.digitalclock'
    classic_clock = 'plugin=org.win7classic.clock'

    def clocks():
        return user('grep -E "^plugin=(org.kde.plasma.digitalclock|org.win7classic.clock)$" '
                    '~/.config/plasma-org.kde.plasma.desktop-appletsrc').splitlines()

    current_clocks = clocks()
    assert current_clock in current_clocks and classic_clock not in current_clocks, current_clocks
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
    assert clocks() == current_clocks, 'current-mode clock applets changed'
    print(f'Calendar popup checks passed; screenshots: {OUT}')


if __name__ == '__main__':
    main()
