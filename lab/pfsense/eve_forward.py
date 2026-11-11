#!/usr/local/bin/python3.11
"""Forward Suricata EVE alert lines from pfSense to Graylog Raw TCP (local lab).

- Reads eve.json of every suricata_em* instance under /var/log/suricata.
- Sends only lines with "event_type":"alert", one JSON object + LF per line,
  to TARGET (default 10.250.0.100:5515), the contract agreed with B on 10/23.
- Starts at the end of each file (no backfill), follows rotation/truncation,
  reconnects with backoff and never retries a line forever (drops after 3 tries,
  counted in the stats line written to syslog).
- No secrets, no payload rewriting. Lab use only; not a team deployment.
"""
import glob
import json
import os
import socket
import sys
import syslog
import time

TARGET = (os.environ.get('EVE_FWD_HOST', '10.250.0.100'), int(os.environ.get('EVE_FWD_PORT', '5515')))
PATTERN = '/var/log/suricata/suricata_em*/eve.json'
POLL = 1.0
STATS_EVERY = 300


class Sender:
    def __init__(self):
        self.sock = None
        self.sent = self.dropped = 0

    def _connect(self):
        s = socket.create_connection(TARGET, timeout=5)
        s.settimeout(5)
        self.sock = s

    def send(self, line):
        data = line.rstrip('\n').encode('utf-8') + b'\n'
        for attempt in range(3):
            try:
                if self.sock is None:
                    self._connect()
                self.sock.sendall(data)
                self.sent += 1
                return
            except OSError:
                if self.sock is not None:
                    try:
                        self.sock.close()
                    except OSError:
                        pass
                self.sock = None
                time.sleep(min(2 ** attempt, 5))
        self.dropped += 1


def is_alert(line):
    if '"event_type":"alert"' not in line:
        return False
    try:
        return json.loads(line).get('event_type') == 'alert'
    except ValueError:
        return False


def main():
    syslog.openlog('haedam-eve-forward', syslog.LOG_PID, syslog.LOG_LOCAL1)
    syslog.syslog(syslog.LOG_NOTICE, 'start target=%s:%d' % TARGET)
    sender = Sender()
    files = {}  # path -> (inode, offset)
    last_stats = time.time()
    while True:
        for path in glob.glob(PATTERN):
            try:
                st = os.stat(path)
            except OSError:
                continue
            inode, offset = files.get(path, (None, None))
            if inode is None:
                files[path] = (st.st_ino, st.st_size)  # start at end, no backfill
                continue
            if st.st_ino != inode or st.st_size < offset:
                offset = 0  # rotated or truncated
            if st.st_size == offset:
                files[path] = (st.st_ino, offset)
                continue
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                fh.seek(offset)
                while True:
                    line = fh.readline()
                    if not line or not line.endswith('\n'):
                        break  # partial line: read again next round
                    offset = fh.tell()
                    if is_alert(line):
                        sender.send(line)
            files[path] = (st.st_ino, offset)
        if time.time() - last_stats >= STATS_EVERY:
            syslog.syslog(syslog.LOG_NOTICE, 'stats sent=%d dropped=%d' % (sender.sent, sender.dropped))
            last_stats = time.time()
        time.sleep(POLL)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
