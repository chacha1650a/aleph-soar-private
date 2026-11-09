"""Read-only loopback HTTP adapter for home tests, not a deployed n8n transport."""
import http.client
from copy import deepcopy
import json
import re
from urllib.parse import urlencode


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("non-finite JSON number")


def _text(value):
    return isinstance(value, str) and 1 <= len(value) <= 300 and not re.search(r"[\x00-\x1f\x7f]", value)


class TicketHTTP:
    """One GET per observation, no redirects/proxies/retries or mutating methods.

    The timeout is a socket inactivity limit, not an end-to-end deadline.
    base_url must be an explicit literal IPv4 loopback address with a port.
    """

    def __init__(self, base_url, key, *, timeout=2.0):
        match = re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})", base_url) if isinstance(base_url, str) else None
        if not match or not 1 <= int(match[1]) <= 65535:
            raise ValueError("only http://127.0.0.1:<port> is supported for home tests")
        if not isinstance(key, str) or not re.fullmatch(r"[!-~]{16,200}", key):
            raise ValueError("key must be 16-200 printable ASCII characters")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 10:
            raise ValueError("timeout must be greater than 0 and at most 10 seconds")
        self.port, self.key, self.timeout = int(match[1]), key, timeout

    def apply(self, expected):
        if not isinstance(expected, dict):
            raise ValueError("expected must be an object")
        expected = deepcopy(expected)
        if expected.get("seat") not in ("A", "B", "C", "D") or not _text(expected.get("group_key")):
            raise ValueError("apply requires seat and group_key")
        query = {name: expected[name] for name in ("seat", "group_key")}
        return {"mode": "apply", "expected": expected, "observation": self._get("open", query)}

    def release(self, expected):
        if not isinstance(expected, dict):
            raise ValueError("expected must be an object")
        expected = deepcopy(expected)
        r = expected.get("resource")
        if (not isinstance(r, dict) or set(r) != {"asset_id", "via", "action", "target"}
                or not all(_text(r[k]) for k in r) or r["via"] not in ("portal", "pfsense", "wazuh-ar", "manual")
                or not re.fullmatch(r"[a-z][a-z_]{1,31}", r["action"])):
            raise ValueError("release requires the exact four-field resource")
        return {"mode": "release", "expected": expected, "observation": self._get("active", dict(r))}

    def _get(self, route, query):
        observation = {"query": query, "status": None, "transport_error": False,
                       "transport": "loopback_http"}
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        response = None
        try:
            connection.request("GET", "/api/v1/tickets/" + route + "?" + urlencode(query),
                               headers={"X-Response-Key": self.key, "Accept": "application/json"})
            response = connection.getresponse()
            observation["status"] = response.status
            # Never follow Location, even to another loopback service.
            if 300 <= response.status < 400:
                observation["error"] = "redirect_blocked"
                return observation
            if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                observation["error"] = "non_json_response"
                return observation
            raw = response.read(65537)
            if len(raw) > 65536:
                observation["error"] = "response_too_large"
                return observation
            if response.length not in (None, 0):
                raise http.client.IncompleteRead(raw, response.length)
            try:
                body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
                if not isinstance(body, dict):
                    raise ValueError("body must be an object")
            except (UnicodeDecodeError, ValueError, RecursionError):
                observation["error"] = "invalid_json_response"
                return observation
            observation["body"] = body
            return observation
        except (OSError, http.client.HTTPException):
            # Exception text can include request/host information; do not echo it.
            observation.update(status=None, transport_error=True, error="transport_failure")
            observation.pop("body", None)
            return observation
        finally:
            if response is not None:
                response.close()
            connection.close()
