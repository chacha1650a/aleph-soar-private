"""S12 baseline probe: GET a URL at a fixed interval and log latency (KST) to CSV."""
import argparse, csv, statistics, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://10.250.0.2:5000/api/v1/health")
ap.add_argument("--interval", type=float, default=2.0)
ap.add_argument("--duration", type=float, default=1800.0, help="seconds")
ap.add_argument("--timeout", type=float, default=3.0)
ap.add_argument("--label", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()

rows = []
end = time.monotonic() + a.duration
nxt = time.monotonic()
with open(a.out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["ts_kst", "label", "status", "ms", "error"])
    while time.monotonic() < end:
        t0 = time.perf_counter()
        status, err = 0, ""
        try:
            with urllib.request.urlopen(a.url, timeout=a.timeout) as r:
                r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            status, err = e.code, "http"
        except Exception as e:
            err = type(e).__name__
        ms = (time.perf_counter() - t0) * 1000
        ts = datetime.now(KST).isoformat(timespec="milliseconds")
        w.writerow([ts, a.label, status, round(ms, 1), err])
        f.flush()
        rows.append((status, ms, err))
        nxt += a.interval
        time.sleep(max(0, nxt - time.monotonic()))

ok = sorted(ms for s, ms, e in rows if s == 200)
def pct(p):
    return ok[min(len(ok) - 1, int(len(ok) * p))] if ok else float("nan")
print(f"{a.label}: n={len(rows)} ok={len(ok)} fail={len(rows)-len(ok)} "
      f"median={statistics.median(ok) if ok else float('nan'):.1f}ms p95={pct(.95):.1f}ms "
      f"p99={pct(.99):.1f}ms max={max(ok) if ok else float('nan'):.1f}ms")
