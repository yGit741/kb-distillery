# 0001. One gateway for every model call

Status: accepted.

## Context

The engine calls a model in several places: digests, summaries, relation proposals, think notes, chat, extraction from images and video. Each caller could build its own request. People who use the engine pay for models in different ways. Some have a subscription login. Some have an API key. Some want the Batch API for half the price and can wait.

If every feature made its own call, billing would be decided in each feature, and a change of billing would mean a rewrite.

## Decision

Every model call goes through `kb_distillery.llm`. The module has three backends behind one setting:

- `subscription`: runs `claude -p` from an empty folder with no tools and with the API key variables removed, so it uses the logged-in account.
- `api`: calls the Messages API with a key from `ANTHROPIC_API_KEY` or the user config folder.
- `batch`: uses the Message Batches API. It costs half as much. Results come within hours. `submit` and `collect` split the work across processes.

The backend is chosen by the `--backend` option, then by `KB_LLM_BACKEND`, then by the default, `subscription`. A feature may set its own default if it is documented. Relation proposals default to `batch`.

A test fails when code outside the gateway starts `claude -p` or sends an HTTP request to the model API.

A change that adds or alters a feature that calls a model has a short Billing section in its plan. The section says which backend is the default and keeps all three selectable.

The module uses the standard library only, so it can run in hooks and small environments.

## Consequences

- Billing is a flag, not a rewrite.
- All three backends stay available in every feature.
- A new feature that needs a model gets cost reporting and batching for free.
- The gateway is a single place to add retries, price tables and model names.
- Contributors cannot add a direct SDK call. They add to the gateway.

## Where

`src/kb_distillery/llm/`, `tests/llm/test_llm.py`. CLI: `distill llm ask|submit|status|collect`.
