"""Bounded read-only file adapters. Metadata preserves owner-declared scope."""

import copy
import csv
import hashlib
import os
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker

from .models import FORMATS, LabError, MAX_BYTES, digest, instant, parse_json, policy, read_json, validate, validate_receipt
from .store import contained


def load_profile(path):
    profile = read_json(path)
    validate("collector-profile", profile)
    root = Path(profile["source_root"])
    if not root.is_absolute():
        root = Path(path).absolute().parent / root
    profile["source_root"] = str(root.absolute())
    return profile


def field(record, dotted):
    value = record
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise LabError("Mapped source field is missing.")
        value = value[part]
    return value


def filterlog_event(line, year, offset):
    """Only the documented BSD-prefixed IPv4 ICMP echo-request layout."""
    match = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+"
                      r"(\d{2}:\d{2}:\d{2})\s+.*?\bfilterlog(?:\[\d+\])?:\s*(.*)$", line)
    if not match:
        raise LabError("Unsupported filterlog prefix.")
    month = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split().index(match[1]) + 1
    at = f"{year:04d}-{month:02d}-{int(match[2]):02d}T{match[3]}{offset}"
    instant(at)  # Never infer a year or timezone from the machine running the collector.
    data = next(csv.reader([match[4]], strict=True))
    if len(data) != 23 or data[8] != "4" or data[15:17] != ["1", "icmp"] or data[20] != "request":
        raise LabError("Unsupported filterlog protocol layout.")
    if data[4] != "em0" or data[6] != "block" or data[7] != "in":
        raise LabError("Filterlog record is outside the supported WAN block projection.")
    fields = dict(rule="pfsense-block", interface=data[4], direction=data[7], action=data[6],
                  tracker=int(data[3]), icmp_id=int(data[21]), icmp_seq=int(data[22]), dst_ip=data[19], proto="ICMP")
    identity = {"at": instant(at).isoformat(), "src_ip": data[18], "fields": fields}
    return dict(key="pf-" + digest(identity), at=at, src_ip=data[18], fields=fields)


def project(record, projection, identity):
    if projection["mode"] == "identity":
        if identity["kind"] != "filterlog-ipv4-icmp-v1":
            raise LabError("Identity projection requires a complete filterlog identity.")
        return filterlog_event(field(record, identity["message"]), identity["source_year"], identity["source_utc_offset"])
    key = (field(record, identity["path"]) if identity["kind"] == "field-v1" else
           filterlog_event(field(record, identity["message"]), identity["source_year"], identity["source_utc_offset"])["key"])
    return dict(key=key, at=field(record, projection["at"]), src_ip=field(record, projection["src_ip"]),
                fields={name: field(record, source) for name, source in projection["fields"].items()})


def collect_file(card, seat, phase, profile):
    """Return a validated receipt and collection exit code; never promote metadata."""
    validate("collector-profile", profile)
    root = Path(profile["source_root"])
    if profile["adapter"] == "file-export-v1":
        receipt = read_json(contained(root, profile["export"]))
        validate_receipt(card, receipt)
        return receipt, 3 if any(c["query_status"] in ("failed", "incomplete") or c["availability"] == "unknown"
                                for c in receipt["checks"]) else 0
    metadata = read_json(contained(root, profile["metadata"]))
    validate_receipt(card, metadata)
    if (metadata["seat"], metadata["phase"]) != (seat, phase):
        raise LabError("Source metadata has a different seat or phase.")
    receipt = copy.deepcopy(metadata)
    specs = {s["id"] for s in policy(card)["checks"] if s["seat"] == seat and s["kind"] == "events"}
    projections = profile.get("projections", [])
    projected = [p["check_id"] for p in projections] if profile["adapter"] == "jsonl-events-v1" else profile["check_ids"]
    if len(projected) != len(set(projected)) or set(projected) != specs:
        raise LabError("Adapter must project exactly this seat's required event checks.")
    if profile["adapter"] == "filterlog-ipv4-icmp-v1" and seat != "B":
        raise LabError("Raw filterlog projection is supported only for B's source check.")
    if any(p["check_id"] == "D.normalized" and p["mode"] != "mapped" for p in projections):
        raise LabError("D normalization must read actual normalized fields, not derive them from raw text.")
    by_id = {c["check_id"]: c for c in receipt["checks"]}
    if not specs or not specs <= by_id.keys():
        raise LabError("Required event metadata is missing.")
    source = contained(root, profile["source"])
    with source.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    changed = (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
    truncated = len(raw) > MAX_BYTES
    bounded = raw[:MAX_BYTES]
    lines = bounded.splitlines(keepends=True)
    if truncated and lines and not bounded.endswith(b"\n"):
        lines = lines[:-1]  # A byte limit may cut a JSON record or log line.
    limit_hit = len(lines) > profile["max_lines"]
    lines = lines[:profile["max_lines"]]
    for cid in specs:
        by_id[cid]["events"] = []  # Do not reuse stale events from the metadata template.
        by_id[cid]["count"] = None  # Event counts are derived after the comparison's scope filter.
    event_schema = read_json(FORMATS / "receipt.schema.json")["properties"]["checks"]["items"]["properties"]["events"]["items"]
    event_validator = Draft202012Validator(event_schema, format_checker=FormatChecker())
    rejected = 0
    rejected_by_check = {cid: 0 for cid in specs}
    for line in lines:
        if not line.strip():
            continue
        try:
            if profile["adapter"] == "filterlog-ipv4-icmp-v1":
                event = filterlog_event(line.decode("utf-8").rstrip("\r\n"), profile["source_year"], profile["source_utc_offset"])
                record = None
            else:
                record = parse_json(line)
        except (LabError, ValueError, TypeError, KeyError, UnicodeError, csv.Error, OverflowError):
            rejected += 1
            for cid in specs:
                rejected_by_check[cid] += 1
            continue
        line_failed = False
        for cid in specs:
            try:
                derived = (copy.deepcopy(event) if record is None else
                           project(record, next(p for p in projections if p["check_id"] == cid), profile["identity"]))
                if next(event_validator.iter_errors(derived), None) is not None:
                    raise LabError("Projected event has an invalid format.")
                by_id[cid]["events"].append(derived)
            except (LabError, ValueError, TypeError, KeyError, UnicodeError, csv.Error, OverflowError):
                line_failed = True
                rejected_by_check[cid] += 1
        rejected += int(line_failed)
    partial = truncated or limit_hit or rejected > 0 or changed
    if partial:
        for cid in specs:
            if truncated or limit_hit or changed or rejected_by_check[cid]:
                by_id[cid].update(query_status="incomplete", coverage="partial", count=None, reason_code="SOURCE_PARSE_INCOMPLETE")
    receipt["collection"] = dict(adapter=profile["adapter"], read_sha256=hashlib.sha256(bounded).hexdigest(),
                                 metadata_sha256=digest(metadata), profile_sha256=digest(profile), source_bytes=len(bounded),
                                 source_truncated=truncated, source_changed=changed, line_limit_hit=limit_hit, rejected_lines=rejected)
    validate_receipt(card, receipt)
    return receipt, 3 if partial or any(c["query_status"] in ("failed", "incomplete") or c["availability"] == "unknown"
                                      for c in receipt["checks"]) else 0
