"""Dedicated localhost Keycloak test identities and real Authorization Code + PKCE."""
from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import secrets
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
ISSUER = "http://127.0.0.1:18082/realms/enterprise-insight"
CLIENT = "enterprise-insight-web"
REDIRECT = "http://127.0.0.1:18080/"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, *, method="GET", payload=None, form=None, token=None, opener=None, origin=None):
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise ValueError("Test credentials may only be sent to localhost")
    headers = {}
    if origin:
        headers["Origin"] = origin
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        body = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(url, data=body, headers=headers, method=method)
    try:
        response = (opener or build_opener(NoRedirect())).open(req, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        data = response.read()
        return response.status, response.headers, data


def json_request(url, **kwargs):
    status, headers, raw = request(url, **kwargs)
    if status >= 400:
        raise RuntimeError(f"Local identity request failed: {status} {urlparse(url).path}")
    return status, headers, json.loads(raw) if raw else None


def create_user(username, password):
    env = dict(line.split("=", 1) for line in (ROOT / "runtime/local-prod/.env").read_text().splitlines()
               if line and not line.startswith("#") and "=" in line)
    _, _, admin = json_request("http://127.0.0.1:18082/realms/master/protocol/openid-connect/token", method="POST", form={
        "grant_type": "password", "client_id": "admin-cli", "username": "admin",
        "password": env["LOCAL_PROD_KEYCLOAK_ADMIN_PASSWORD"],
    })
    json_request("http://127.0.0.1:18082/admin/realms/enterprise-insight/users", method="POST",
                 token=admin["access_token"], payload={
                     "username": username, "enabled": True, "firstName": "Local", "lastName": "Validation",
                     "email": username + "@example.invalid", "emailVerified": True,
                     "credentials": [{"type": "password", "value": password, "temporary": False}],
                 })


class LoginForm(HTMLParser):
    action = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action = attrs.get("action")


def login(username, password):
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    _, _, html = request(ISSUER + "/protocol/openid-connect/auth?" + urlencode({
        "client_id": CLIENT, "redirect_uri": REDIRECT, "response_type": "code", "scope": "openid",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    }), opener=opener)
    parser = LoginForm()
    parser.feed(html.decode())
    if not parser.action:
        raise RuntimeError("Keycloak login form unavailable")
    status, headers, _ = request(parser.action, method="POST", form={"username": username, "password": password}, opener=opener)
    query = parse_qs(urlparse(headers.get("Location", "")).query)
    if status != 302 or query.get("state") != [state] or "code" not in query:
        raise RuntimeError("Keycloak PKCE login callback failed")
    _, grant_headers, grant = json_request(ISSUER + "/protocol/openid-connect/token", method="POST", origin=REDIRECT.rstrip("/"), form={
        "grant_type": "authorization_code", "client_id": CLIENT, "redirect_uri": REDIRECT,
        "code": query["code"][0], "code_verifier": verifier,
    })
    if grant_headers.get("Access-Control-Allow-Origin") != REDIRECT.rstrip("/"):
        raise RuntimeError("Keycloak token response does not allow the real browser origin")
    _, _, response = json_request("http://127.0.0.1:18081/api/auth/oidc/exchange", method="POST", token=grant["access_token"])
    return response["data"], grant


def register_workspace(username, password):
    create_user(username, password)
    session, _ = login(username, password)
    return 200, {"success": True, "data": session}


if __name__ == "__main__":
    username = "load-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    create_user(username, password)
    session, _ = login(username, password)
    target = ROOT / "runtime/local-prod/load.env"
    target.write_text(f"E2E_OIDC_USERNAME={username}\nE2E_OIDC_PASSWORD={password}\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "flow": "Authorization Code + S256 PKCE", "tenant_id": session["tenantId"], "credentials_file": str(target)}))
