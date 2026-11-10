"""Opt-in proxy identity (KB_AUTH=proxy): signed JWT or trusted header, one allowed email, same-host Origin.

Every JWKS fetch is faked (`security._fetch_jwks`); no test touches the network."""
import base64
import hashlib
import hmac
import json
import time
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from kb_distillery.server import __main__ as server_main
from kb_distillery.server import security
from kb_distillery.server.app import create_app

EMAIL = "me@example.com"
HOST = "kb.example.com"
BASE = f"https://{HOST}"
JWKS_URL = "https://team.example.com/cdn-cgi/access/certs"
PROXY_IP = "192.0.2.10"            # RFC 5737 documentation ranges only
OUTSIDE_IP = "198.51.100.7"
AUTH_VARS = ("KB_AUTH", "KB_AUTH_EMAIL", "KB_AUTH_JWKS_URL", "KB_AUTH_JWT_KEY", "KB_AUTH_AUDIENCE", "KB_AUTH_HEADER",
             "KB_AUTH_TRUSTED_PROXY_CIDR")


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM,
                                                  serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return {"private": private, "other": other, "public_pem": public_pem}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in AUTH_VARS:
        monkeypatch.delenv(var, raising=False)
    security._jwks_cache.clear()
    security._jwks_tried.clear()
    yield
    security._jwks_cache.clear()
    security._jwks_tried.clear()


AUD = "aud-tag-1"


def token(keys, email=EMAIL, exp=3600, kid="k1", signer="private", **extra):
    claims = {"email": email, "aud": AUD, **extra}
    if exp is not None:
        claims["exp"] = int(time.time()) + exp
    return jwt.encode(claims, keys[signer], algorithm="RS256", headers={"kid": kid})


def jwks(keys, kid="k1"):
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(keys["private"].public_key()))
    return {"keys": [{**data, "kid": kid, "alg": "RS256", "use": "sig"}]}


def proxy_env(monkeypatch, **extra):
    monkeypatch.setenv("KB_AUTH", "proxy")
    monkeypatch.setenv("KB_AUTH_EMAIL", EMAIL)
    for name, value in extra.items():
        monkeypatch.setenv(name, value)


def jwt_env(monkeypatch, keys, **extra):
    proxy_env(monkeypatch, **{"KB_AUTH_JWKS_URL": JWKS_URL, "KB_AUTH_AUDIENCE": AUD, **extra})
    fetch = mock.Mock(return_value=jwks(keys))
    monkeypatch.setattr(security, "_fetch_jwks", fetch)
    return fetch


def header_env(monkeypatch):
    proxy_env(monkeypatch, KB_AUTH_HEADER="X-Auth-Request-Email", KB_AUTH_TRUSTED_PROXY_CIDR="192.0.2.0/24, 10.9.0.0/16")


def make_app():
    app = create_app()

    @app.get("/api/_ping")
    def ping():
        return {"ok": True}

    @app.post("/api/_ping")
    def poke(payload: dict):
        return {"ok": True}

    return app


def client(peer="testclient"):
    return TestClient(make_app(), base_url=BASE, client=(peer, 50000))


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def forged(header, claims, secret=b""):
    signing_input = f"{b64(json.dumps(header).encode())}.{b64(json.dumps(claims).encode())}"
    sig = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest() if secret else b""
    return f"{signing_input}.{b64(sig)}"


# ---- loopback mode stays the default ----

def test_auth_loopback_mode_is_default_and_unchanged():
    c = TestClient(make_app())
    assert c.get("/api/_ping").status_code == 200                                           # no identity needed
    assert c.get("/api/_ping", headers={"Host": HOST}).status_code == 400                   # host check as before
    assert c.post("/api/_ping", json={}, headers={"Origin": "http://127.0.0.1:8765"}).status_code == 200


def test_auth_off_loopback_bind_refused_without_kb_auth(monkeypatch):
    for host in ("0.0.0.0", "192.0.2.5", "example.com"):
        with pytest.raises(SystemExit):
            security.assert_loopback_bind(host)
    monkeypatch.setenv("KB_AUTH", "loopback")
    with pytest.raises(SystemExit):
        security.assert_loopback_bind("0.0.0.0")


def test_auth_off_loopback_bind_allowed_with_proxy_config(monkeypatch, keys):
    jwt_env(monkeypatch, keys)
    security.assert_loopback_bind("0.0.0.0")


