"""Launcher identities shared by fresh seeding and existing Windows-layout upgrades."""
from pathlib import Path
from urllib.parse import unquote, urlsplit

EXPLORER = 'applications:org.win7classic.explorer.desktop'
DEFAULT_LAUNCHERS = f'applications:firefox.desktop,{EXPLORER},applications:org.kde.konsole.desktop'


def split_launchers(value):
    item, escaped = '', False
    escapes = {'\\': '\\', ',': ',', 's': ' ', 'n': '\n', 'r': '\r', 't': '\t'}
    for char in value:
        if escaped:
            if char not in escapes:
                raise ValueError(f'unsupported escape in launcher list: \\{char}')
            item += escapes[char]
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ',':
            yield item
            item = ''
        else:
            item += char
    if escaped:
        raise ValueError('incomplete escape in launcher list')
    yield item


def normalize_launchers(values):
    result = []
    for value in values:
        for launcher in split_launchers(value):
            if not launcher:
                continue
            url = urlsplit(launcher)
            path = unquote(url.path)
            if url.scheme == 'file' and url.netloc in ('', 'localhost') and not url.query and not url.fragment and (
                    path.startswith(('/usr/share/applications/', '/usr/local/share/applications/')) or
                    '/.local/share/applications/' in path):
                launcher = 'applications:' + Path(path).name
            if launcher in ('preferred://filemanager', 'applications:org.kde.dolphin.desktop'):
                launcher = EXPLORER
            if launcher not in result:
                result.append(launcher)
    return ','.join(launcher.replace('\\', '\\\\').replace(',', '\\,').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') for launcher in result)
