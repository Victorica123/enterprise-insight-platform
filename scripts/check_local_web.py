"""Read-only regression gate for the localhost nginx browser entry point.

The empty login payload reaches validation only when nginx preserves the
browser's Host (including its port). No account or credential is needed.
"""

from __future__ import annotations

import argparse
import json

from local_acceptance import http_request


def check_web(port: int) -> dict[str, object]:
    if not 1 <= port <= 65535:
        raise ValueError("The localhost port must be between 1 and 65535")
    origin = f"http://127.0.0.1:{port}"
    login = f"{origin}/media/api/auth/login"
    status, body = http_request(origin)
    assert status == 200 and b"<html" in body.lower(), "Web entry point is unavailable"
    status, _ = http_request(f"{origin}/agent/health")
    assert status == 200, "Agent proxy is unavailable"

    status, body = http_request(
        login, method="POST", body=b"{}",
        headers={"Content-Type": "application/json", "Origin": origin},
    )
    assert status == 400, f"Same-origin login must reach input validation, got HTTP {status}"
    assert json.loads(body)["success"] is False
    status, _ = http_request(
        login, method="OPTIONS",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"},
    )
    assert status == 200, f"Same-origin preflight was rejected with HTTP {status}"
    status, body = http_request(
        login, method="POST", body=b"{}",
        headers={"Content-Type": "application/json", "Origin": "https://untrusted.invalid"},
    )
    assert status == 403 and body == b"Invalid CORS request", "Untrusted Origin was accepted"
    return {"result": "PASS", "entry_point": origin, "checks": [
        "web_entry", "agent_proxy", "same_origin_login_validation",
        "same_origin_preflight", "untrusted_origin_rejected",
    ]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    print(json.dumps(check_web(args.port), indent=2))
