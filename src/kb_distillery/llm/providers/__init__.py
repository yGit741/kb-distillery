"""Provider adapters: one blocking chat completion each, text in, text out, stdlib HTTP only.

An adapter module exposes `complete(request, model_id, key) -> Result` and `availability() -> (ok, reason)`, plus
`api_key()` / `key_source()` for its key (env var first, then `~/.config/kb-distillery/<provider>_key`). The Claude
adapter also serves the Message Batches API through `kb_distillery.llm`; the others are `api`-backend only.
"""
import importlib
import json
import os
import urllib.error
import urllib.request

PROVIDERS = ("claude", "openai", "gemini")
_MODULES = {"claude": "anthropic", "openai": "openai", "gemini": "gemini"}


def get(name):
    """The adapter module for a provider name; ValueError for an unknown one."""
    if name not in _MODULES:
        raise ValueError(f"unknown provider {name!r}; pick one of {', '.join(PROVIDERS)}")
    return importlib.import_module(f"{__name__}.{_MODULES[name]}")


def read_key(env_var, key_file):
    """The key from `env_var`, else the first line of `key_file`; None when neither holds one. Never logged."""
    k = os.environ.get(env_var, "").strip()
    if k:
        return k
    try:
        with open(key_file, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def key_status(provider, env_var, key_file):
    """(ok, reason) for availability(): a key is findable, without calling the API."""
    if os.environ.get(env_var, "").strip():
        return True, f"API key found (env {env_var})"
    if read_key(env_var, key_file):
        return True, f"API key found ({key_file})"
    return False, f"no {provider} API key: set {env_var} or put the key in {key_file}"


def post_json(url, headers, body, timeout=600):
    """POST a JSON body → the decoded JSON reply. Raises kb_distillery.llm.HTTPFail (status 0: unreachable)."""
    from kb_distillery import llm
    from kb_distillery.config.net import ssl_context
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("error", {})
            detail = err.get("message", "") if isinstance(err, dict) else str(err)
        except Exception:
            detail = ""
        raise llm.HTTPFail(e.code, detail or str(e.reason)) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise llm.HTTPFail(0, f"cannot reach the API: {getattr(e, 'reason', e)}") from None
    except ValueError:
        raise llm.HTTPFail(0, "the API answered with something that is not JSON") from None


def post_retrying(url, headers, body, retries=3):
    """`post_json` (looked up on this module so tests can fake it) with the same transient-error retries as Claude."""
    from kb_distillery import llm
    for attempt in range(retries + 1):
        try:
            return post_json(url, headers, body)
        except llm.HTTPFail as e:
            if attempt == retries or (e.status and e.status not in llm.RETRYABLE):
                raise
            llm._sleep(2 ** attempt * 2)
