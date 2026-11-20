#!/usr/bin/env python3
"""Real KF6/parser/recorder race tests, using only disposable XDG roots and no session."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

NAME = 'kactivitymanagerd-pluginsrc'
GROUP = '[Plugin-org.kde.ActivityManager.Resources.Scoring]'


def cfg(value=0, extra='', header=GROUP):
    return f'{header}\nwhat-to-remember={value}\n{extra}'


def main(build):
    assert os.geteuid() != 0, 'permission regression requires a regular user'
    with tempfile.TemporaryDirectory(prefix='frequent-policy-', dir=build) as area:
        root = Path(area)
        u, high, low, state, work = (root / d for d in ('user', 'high', 'low', 'state', 'work'))
        a, b = work / 'Alpha', work / 'Beta'
        for d in (u, high, low, state / 'win7-classic', a, b):
            d.mkdir(parents=True)
        mode = state / 'win7-classic/mode'
        mode.write_text('windows\n')
        store = state / 'win7-explorer/frequent.json'
        env = dict(PATH='/usr/bin', HOME=str(root), LC_ALL='C', XDG_CONFIG_HOME=str(u),
                   XDG_CONFIG_DIRS=f'{high}:{low}', XDG_STATE_HOME=str(state), KDE_SKIP_KDERC='1',
                   TEST_REAL_READER=str(build / 'win7-explorer-policy'))

        def run(action, path=a, **extra):
            return subprocess.check_output([build / 'probe', action, path], env=env | extra, text=True).splitlines()

        def deny(before, **extra):
            assert run('rows', **extra) == []
            assert run('activate', **extra) == ['no']
            run('record', **extra)
            assert store.read_bytes() == before

        if str(a).startswith('/tmp/'):
            run('record')
            assert not store.exists(), 'stock /tmp exclusion was ignored'
        (u / NAME).write_text(f'{GROUP}\nurl-filters=\n')
        run('record'); run('record', b); run('record'); run('record', b); run('record')
        assert run('rows') == list(map(str, [a, b]))
        assert run('activate') == ['yes']
        before = store.read_bytes()
        print('real aggregate ranking/tie recency/activation; stock /tmp exclusion when applicable')
        (low / NAME).write_text(cfg(2))
        deny(before)
        (u / NAME).write_text(cfg(extra='url-filters=\n'))
        assert run('rows') == list(map(str, [a, b]))
        for content in (cfg(2).replace('what-to-remember=', 'what-to-remember[$i]='),
                        cfg(2, header=GROUP+'[$i]'), cfg(2, header='[$i]\n'+GROUP)):
            (low / NAME).write_text(content)
            deny(before)
        print('mutable native user precedence; native immutable key, group and file deny all operations')
        (low / NAME).write_text(cfg(2))
        for operation, result in (('rows', []), ('activate', ['no']), ('record', [])):
            try:
                assert run(operation, TEST_DURING_PARSE='chmod') == result
                assert store.read_bytes() == before
            finally:
                low.chmod(0o700)
        low.chmod(0)
        try:
            deny(before)
        finally:
            low.chmod(0o700)
        print('unreadable lower deny before read and deterministic chmod after capture: no rows, activation, write')
        (low / NAME).write_text(cfg())
        deny(before, TEST_DURING_PARSE='aba')
        run('record', TEST_BEFORE_COMMIT=str(u / NAME))
        assert store.read_bytes() == before and 'what-to-remember=2' in (u / NAME).read_text()
        deny(before)
        print('deny/allow ABA during parse and flip after real save starts before commit: no leak')
        (u / NAME).write_text(cfg(extra=f'url-filters={work}/Al*\n'))
        assert run('rows') == [str(b)] and run('activate') == ['no']
        run('record')
        assert store.read_bytes() == before
        (u / NAME).write_text(cfg(extra='url-filters=\n'))
        mode.write_text('current\n')
        deny(before)
        mode.write_text('windows\n')
        assert run('rows') == list(map(str, [a, b]))
        print('filtered paths withheld from recording, display and activation; current mode leaves store byte-identical')
        unrelated = root / 'unrelated.txt'
        unrelated.write_bytes(b'unrelated contents\n')
        run('record', TEST_SWAP_HISTORY=str(store), TEST_SWAP_FIXTURE=str(unrelated))
        assert unrelated.read_bytes() == b'unrelated contents\n', 'save overwrote a different file through the swapped entry'
        assert not store.is_symlink() and dict(json.loads(store.read_bytes()))[str(a)] == 4
        assert list(store.parent.iterdir()) == [store], 'staging file was not removed'
        print('deterministic post-read/pre-save swap replaced only the history entry; unrelated file untouched')
        store.write_text('invalid')
        deny(b'invalid')
        store.unlink()
        assert run('rows') == [] and run('activate') == ['no'] and not store.exists()
        print('malformed and deleted stores cannot activate stale rows')


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