@pytest.mark.parametrize("env", [
    {"KB_AUTH": "yes-please"},                                                       # unknown mode: no silent fallback
    {"KB_AUTH": "proxy", "KB_AUTH_JWKS_URL": JWKS_URL, "KB_AUTH_AUDIENCE": "a"},     # no email
    {"KB_AUTH": "proxy", "KB_AUTH_EMAIL": EMAIL, "KB_AUTH_JWKS_URL": JWKS_URL},     # JWKS without audience
    {"KB_AUTH": "proxy", "KB_AUTH_EMAIL": EMAIL},                                    # no identity source
    {"KB_AUTH": "proxy", "KB_AUTH_EMAIL": EMAIL, "KB_AUTH_HEADER": "X-Email"},       # header without CIDR
    {"KB_AUTH": "proxy", "KB_AUTH_EMAIL": EMAIL, "KB_AUTH_AUDIENCE": "a", "KB_AUTH_JWKS_URL": "http://team.example.com/certs"},
    {"KB_AUTH": "proxy", "KB_AUTH_EMAIL": EMAIL, "KB_AUTH_JWT_KEY": "-----BEGIN nonsense-----"},
])
def test_auth_bad_config_refuses_to_start(monkeypatch, env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit):
        security.assert_loopback_bind("127.0.0.1")
    with pytest.raises(SystemExit):
        create_app()


def test_auth_main_disables_uvicorn_proxy_headers(monkeypatch, keys):
    """uvicorn rewrites the ASGI client from X-Forwarded-For by default (peer 127.0.0.1): it must not."""
    jwt_env(monkeypatch, keys)
    import uvicorn

    from kb_distillery.graph import cache
    monkeypatch.setattr(cache, "start_refresher", lambda: None)
    run = mock.Mock()
    monkeypatch.setattr(uvicorn, "run", run)
    assert server_main.main(["--host", "0.0.0.0", "--no-open", "--no-build"]) == 0
    assert run.call_args.kwargs["proxy_headers"] is False
    assert run.call_args.kwargs["host"] == "0.0.0.0"


# ---- signed JWT ----

def test_auth_valid_token(monkeypatch, keys):
    fetch = jwt_env(monkeypatch, keys)
    c = client()
    assert c.get("/api/_ping").status_code == 401                                          # nothing carried
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys)}).json() == {"ok": True}
    assert c.get("/api/_ping", headers={"Authorization": f"Bearer {token(keys)}"}).status_code == 200
    assert c.get("/docs", headers={}).status_code == 401                                    # docs are covered too
    assert c.get("/no-such-route").status_code == 401                                       # and 404s
    assert fetch.call_count == 1                                                            # the JWKS is cached


def test_auth_static_key(monkeypatch, keys):
    proxy_env(monkeypatch, KB_AUTH_JWT_KEY=keys["public_pem"])
    c = client()
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys)}).status_code == 200
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, signer="other")}).status_code == 401


def test_auth_wrong_email(monkeypatch, keys):
    jwt_env(monkeypatch, keys)
    c = client()
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, email="octocat@example.com")}).status_code == 401
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, email=None)}).status_code == 401


def test_auth_email_case_folding(monkeypatch, keys):
    jwt_env(monkeypatch, keys, KB_AUTH_EMAIL="Me@Example.COM ")
    c = client()
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, email="ME@example.com")}).status_code == 200


def test_auth_expired_or_missing_exp(monkeypatch, keys):
    jwt_env(monkeypatch, keys)
    c = client()
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, exp=-3600)}).status_code == 401
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, exp=None)}).status_code == 401


def test_auth_alg_none_and_algorithm_confusion(monkeypatch, keys):
    proxy_env(monkeypatch, KB_AUTH_JWT_KEY=keys["public_pem"])
    claims = {"email": EMAIL, "exp": int(time.time()) + 3600}
    c = client()
    for alg in ("none", "None", "NONE"):
        none_token = forged({"alg": alg, "typ": "JWT"}, claims)
        assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": none_token}).status_code == 401
    confused = forged({"alg": "HS256", "typ": "JWT"}, claims, secret=keys["public_pem"].encode())
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": confused}).status_code == 401


def test_auth_jwks_symmetric_key_refused(monkeypatch, keys):
    """A JWKS that (wrongly or maliciously) carries an `oct` key still cannot verify an HS256 token."""
    proxy_env(monkeypatch, KB_AUTH_JWKS_URL=JWKS_URL, KB_AUTH_AUDIENCE=AUD)
    secret = b"s" * 32
    monkeypatch.setattr(security, "_fetch_jwks", lambda url: {"keys": [
        {"kty": "oct", "kid": "k1", "alg": "HS256", "k": b64(secret)}]})
    hs = jwt.encode({"email": EMAIL, "aud": AUD, "exp": int(time.time()) + 3600}, secret, algorithm="HS256", headers={"kid": "k1"})
    assert client().get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": hs}).status_code == 401


