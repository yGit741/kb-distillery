// node --test share — Google JWKS + token endpoint mocked, WebCrypto only.
import { test } from "node:test";
import assert from "node:assert/strict";
import { handle } from "./auth.js";

const ORIGIN = "https://kb.example.workers.dev";
const SECRET = "test-session-secret";
const CLIENT_ID = "client-id.apps.googleusercontent.com";
const NOW = 1_800_000_000_000; // ms

const enc = new TextEncoder();
const b64url = (bytes) => Buffer.from(bytes).toString("base64url");

const { publicKey, privateKey } = await crypto.subtle.generateKey(
  { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
  true, ["sign", "verify"]);
const jwk = { ...(await crypto.subtle.exportKey("jwk", publicKey)), kid: "k1", use: "sig", alg: "RS256" };

async function idToken(claims, { kid = "k1" } = {}) {
  const head = b64url(enc.encode(JSON.stringify({ alg: "RS256", kid })));
  const body = b64url(enc.encode(JSON.stringify(claims)));
  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", privateKey, enc.encode(head + "." + body));
  return `${head}.${body}.${b64url(sig)}`;
}

async function hmac(body) {
  const key = await crypto.subtle.importKey("raw", enc.encode(SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(body)));
}
async function signed(payload) {
  const body = b64url(enc.encode(JSON.stringify(payload)));
  return body + "." + (await hmac(body));
}

function env(overrides = {}) {
  return {
    ASSETS: { fetch: async (req) => new Response("asset:" + new URL(req.url).pathname, { status: 200 }) },
    GOOGLE_CLIENT_ID: CLIENT_ID, GOOGLE_CLIENT_SECRET: "shh", SESSION_SECRET: SECRET,
    ALLOWED_EMAILS: "me@example.com, Other@Example.org", ...overrides,
  };
}

function mockFetch(email, { tokenStatus = 200 } = {}) {
  const calls = [];
  return {
    calls,
    fetch: async (url, init) => {
      calls.push(String(url));
      if (String(url).includes("/oauth2/v3/certs")) return Response.json({ keys: [jwk] });
      if (String(url).includes("oauth2.googleapis.com/token")) {
        const form = new URLSearchParams(init.body);
        assert.equal(form.get("grant_type"), "authorization_code");
        assert.ok(form.get("code_verifier"));
        if (tokenStatus !== 200) return new Response("nope", { status: tokenStatus });
        const token = await idToken({ iss: "https://accounts.google.com", aud: CLIENT_ID, exp: NOW / 1000 + 60,
                                       email, email_verified: true });
        return Response.json({ id_token: token, access_token: "x" });
      }
      throw new Error("unexpected fetch " + url);
    },
  };
}

const deps = (f) => ({ fetch: f, now: () => NOW });
const get = (path, headers = {}) => new Request(ORIGIN + path, { headers: { Accept: "text/html", ...headers } });
const cookies = (res) => res.headers.getSetCookie();

test("no cookie → 302 to /auth/login for html, 401 otherwise", async () => {
  const res = await handle(get("/"), env(), deps());
  assert.equal(res.status, 302);
  assert.equal(res.headers.get("Location"), "/auth/login");
  const api = await handle(new Request(ORIGIN + "/manifest.json", { headers: { Accept: "application/json" } }), env(), deps());
  assert.equal(api.status, 401);
});

test("valid cookie → asset served", async () => {
  const cookie = await signed({ email: "me@example.com", iat: NOW / 1000, exp: NOW / 1000 + 100 });
  const res = await handle(get("/index.html", { Cookie: `kb_session=${cookie}` }), env(), deps());
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "asset:/index.html");
});

test("tampered or expired cookie → 302", async () => {
  const good = await signed({ email: "me@example.com", iat: NOW / 1000, exp: NOW / 1000 + 100 });
  const [body, sig] = good.split(".");
  const forgedBody = b64url(enc.encode(JSON.stringify({ email: "evil@example.com", exp: NOW / 1000 + 100 })));
  for (const bad of [`${forgedBody}.${sig}`, `${body}.AAAA`, "garbage", ""]) {
    const res = await handle(get("/", { Cookie: `kb_session=${bad}` }), env(), deps());
    assert.equal(res.status, 302, `cookie ${bad}`);
  }
  const expired = await signed({ email: "me@example.com", exp: NOW / 1000 - 1 });
  const res = await handle(get("/", { Cookie: `kb_session=${expired}` }), env(), deps());
  assert.equal(res.status, 302);
});

test("/auth/login → 302 to accounts.google.com with PKCE and a signed state cookie", async () => {
  const res = await handle(get("/auth/login"), env(), deps());
  assert.equal(res.status, 302);
  const loc = new URL(res.headers.get("Location"));
  assert.equal(loc.origin + loc.pathname, "https://accounts.google.com/o/oauth2/v2/auth");
  assert.equal(loc.searchParams.get("client_id"), CLIENT_ID);
  assert.equal(loc.searchParams.get("redirect_uri"), ORIGIN + "/auth/callback");
  assert.equal(loc.searchParams.get("code_challenge_method"), "S256");
  const c = cookies(res).find((x) => x.startsWith("kb_oauth="));
  assert.match(c, /HttpOnly; Secure; SameSite=Lax/);
});

