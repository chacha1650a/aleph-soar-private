"""SQLite consistent backup/restore-to-new-file. Never overwrites a running DB."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import time


def copy_database(source, destination, timeout=30):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if not source.is_file():
        raise ValueError('source database does not exist')
    if destination.exists() or destination.is_symlink():
        raise ValueError('destination already exists; use a NEW file')
    if not destination.parent.is_dir():
        raise ValueError('destination parent must already exist')
    # Exclusive reservation prevents accidental replacement. Failed copies are
    # removed; neither the source nor a pre-existing destination is deleted.
    with destination.open('xb'):
        pass
    deadline = time.monotonic() + timeout
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('backup deadline exceeded')
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst, pages=64, progress=progress, sleep=.05)
                if dst.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('database integrity check failed')
                tables = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'tickets', 'actions'}.issubset(tables):
                    raise ValueError('not a ticket-store database')
                counts = {t: dst.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in ('tickets','actions')}
        return {'ok': True, 'mode': 'copy_to_new_database', 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                'counts': counts, 'integrity': 'ok', 'live_restore_performed': False}
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(copy_database(args.source, args.out), sort_keys=True))
    except (OSError, ValueError, sqlite3.Error, TimeoutError) as exc:
        parser.exit(1, f'Backup/restore copy failed: {type(exc).__name__}\n')


if __name__ == '__main__':
    main()
