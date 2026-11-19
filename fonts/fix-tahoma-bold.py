import sys

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otTables import LigatureSubst


with TTFont(sys.argv[1], recalcBBoxes=False, recalcTimestamp=False) as font:
    cmap = font.getBestCmap()
    if not all(c in cmap for c in (ord('f'), ord('i'), ord('l'), 0xFB01, 0xFB02)) or 'GSUB' not in font:
        sys.exit('Tahoma Bold: expected f/i/l and U+FB01/U+FB02 glyphs and GSUB')

    first = cmap[ord('f')]
    expected = {((cmap[ord('i')],), cmap[0xFB01]), ((cmap[ord('l')],), cmap[0xFB02])}
    components = {part for part, _ in expected}
    gsub = font['GSUB'].table
    indices = {i for record in gsub.FeatureList.FeatureRecord if record.FeatureTag == 'liga'
               for i in record.Feature.LookupListIndex}
    found = set()
    # Wine's fi/fl outlines are regular-weight. Use separate letters, as GDI UI text does.
    for i in sorted(indices):
        lookup = gsub.LookupList.Lookup[i]
        for table in lookup.SubTable:
            if lookup.LookupType == 7:
                table = table.ExtSubTable
            if not isinstance(table, LigatureSubst) or first not in table.ligatures:
                continue
            rules = table.ligatures.pop(first)
            found.update((tuple(rule.Component), rule.LigGlyph) for rule in rules
                         if tuple(rule.Component) in components)
            kept = [rule for rule in rules if tuple(rule.Component) not in components]
            if kept:
                table.ligatures[first] = kept
    if found != expected:
        sys.exit(f'Tahoma Bold: expected fi/fl liga rules {sorted(expected)}, found {sorted(found)}')
    font.save(sys.argv[2])
