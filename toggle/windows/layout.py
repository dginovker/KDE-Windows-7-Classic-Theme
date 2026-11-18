"""Byte-local KConfig edits for the staged Plasma applet layout."""
import os
import re
import tempfile


class Layout:
    def __init__(self, text):
        self.text = text
        self.groups = {}
        headers = list(re.finditer(r'(?m)^(\[[^\r\n]+\])(?:\r?\n|$)', text))
        for index, header in enumerate(headers):
            group = tuple(re.findall(r'\[([^\]]*)\]', header[1]))
            if ''.join(f'[{part}]' for part in group) != header[1] or group in self.groups:
                raise ValueError(f'ambiguous layout group: {header[1]}')
            self.groups[group] = (header.start(), headers[index + 1].start() if index + 1 < len(headers) else len(text))

    def value_span(self, group, key):
        if group not in self.groups:
            return None
        start, end = self.groups[group]
        matches = list(re.finditer(r'(?m)^' + re.escape(key) + r'=([^\r\n]*)', self.text[start:end]))
        if len(matches) > 1:
            raise ValueError(f'duplicate {key} in {group}')
        return tuple(start + position for position in matches[0].span(1)) if matches else None

    def get(self, group, key):
        span = self.value_span(group, key)
        return self.text[slice(*span)] if span else None


def replace_layout(path, original, result):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(result.encode('utf-8'))
        os.chmod(temporary, path.stat().st_mode & 0o7777)
        if path.read_bytes() != original:
            raise ValueError(f'{path} changed during migration; refusing to overwrite')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
