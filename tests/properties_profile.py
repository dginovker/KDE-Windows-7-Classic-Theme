"""Guest-side backup for the live current appearance and the existing Properties test profile."""
from pathlib import Path
import filecmp
import os
import shutil
import stat
import subprocess
import sys
import tempfile


def snapshot(config, target):
    share = Path('/usr/bin/win7-classic').resolve().parent
    subprocess.run([share / 'kconfig-keys', 'save', share / 'windows/keys', config.parent, target], check=True)


def backup(files, config=None):
    saved = Path(tempfile.mkdtemp(prefix='w7prop-config.'))
    try:
        for path in files:
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                (saved / (path.name + '.absent')).touch()
                continue
            if not stat.S_ISREG(mode):
                raise ValueError(f'Not a regular profile file: {path}')
            copy = saved / path.name
            shutil.copy2(path, copy)
            if not filecmp.cmp(path, copy, shallow=False):
                raise OSError(f'Backup does not match {path}')
        if config is not None:
            snapshot(config, saved / 'live-keys.json')
    except BaseException:
        shutil.rmtree(saved)
        raise
    return saved


def restore(saved, path):
    copy = saved / path.name
    absent = saved / (path.name + '.absent')
    if not copy.exists() and absent.is_file():
        path.unlink(missing_ok=True)
        return
    if not copy.is_file() or absent.exists():
        raise OSError(f'Missing or ambiguous backup for {path} in {saved}')
    fd, scratch = tempfile.mkstemp(dir=path.parent, prefix='.w7prop-restore.')
    os.close(fd)
    tmp = Path(scratch)
    try:
        shutil.copy2(copy, tmp)
        if not filecmp.cmp(copy, tmp, shallow=False):
            raise OSError(f'Restore does not match {copy}')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


if __name__ == '__main__':
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'kdeglobals'
    keys = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'win7-classic/profiles/current/keys.json'
    if sys.argv[1] == 'backup':
        print(backup((config, keys), config))
    elif sys.argv[1] == 'verify':
        with tempfile.TemporaryDirectory(prefix='w7prop-verify.') as scratch:
            actual = Path(scratch) / 'keys.json'
            snapshot(config, actual)
            if not filecmp.cmp(Path(sys.argv[2]) / 'live-keys.json', actual, shallow=False):
                raise OSError('Live current appearance does not match the pre-test settings')
    elif sys.argv[1] == 'restore':
        saved = Path(sys.argv[2])
        restore(saved, {'config': config, 'keys': keys}[sys.argv[3]])
    else:
        raise ValueError(sys.argv[1])
