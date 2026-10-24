// Self-hosted Google sign-in for the private `kb` Worker (no Zero Trust, no npm deps).
//
//   /auth/login     → Google OAuth 2.0 authorization-code flow with PKCE; state + verifier
//                     travel in a short-lived signed cookie (`kb_oauth`, 10 min, Path=/auth/).
//   /auth/callback  → exchange the code, verify the ID token against Google's JWKS, check
//                     iss / aud / exp / email_verified and the ALLOWED_EMAILS allowlist, then set
//                     the session cookie `kb_session` = base64url(payload).sig (HMAC-SHA256 with
//                     SESSION_SECRET, 7-day expiry) and 302 → `/`. Not allowlisted → 403, no cookie.
//   /auth/logout    → clear the session cookie.
//   /admin/…        → admin.js (snapshot control panel API; JSON 401/403 instead of a redirect).
//   anything else   → valid session → env.ASSETS.fetch(request); otherwise 302 → /auth/login for
//                     HTML navigations, 401 for everything else.
//
// Bindings: env.ASSETS (static assets, run_worker_first), vars GOOGLE_CLIENT_ID, ALLOWED_EMAILS
// (comma-separated), CF_ACCOUNT_ID, secrets GOOGLE_CLIENT_SECRET, SESSION_SECRET, CF_API_TOKEN (panel).
//
// `handle(request, env, deps)` is exported for tests: deps = {fetch, now} default to the globals.

import { handleAdmin } from "./admin.js";

const GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN = "https://oauth2.googleapis.com/token";
const GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs";
const GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"];
const SESSION_COOKIE = "kb_session";
const OAUTH_COOKIE = "kb_oauth";
const SESSION_TTL = 7 * 24 * 3600; // seconds
const OAUTH_TTL = 600;
const JWKS_TTL_MS = 6 * 3600 * 1000;

let jwksCache = { keys: [], fetchedAt: 0 };

// ---------- base64url / crypto helpers ----------

const enc = new TextEncoder();