// Runs the login step for real, then replays the callback with the resulting cookie.
async function loginThenCallback(e, f, { state } = {}) {
  const login = await handle(get("/auth/login"), e, deps(f));
  const loc = new URL(login.headers.get("Location"));
  const cookie = cookies(login).find((x) => x.startsWith("kb_oauth=")).split(";")[0];
  const s = state ?? loc.searchParams.get("state");
  return handle(get(`/auth/callback?code=abc&state=${s}`, { Cookie: cookie }), e, deps(f));
}

test("callback: allowlisted email → session cookie + 302 /", async () => {
  const m = mockFetch("Me@Example.com");
  const res = await loginThenCallback(env(), m.fetch);
  assert.equal(res.status, 302);
  assert.equal(res.headers.get("Location"), "/");
  const session = cookies(res).find((x) => x.startsWith("kb_session="));
  assert.match(session, /HttpOnly; Secure; SameSite=Lax/);
  assert.match(session, /Max-Age=604800/);
  assert.ok(m.calls.some((u) => u.includes("/oauth2/v3/certs")), "JWKS fetched");
  // the cookie it set is accepted afterwards
  const value = session.split(";")[0].slice("kb_session=".length);
  const ok = await handle(get("/", { Cookie: `kb_session=${value}` }), env(), deps());
  assert.equal(ok.status, 200);
});

test("callback: non-allowlisted email → 403 and no cookie", async () => {
  const m = mockFetch("stranger@example.com");
  const res = await loginThenCallback(env(), m.fetch);
  assert.equal(res.status, 403);
  assert.equal(cookies(res).filter((x) => x.startsWith("kb_session=")).length, 0);
});

test("callback: state mismatch or missing PKCE cookie → 400", async () => {
  const m = mockFetch("me@example.com");
  const mismatch = await loginThenCallback(env(), m.fetch, { state: "wrong" });
  assert.equal(mismatch.status, 400);
  const noCookie = await handle(get("/auth/callback?code=abc&state=x"), env(), deps(m.fetch));
  assert.equal(noCookie.status, 400);
  assert.equal(m.calls.length, 0, "no token exchange without a valid state");
});

test("callback: bad audience / unverified email / bad signature → 400, no cookie", async () => {
  for (const claims of [
    { iss: "https://accounts.google.com", aud: "someone-else", exp: NOW / 1000 + 60, email: "me@example.com", email_verified: true },
    { iss: "https://accounts.google.com", aud: CLIENT_ID, exp: NOW / 1000 + 60, email: "me@example.com", email_verified: false },
    { iss: "https://accounts.google.com", aud: CLIENT_ID, exp: NOW / 1000 - 60, email: "me@example.com", email_verified: true },
  ]) {
    const f = async (url) => url.includes("certs") ? Response.json({ keys: [jwk] })
      : Response.json({ id_token: await idToken(claims) });
    const res = await loginThenCallback(env(), f);
    assert.equal(res.status, 400);
    assert.equal(cookies(res).length, 0);
  }
  const forged = async (url) => url.includes("certs") ? Response.json({ keys: [jwk] })
    : Response.json({ id_token: (await idToken({ iss: "https://accounts.google.com", aud: CLIENT_ID, exp: NOW / 1000 + 60,
                                                   email: "me@example.com", email_verified: true })).slice(0, -4) + "AAAA" });
  assert.equal((await loginThenCallback(env(), forged)).status, 400);
});

test("/auth/logout clears the cookie", async () => {
  const res = await handle(get("/auth/logout"), env(), deps());
  assert.equal(res.status, 302);
  assert.match(cookies(res)[0], /kb_session=; Max-Age=0/);
});

test("default fetch stays bound to the global (Workers throws 'Illegal invocation' otherwise)", async () => {
  const m = mockFetch("me@example.com");
  const real = globalThis.fetch;
  // a fetch that, like the Workers runtime, refuses to run with a receiver other than the global
  globalThis.fetch = function (url, init) {
    if (this !== undefined && this !== globalThis) throw new TypeError("Illegal invocation");
    return m.fetch(url, init);
  };
  try {
    const noFetch = { now: () => NOW };
    const login = await handle(get("/auth/login"), env(), noFetch);
    const s = new URL(login.headers.get("Location")).searchParams.get("state");
    const cookie = cookies(login).find((x) => x.startsWith("kb_oauth=")).split(";")[0];
    const res = await handle(get(`/auth/callback?code=abc&state=${s}`, { Cookie: cookie }), env(), noFetch);
    assert.equal(res.status, 302);
    assert.equal(res.headers.get("Location"), "/");
  } finally {
    globalThis.fetch = real;
  }
});

test("callback: an unexpected exception becomes a readable 500 page, not a Worker crash", async () => {
  const boom = async () => { throw new Error("network down"); };
  const res = await loginThenCallback(env(), boom);
  assert.equal(res.status, 500);
  assert.match(await res.text(), /Sign-in failed/);
  assert.ok(!cookies(res).some((x) => x.startsWith("kb_session=")));
});
