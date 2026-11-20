#!/usr/bin/env python3
"""Change synthetic paths after the real client captured them, then run its actual reader."""
import os
from pathlib import Path

root = Path(os.environ['XDG_CONFIG_DIRS'].split(':')[-1])
change = os.environ.get('TEST_DURING_PARSE')
if change == 'chmod':
    root.chmod(0)
elif change == 'aba':
    file = root / 'kactivitymanagerd-pluginsrc'
    old = file.read_bytes()
    file.write_bytes(old.replace(b'what-to-remember=0', b'what-to-remember=2'))
    file.write_bytes(old)
reader = os.environ['TEST_REAL_READER']
os.execv(reader, [reader])