function b64url(bytes) {
  let s = "";
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(str) {
  const pad = "=".repeat((4 - (str.length % 4)) % 4);
  const bin = atob(str.replace(/-/g, "+").replace(/_/g, "/") + pad);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function randomToken(n = 32) {
  return b64url(crypto.getRandomValues(new Uint8Array(n)));
}

async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

// Signed token = base64url(JSON payload) + "." + base64url(HMAC-SHA256(payload part)).
async function sign(payload, secret) {
  const body = b64url(enc.encode(JSON.stringify(payload)));
  const mac = await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(body));
  return body + "." + b64url(mac);
}

// Returns the payload when the signature is valid and `exp` (seconds) is in the future, else null.
async function verify(token, secret, nowSec) {
  if (!token || !token.includes(".")) return null;
  const [body, mac] = token.split(".", 2);
  let ok = false;
  try {
    ok = await crypto.subtle.verify("HMAC", await hmacKey(secret), b64urlDecode(mac), enc.encode(body));
  } catch { return null; }
  if (!ok) return null;
  try {
    const payload = JSON.parse(new TextDecoder().decode(b64urlDecode(body)));
    return typeof payload.exp === "number" && payload.exp > nowSec ? payload : null;
  } catch { return null; }
}

// ---------- cookies ----------

function readCookie(request, name) {
  const header = request.headers.get("Cookie") || "";
  for (const part of header.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return null;
}

function setCookie(name, value, maxAge, path = "/") {
  return `${name}=${value}; Max-Age=${maxAge}; Path=${path}; HttpOnly; Secure; SameSite=Lax`;
}

function clearCookie(name, path = "/") {
  return `${name}=; Max-Age=0; Path=${path}; HttpOnly; Secure; SameSite=Lax`;
}

// ---------- Google ID token ----------

async function fetchJwks(fetchFn, nowMs, kid) {
  const fresh = nowMs - jwksCache.fetchedAt < JWKS_TTL_MS;
  if (!fresh || !jwksCache.keys.some((k) => k.kid === kid)) {
    const res = await fetchFn(GOOGLE_JWKS);
    if (!res.ok) throw new Error(`jwks fetch failed: ${res.status}`);
    jwksCache = { keys: (await res.json()).keys || [], fetchedAt: nowMs };
  }
  return jwksCache.keys.find((k) => k.kid === kid) || null;
}

// Verifies signature + claims; returns the claims or throws with a reason.
async function verifyIdToken(idToken, clientId, fetchFn, nowMs) {
  const parts = (idToken || "").split(".");
  if (parts.length !== 3) throw new Error("malformed id_token");
  const header = JSON.parse(new TextDecoder().decode(b64urlDecode(parts[0])));
  if (header.alg !== "RS256") throw new Error(`unexpected alg ${header.alg}`);
  const jwk = await fetchJwks(fetchFn, nowMs, header.kid);
  if (!jwk) throw new Error("unknown key id");
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64urlDecode(parts[2]), enc.encode(parts[0] + "." + parts[1]));
  if (!ok) throw new Error("bad id_token signature");
  const claims = JSON.parse(new TextDecoder().decode(b64urlDecode(parts[1])));
  if (!GOOGLE_ISSUERS.includes(claims.iss)) throw new Error("bad issuer");
  if (claims.aud !== clientId) throw new Error("bad audience");
  if (typeof claims.exp !== "number" || claims.exp * 1000 < nowMs) throw new Error("id_token expired");
  if (claims.email_verified !== true) throw new Error("email not verified");
  return claims;
}

function allowedEmails(env) {
  return (env.ALLOWED_EMAILS || "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
}

// ---------- responses ----------

function page(status, title, text) {
  const body = `<!doctype html><meta charset="utf-8"><title>${title}</title>` +
    `<body style="font:16px system-ui;margin:4rem auto;max-width:36rem;color:#222">` +
    `<h1 style="font-size:1.3rem">${title}</h1><p>${text}</p></body>`;
  return new Response(body, { status, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

function redirect(location, cookies = []) {
  const headers = new Headers({ Location: location });
  for (const c of cookies) headers.append("Set-Cookie", c);
  return new Response(null, { status: 302, headers });
}

function wantsHtml(request) {
  const accept = request.headers.get("Accept") || "";
  const path = new URL(request.url).pathname;
  return request.method === "GET" && (accept.includes("text/html") || path === "/" || path.endsWith("/") || path.endsWith(".html"));
}

// ---------- routes ----------

async function login(url, env, deps) {
  const state = randomToken(16);
  const verifier = randomToken(32);
  const challenge = b64url(await crypto.subtle.digest("SHA-256", enc.encode(verifier)));
  const nowSec = Math.floor(deps.now() / 1000);
  const cookie = await sign({ state, verifier, exp: nowSec + OAUTH_TTL }, env.SESSION_SECRET);
  const params = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID, redirect_uri: `${url.origin}/auth/callback`, response_type: "code",
    scope: "openid email", state, code_challenge: challenge, code_challenge_method: "S256",
  });
  return redirect(`${GOOGLE_AUTH}?${params}`, [setCookie(OAUTH_COOKIE, cookie, OAUTH_TTL, "/auth/")]);
}

async function callback(request, url, env, deps) {
  const nowMs = deps.now();
  const nowSec = Math.floor(nowMs / 1000);
  const pending = await verify(readCookie(request, OAUTH_COOKIE), env.SESSION_SECRET, nowSec);
  const state = url.searchParams.get("state");
  const code = url.searchParams.get("code");
  if (!pending || !state || !code || state !== pending.state) {
    return page(400, "Sign-in failed", "The sign-in state does not match. Start again from <a href=\"/auth/login\">/auth/login</a>.");
  }
  const tokenRes = await deps.fetch(GOOGLE_TOKEN, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code, client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: `${url.origin}/auth/callback`, grant_type: "authorization_code", code_verifier: pending.verifier,
    }),
  });
  if (!tokenRes.ok) return page(400, "Sign-in failed", `Google rejected the code exchange (${tokenRes.status}).`);
  const tokens = await tokenRes.json();
  let claims;
  try {
    claims = await verifyIdToken(tokens.id_token, env.GOOGLE_CLIENT_ID, deps.fetch, nowMs);
  } catch (e) {
    return page(400, "Sign-in failed", `The identity token could not be verified (${e.message}).`);
  }
  const email = String(claims.email || "").toLowerCase();
  if (!allowedEmails(env).includes(email)) {
    return page(403, "Not allowed", `${email} is not on the allowlist for this site.`);
  }
  const session = await sign({ email, iat: nowSec, exp: nowSec + SESSION_TTL }, env.SESSION_SECRET);
  return redirect("/", [setCookie(SESSION_COOKIE, session, SESSION_TTL), clearCookie(OAUTH_COOKIE, "/auth/")]);
}

export async function handle(request, env, deps = {}) {
  // fetch must stay bound to the global: a detached `deps.fetch(...)` throws "Illegal invocation" in Workers
  deps = { fetch: (...args) => globalThis.fetch(...args), now: Date.now, ...deps };
  const url = new URL(request.url);
  if (url.pathname === "/auth/login") return login(url, env, deps);
  if (url.pathname === "/auth/callback") {
    try {
      return await callback(request, url, env, deps);
    } catch (e) {
      console.error("auth callback failed", e && e.stack ? e.stack : e);
      return page(500, "Sign-in failed", "Something went wrong during sign-in. Start again from <a href=\"/auth/login\">/auth/login</a>.");
    }
  }
  if (url.pathname === "/auth/logout") return redirect("/auth/login", [clearCookie(SESSION_COOKIE)]);
  const session = await verify(readCookie(request, SESSION_COOKIE), env.SESSION_SECRET, Math.floor(deps.now() / 1000));
  if (url.pathname === "/admin" || url.pathname.startsWith("/admin/")) return handleAdmin(request, env, deps, session);
  if (session) return env.ASSETS.fetch(request);
  if (wantsHtml(request)) return redirect("/auth/login");
  return new Response("unauthorized", { status: 401, headers: { "Content-Type": "text/plain" } });
}

export default { fetch: (request, env) => handle(request, env) };
