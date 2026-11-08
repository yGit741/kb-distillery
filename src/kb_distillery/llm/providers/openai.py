"""OpenAI chat completions: POST https://api.openai.com/v1/chat/completions."""
from kb_distillery.config import userdir

from . import post_retrying, key_status, read_key

URL = "https://api.openai.com/v1/chat/completions"
ENV = "OPENAI_API_KEY"


def _key_file():
    return userdir.path("openai_key")


def api_key():
    return read_key(ENV, _key_file())


def availability():
    return key_status("openai", ENV, _key_file())


def complete(request, model_id, key):
    from kb_distillery import llm
    if request.images:
        raise llm.LLMError("images need the claude provider")
    res = llm.Result(id=request.id, backend="api", model=model_id)
    if not key:
        res.error = f"no API key: set {ENV} or write {_key_file()}"
        return res
    messages = ([{"role": "system", "content": request.system}] if request.system else [])
    messages.append({"role": "user", "content": request.prompt})
    body = {"model": model_id, "messages": messages, "max_completion_tokens": request.max_tokens}
    try:
        out = post_retrying(URL, {"authorization": f"Bearer {key}"}, body)
    except llm.HTTPFail as e:
        res.error = str(e)[:300]
        return res
    u = out.get("usage") or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    res.usage = {"input_tokens": max(0, (u.get("prompt_tokens") or 0) - cached),
                 "output_tokens": u.get("completion_tokens") or 0, "cache_read_input_tokens": cached}
    res.usd = llm.cost(model_id, res.usage)
    choice = (out.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    res.text = msg.get("content") or ""
    res.stop_reason = choice.get("finish_reason") or ""
    if msg.get("refusal"):
        res.error = "refused: " + str(msg["refusal"])[:200]
    elif res.stop_reason == "length":
        res.error = "cut at max_tokens (text kept)"
    elif not res.text:
        res.error = "empty result"
    return res
