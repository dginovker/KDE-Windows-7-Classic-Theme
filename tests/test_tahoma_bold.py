#!/usr/bin/env python3
"""Check a staged or extracted package's Tahoma with FontTools and HarfBuzz."""
import argparse
from pathlib import Path

from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb


def shape(font, text, features=None):
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, features)
    return [(i.codepoint, p.x_advance, p.y_advance, p.x_offset, p.y_offset)
            for i, p in zip(buf.glyph_infos, buf.glyph_positions)]


def ink_area(font, name):
    glyphs = font.getGlyphSet()
    pen = AreaPen(glyphs)
    glyphs[name].draw(pen)
    return abs(pen.value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fonts', type=Path, help='package usr/share/fonts/win7-classic directory')
    parser.add_argument('--wine-fonts', type=Path, default=Path('/usr/share/wine/fonts'))
    args = parser.parse_args()
    regular = args.fonts / 'tahoma.ttf'
    assert regular.read_bytes() == (args.wine_fonts / regular.name).read_bytes(), 'regular Tahoma changed'
    bold = args.fonts / 'tahomabd.ttf'
    original = hb.Font(hb.Face((args.wine_fonts / bold.name).read_bytes()))
    packaged = hb.Font(hb.Face(bold.read_bytes()))
    with TTFont(bold) as bold_font, TTFont(regular) as regular_font:
        for text in ('fi', 'fl'):
            shaped = shape(packaged, text)
            glyphs = [bold_font.getGlyphName(gid) for gid, *_ in shaped]
            expected = [bold_font.getBestCmap()[ord(char)] for char in text]
            assert glyphs == expected, f'{text} selected {glyphs}, not the separate bold glyphs {expected}'
            assert shaped == shape(original, text, {'liga': False}), f'{text}: changed unligated positioning'
            areas = [(ink_area(bold_font, name), ink_area(regular_font, regular_font.getBestCmap()[ord(char)]))
                     for char, name in zip(text, glyphs)]
            assert all(bold_area > regular_area for bold_area, regular_area in areas), (text, areas)
            print(f'{text}: {glyphs}, advances {[row[1] for row in shaped]}, bold/regular ink areas {areas}')


if __name__ == '__main__':
    main()
