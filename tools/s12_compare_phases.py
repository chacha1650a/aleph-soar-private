"""Offline S12 normal-path four-phase comparison. No network, DB writes or actions."""
import argparse
from collections import Counter
from datetime import datetime
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/ticket-store'))
from ticket_store.s12_measurements import read_run  # noqa: E402

PHASES = ('before_block', 'after_block', 'recovery', 'after_release')


def compare(meta, folder):
    if not re.fullmatch(r'S12-[A-Z0-9-]{2,80}', meta.get('run_id', '')):
        raise ValueError('explicit S12 run_id required')
    normal, attack = (str(ipaddress.IPv4Address(meta[k])) for k in ('normal_source', 'attack_source'))
    if normal == attack or normal.startswith('10.250.0.'):
        raise ValueError('normal source must be separate from attack and D VPN paths')
    url = urlsplit(meta['target'])
    if url.scheme != 'http' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('target must be a plain HTTP URL without secrets')
    target = f'http://{url.hostname}:{url.port or 80}{url.path or "/"}'
    for key in ('baseline_ms', 'interval_seconds', 'timeout_seconds', 'duration_seconds'):
        v = meta[key]
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
            raise ValueError('positive finite measurement settings required')
    if meta['baseline_ms'] >= meta['timeout_seconds'] * 1000:
        raise ValueError('normal-path baseline must be below timeout')
    k = meta.get('k', 3)
    if type(k) is not int or not 1 <= k <= 10:
        raise ValueError('k must be 1..10')
    if set(meta['phases']) != set(PHASES):
        raise ValueError('four explicit phases required; use null for missing data')
    expected = meta.get('expected_status', 200)
    if type(expected) is not int or not 200 <= expected <= 299:
        raise ValueError('normal requests require an expected 2xx status')
    result, warnings, hashes, labels = {}, [], set(), set()
    previous_end = None
    for phase in PHASES:
        spec = meta['phases'][phase]
        if spec is None:
            result[phase] = None
            warnings.append(phase + ':missing')
            continue
        if type(spec.get('load_running')) is not bool:
            raise ValueError('load_running must be explicitly declared for each measured phase')
        path = Path(folder) / spec['csv']
        run = read_run(path, expected)
        if run['sha256'] in hashes or run['label'] in labels:
            raise ValueError('phases require distinct CSVs and labels')
        hashes.add(run['sha256']); labels.add(run['label'])
        if run['source_missing_samples'] or run['source_recorded'] != normal:
            raise ValueError('CSV source must match the separate normal client')
        started = datetime.fromisoformat(run['started_at'])
        if previous_end is not None and started < previous_end:
            raise ValueError('phase windows overlap or are reversed')
        previous_end = datetime.fromisoformat(run['last_completion_estimate'])
        sidecar = Path(str(path) + '.meta.json')
        if not sidecar.exists():
            warnings.append(phase + ':probe_metadata_missing')
        else:
            evidence = json.loads(sidecar.read_text(encoding='utf-8'))
            match = {'url': target, 'url_redacted': False, 'label': run['label'],
                     'csv_sha256': run['sha256'], 'sample_count': run['sample_count'],
                     **{key: meta[key] for key in ('interval_seconds', 'timeout_seconds', 'duration_seconds')}}
            if any(evidence.get(key) != value for key, value in match.items()):
                raise ValueError('probe metadata does not match the CSV or locked measurement settings')
        if run['observed_span_seconds'] < meta['duration_seconds'] * .9:
            warnings.append(phase + ':short_window')
        if run['observed_span_seconds'] > meta['duration_seconds'] + meta['timeout_seconds']:
            warnings.append(phase + ':overlong_window')
        if (run['start_gap_seconds']['max'] or 0) > meta['interval_seconds'] * 1.5:
            warnings.append(phase + ':cadence_exceeded')
        classifications = []
        for sample in run['samples']:
            error = sample['error']
            category = ('timeout' if error == 'timeout' else 'network_error') if error else (
                'server_error' if sample['status'] >= 500 else 'unexpected_status' if not sample['success'] else
                'slow_success' if sample['ms'] > meta['baseline_ms'] else 'healthy')
            classifications.append(category)
        streak = longest = 0
        for category in classifications:
            streak = 0 if category == 'healthy' else streak + 1
            longest = max(longest, streak)
        result[phase] = {key: run[key] for key in ('sha256', 'source_recorded', 'started_at',
            'last_completion_estimate', 'observed_span_seconds', 'sample_count', 'success_percent',
            'failure_count', 'successful_latency_ms', 'status_counts')}
        result[phase].update(classification_counts=dict(Counter(classifications)),
            last_k_healthy=len(classifications) >= k and all(x == 'healthy' for x in classifications[-k:]),
            degraded_streak=longest >= k, load_running_declared=spec['load_running'])
        if len(classifications) < k:
            warnings.append(phase + ':too_few_samples')
    ready = not warnings
    recovered = ready and result['before_block']['degraded_streak'] and result['recovery']['last_k_healthy']
    return {'run_id': meta['run_id'], 'scope': 'separate_normal_client_http_only', 'phases': result,
            'comparison_ready': ready, 'warnings': warnings,
            'normal_http_recovered': recovered if ready else None,
            'normal_http_ok_after_release': result['after_release']['last_k_healthy'] if ready else None,
            'recovered_while_load_running_declared': bool(recovered and result['before_block']['load_running_declared']
                and result['recovery']['load_running_declared']) if ready else None,
            'load_state_evidence': 'operator_declared_not_verified_by_probe',
            'business_verified': None, 'effect_verified': None, 'causal_effect_verified': None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    args = parser.parse_args(argv)
    path = Path(args.manifest)
    try:
        result = compare(json.loads(path.read_text(encoding='utf-8')), path.parent)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
