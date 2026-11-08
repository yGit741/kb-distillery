"""Claude via POST /v1/messages (the `api` backend). Request shape, retries and the key lookup live in
`kb_distillery.llm` because the Batch API shares them."""
import json


def api_key():
    from kb_distillery import llm
    return llm.api_key()


def availability():
    from kb_distillery import llm
    src = llm.api_key_source()
    if src:
        return True, f"API key found ({src})"
    return False, f"no anthropic API key: set ANTHROPIC_API_KEY or put the key in {llm.KEY_FILE}"


def complete(request, model_id, key):
    from kb_distillery import llm
    res = llm.Result(id=request.id, backend="api", model=model_id)
    try:
        msg = json.loads(llm._call("POST", "/messages", llm.params(request), key=key))
    except (llm.HTTPFail, ValueError) as e:
        res.error = str(e)[:300]
        return res
    return llm._from_message(res, msg)