def test_auth_audience(monkeypatch, keys):
    jwt_env(monkeypatch, keys)
    c = client()
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, aud=[AUD])}).status_code == 200
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, aud="aud-tag-2")}).status_code == 401
    no_aud = jwt.encode({"email": EMAIL, "exp": int(time.time()) + 60}, keys["private"], algorithm="RS256",
                        headers={"kid": "k1"})
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": no_aud}).status_code == 401


def test_auth_unknown_kid_and_failed_fetch(monkeypatch, keys):
    fetch = jwt_env(monkeypatch, keys)
    c = client()
    assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys, kid="rotated")}).status_code == 401
    assert fetch.call_count == 1                        # an unknown kid right after a fetch does not refetch
    security._jwks_cache.clear()
    security._jwks_tried.clear()
    fetch.side_effect = OSError("network down")
    for _ in range(5):
        assert c.get("/api/_ping", headers={"Cf-Access-Jwt-Assertion": token(keys)}).status_code == 401
    assert fetch.call_count == 2                        # a dead endpoint is tried once per throttle window


def test_auth_bad_token_is_not_retried_as_header(monkeypatch, keys):
    jwt_env(monkeypatch, keys, KB_AUTH_HEADER="X-Auth-Request-Email", KB_AUTH_TRUSTED_PROXY_CIDR="192.0.2.0/24")
    c = client(PROXY_IP)
    headers = {"Cf-Access-Jwt-Assertion": token(keys, signer="other"), "X-Auth-Request-Email": EMAIL}
    assert c.get("/api/_ping", headers=headers).status_code == 401


# ---- trusted header ----

def test_auth_header_from_trusted_proxy(monkeypatch):
    header_env(monkeypatch)
    assert client(PROXY_IP).get("/api/_ping", headers={"X-Auth-Request-Email": EMAIL}).status_code == 200
    assert client("10.9.4.2").get("/api/_ping", headers={"X-Auth-Request-Email": "ME@EXAMPLE.COM"}).status_code == 200
    assert client(PROXY_IP).get("/api/_ping").status_code == 401                          # proxy sent no identity
    assert client(PROXY_IP).get("/api/_ping", headers={"X-Auth-Request-Email": "octocat@example.com"}).status_code == 401


def test_auth_header_from_untrusted_source(monkeypatch):
    header_env(monkeypatch)
    for peer in (OUTSIDE_IP, "testclient", "127.0.0.1"):
        assert client(peer).get("/api/_ping", headers={"X-Auth-Request-Email": EMAIL}).status_code == 401


def test_auth_x_forwarded_for_not_trusted(monkeypatch):
    header_env(monkeypatch)
    spoof = {"X-Auth-Request-Email": EMAIL, "X-Forwarded-For": PROXY_IP, "X-Real-IP": PROXY_IP, "Forwarded": f"for={PROXY_IP}"}
    assert client(OUTSIDE_IP).get("/api/_ping", headers=spoof).status_code == 401


def test_auth_repeated_identity_header_refused(monkeypatch):
    header_env(monkeypatch)
    raw = [(b"host", HOST.encode()), (b"x-auth-request-email", EMAIL.encode()),
           (b"x-auth-request-email", b"octocat@example.com")]
    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        raise AssertionError("must not reach the app")

    scope = {"type": "http", "method": "GET", "path": "/", "headers": raw, "client": (PROXY_IP, 1), "query_string": b""}
    import asyncio
    asyncio.run(security.ProxyAuthMiddleware(app)(scope, receive, send))
    assert sent[0]["status"] == 401


# ---- same-host Origin on mutations ----

def test_auth_origin_same_host_in_proxy_mode(monkeypatch):
    header_env(monkeypatch)
    c = client(PROXY_IP)
    ident = {"X-Auth-Request-Email": EMAIL}
    assert c.post("/api/_ping", json={}, headers={**ident, "Origin": BASE}).status_code == 200
    assert c.post("/api/_ping", json={}, headers=ident).status_code == 403                             # no Origin
    assert c.post("/api/_ping", json={}, headers={**ident, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/_ping", json={}, headers={**ident, "Origin": "http://127.0.0.1:8765"}).status_code == 403
    assert c.post("/api/_ping", json={}, headers={**ident, "Origin": f"{BASE}:8443"}).status_code == 403
