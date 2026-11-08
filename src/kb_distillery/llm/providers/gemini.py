"""Gemini generateContent: POST https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent."""
from kb_distillery.config import userdir

from . import post_retrying, key_status, read_key

ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
ENV = "GEMINI_API_KEY"


def _key_file():
    return userdir.path("gemini_key")


def api_key():
    return read_key(ENV, _key_file())


def availability():
    return key_status("gemini", ENV, _key_file())


def complete(request, model_id, key):
    from kb_distillery import llm
    if request.images:
        raise llm.LLMError("images need the claude provider")
    res = llm.Result(id=request.id, backend="api", model=model_id)
    if not key:
        res.error = f"no API key: set {ENV} or write {_key_file()}"
        return res
    body = {"contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {"maxOutputTokens": request.max_tokens}}
    if request.system:
        body["systemInstruction"] = {"parts": [{"text": request.system}]}
    try:
        out = post_retrying(f"{ROOT}/{model_id}:generateContent", {"x-goog-api-key": key}, body)
    except llm.HTTPFail as e:
        res.error = str(e)[:300].replace(key, "***")
        return res
    u = out.get("usageMetadata") or {}
    cached = u.get("cachedContentTokenCount") or 0
    res.usage = {"input_tokens": max(0, (u.get("promptTokenCount") or 0) - cached),
                 "output_tokens": (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0),
                 "cache_read_input_tokens": cached}
    res.usd = llm.cost(model_id, res.usage)
    cand = (out.get("candidates") or [{}])[0]
    res.text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or [])
    res.stop_reason = cand.get("finishReason") or ""
    block = (out.get("promptFeedback") or {}).get("blockReason")
    if block:
        res.error = f"refused: {block}"
    elif res.stop_reason == "MAX_TOKENS":
        res.error = "cut at max_tokens (text kept)"
    elif res.stop_reason in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT") and not res.text:
        res.error = f"refused: {res.stop_reason.lower()}"
    elif not res.text:
        res.error = "empty result"
    return res
