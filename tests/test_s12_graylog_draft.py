import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "lab" / "s12" / "graylog" / "s12-request-flood.json"
NOTIFICATION = ROOT / "infra" / "graylog" / "notifications" / "s12-n8n-haedam-s12.json"
WORKFLOW = ROOT / "infra" / "n8n" / "workflows" / "haedam-20-s12-main.json"


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_notification_reaches_haedam_20_webhook_with_required_fields():
    n = load(NOTIFICATION)
    wf = load(WORKFLOW)[0]
    hook = next(x for x in wf["nodes"] if x["type"].endswith("webhook"))["parameters"]["path"]
    assert n["config"]["url"].endswith("/webhook/" + hook)
    body = n["config"]["body_template"]
    # keys haedam-20 requires before it does anything
    for key in ("event_id", "asset_id", "src_ip"):
        assert f'\\"{key}\\"' in body or f'"{key}"' in body
    assert "${event.fields.src_ip}" in body and "${event.id}" in body


def test_notification_keeps_the_safe_defaults():
    # real actions are switched on only by a separate, approved change to the body
    body = load(NOTIFICATION)["config"]["body_template"]
    assert "dry_run" not in body and "store_real" not in body


def test_definition_is_a_per_source_one_minute_count_with_baseline_values():
    d = load(DEFINITION)
    c = d["config"]
    assert c["group_by"] == ["src_ip"] and c["search_within_ms"] == 60000
    assert d["notifications"] == []                    # attached by D when it is imported
    # the 60 s window slides every 30 s so a 30 s stage always fits in one window; a short grace re-checks while the count stays over N
    assert c["execute_every_ms"] == 30000
    assert d["notification_settings"]["grace_period_ms"] == 60000
    assert c["streams"] == ["6ad95444188b5d4016e9d412"]   # haedam-portal stream on the lab Graylog
    # N = 3 x the busiest 60 s of the 10/30 baseline (31 requests)
    assert c["conditions"]["expression"]["right"]["value"] == 93
    assert re.search(r"event_type:web\.request", c["query"])
    assert "REPLACE_" not in json.dumps(d)


def test_haedam_20_uses_the_measured_independent_health_baseline():
    code = next(x for x in load(WORKFLOW)[0]["nodes"] if "baseline_ms:" in x.get("parameters", {}).get("jsCode", ""))["parameters"]["jsCode"]
    # S12-20261103-D-HEALTH-BASELINE01: normal max 1759.1 ms; 881.4 ms hit K=3 in the normal window
    assert "baseline_ms: 2000" in code and "baseline_source: 'S12-20261103-D-HEALTH-BASELINE01'" in code
    assert "health_timeout_ms: 5000" in code
    # real actions stay off until a separate approved change
    assert "dry_run: true" in code and "store_real: false" in code
