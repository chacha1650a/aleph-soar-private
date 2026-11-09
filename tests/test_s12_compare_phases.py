"""Offline normal-user evidence, including missing/changed/misattributed inputs."""
from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.s12_compare_phases import PHASES, compare  # noqa: E402


@pytest.fixture
def evidence(tmp_path):
    meta = {'run_id': 'S12-SYNTHETIC-01', 'normal_source': '203.0.113.100',
            'attack_source': '203.0.113.41', 'target': 'http://10.250.0.2:5000/login',
            'baseline_ms': 1000, 'interval_seconds': 2, 'timeout_seconds': 5,
            'duration_seconds': 6, 'phases': {}}
    for index, phase in enumerate(PHASES):
        path = tmp_path / (phase + '.csv')
        stamp = datetime(2026, 11, 3, 10, tzinfo=timezone(timedelta(hours=9))) + timedelta(seconds=index * 30)
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ts_kst', 'label', 'source', 'status', 'ms', 'error'])
            for i in range(4):
                writer.writerow([(stamp+timedelta(seconds=2*i)).isoformat(), phase, '203.0.113.100',
                                 200, 1200 if phase == 'before_block' else 100, ''])
        sidecar = {'url': meta['target'], 'url_redacted': False, 'label': phase,
                   'sample_count': 4, 'csv_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   **{key: meta[key] for key in ('interval_seconds', 'timeout_seconds', 'duration_seconds')}}
        Path(str(path)+'.meta.json').write_text(json.dumps(sidecar), encoding='utf-8')
        meta['phases'][phase] = {'csv': path.name, 'load_running': phase != 'after_release'}
    return tmp_path, meta


def rewrite_csv(folder, phase, transform):
    path = folder / (phase+'.csv')
    path.write_text(transform(path.read_text(encoding='utf-8')), encoding='utf-8')
    sidecar = Path(str(path)+'.meta.json')
    data = json.loads(sidecar.read_text(encoding='utf-8'))
    data['csv_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(data), encoding='utf-8')


def test_full_comparison_is_http_evidence_with_effect_still_unverified(evidence):
    folder, meta = evidence
    report = compare(meta, folder)
    assert report['comparison_ready'] is True
    assert report['normal_http_recovered'] is True
    assert report['normal_http_ok_after_release'] is True
    assert report['recovered_while_load_running_declared'] is True
    assert report['effect_verified'] is None and report['business_verified'] is None
    assert report['phases']['before_block']['classification_counts'] == {'slow_success': 4}


def test_ended_load_is_not_reported_as_recovery_during_load(evidence):
    folder, meta = evidence
    meta['phases']['recovery']['load_running'] = False
    assert compare(meta, folder)['recovered_while_load_running_declared'] is False


@pytest.mark.parametrize('missing', PHASES)
def test_missing_phase_stays_null_and_cannot_complete_comparison(evidence, missing):
    folder, meta = evidence
    meta['phases'][missing] = None
    result = compare(meta, folder)
    assert result['phases'][missing] is None and result['normal_http_recovered'] is None


def test_old_probe_without_sidecar_can_be_summarized_but_not_verified(evidence):
    folder, meta = evidence
    (folder/'recovery.csv.meta.json').unlink()
    result = compare(meta, folder)
    assert result['comparison_ready'] is False and result['normal_http_recovered'] is None


@pytest.mark.parametrize('field,value', [('timeout_seconds', 3), ('interval_seconds', 1),
                                       ('duration_seconds', 60), ('url', 'http://10.250.0.2:5000/api/v1/health'),
                                       ('csv_sha256', '0'*64)])
def test_different_probe_conditions_or_csv_are_rejected(evidence, field, value):
    folder, meta = evidence
    path = folder/'recovery.csv.meta.json';data=json.loads(path.read_text())
    data[field] = value;path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='probe metadata'):
        compare(meta, folder)


@pytest.mark.parametrize('source', ['203.0.113.41', '10.250.0.100'])
def test_attack_or_vpn_source_is_not_normal_client_evidence(evidence, source):
    folder, meta = evidence
    meta['normal_source'] = source
    with pytest.raises(ValueError, match='separate'):
        compare(meta, folder)


def test_successful_attack_denial_is_not_normal_user_recovery(evidence):
    folder, meta = evidence
    rewrite_csv(folder, 'recovery', lambda s: s.replace(',200,100,', ',403,100,'))
    report = compare(meta, folder)
    assert report['normal_http_recovered'] is False
    assert report['phases']['recovery']['classification_counts'] == {'unexpected_status': 4}


def test_normal_throughout_does_not_fabricate_a_recovery(evidence):
    folder, meta = evidence
    rewrite_csv(folder, 'before_block', lambda s: s.replace(',200,1200,', ',200,100,'))
    assert compare(meta, folder)['normal_http_recovered'] is False


def test_reused_and_overlapping_phase_data_are_rejected(evidence):
    folder, meta = evidence
    meta['phases']['recovery'] = deepcopy(meta['phases']['after_block'])
    with pytest.raises(ValueError, match='distinct'):
        compare(meta, folder)


def test_probe_emits_hash_bound_sidecar_and_preserves_existing_outputs(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Length', '0');self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    thread.start()
    path = tmp_path/'probe.csv'
    command = [sys.executable, str(ROOT/'tools/s12_probe.py'), '--url',
               f'http://127.0.0.1:{server.server_port}/login?token=synthetic-secret',
               '--source', '127.0.0.1', '--interval', '.02', '--duration', '.08',
               '--timeout', '1', '--label', 'SYNTHETIC', '--out', str(path)]
    try:
        subprocess.run(command, capture_output=True, check=True, timeout=10)
        sidecar = json.loads(Path(str(path)+'.meta.json').read_text())
        assert sidecar['csv_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert sidecar['url_redacted'] is True and 'synthetic-secret' not in json.dumps(sidecar)
        assert sidecar['interval_seconds'] == .02 and sidecar['timeout_seconds'] == 1
        assert sidecar['sample_count'] >= 1
        assert subprocess.run(command, capture_output=True, timeout=10).returncode != 0
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sidecar['csv_sha256']
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
