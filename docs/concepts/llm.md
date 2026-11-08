# Language models: providers, tiers and billing

Every model call in the engine goes through one module, `kb_distillery.llm` ([ADR 0001](../adr/0001-single-llm-gateway.md)). It makes three independent choices: the provider (which vendor), the backend (how the call is billed and run) and the tier (how strong a model).

## Providers

| Provider | Backends | Key |
|---|---|---|
| `claude` | subscription, api, batch | `ANTHROPIC_API_KEY` or `~/.config/kb-distillery/anthropic_key` (the subscription needs `claude login` instead) |
| `openai` | api | `OPENAI_API_KEY` or `~/.config/kb-distillery/openai_key` |
| `gemini` | api | `GEMINI_API_KEY` or `~/.config/kb-distillery/gemini_key` |

Subscription and batch exist for Claude only. Asking for them with another provider is an error. OpenAI and Gemini take text, not images.

Choose a provider, first match wins:

1. the argument (`distill llm ask --provider openai`)
2. `$KB_LLM_PROVIDER`
3. `[llm] provider = "gemini"` in the knowledge base's `kb.toml`
4. automatic: Claude when its subscription is logged in or it has an API key, otherwise the first of OpenAI and Gemini that has a key, otherwise Claude (so the error says what to set up). If you ask for the subscription or batch backend, the automatic choice stays on Claude

`distill doctor` lists each provider, whether it is usable, and which provider and backend a call gets by default.

Today only `distill llm ask` and `distill doctor` follow the provider setting. Every other feature (digests, relation proposals, chat, summaries) still runs on Claude.

### Features that need Claude

The chat Agent backend runs only on Claude. When Claude cannot run (no `claude login` and no Anthropic key), the app marks the control "Needs Claude" and the chat endpoint answers HTTP 409 with the message "Needs Claude: sign in with `claude login` or add an Anthropic API key." The login is re-checked before the refusal, so signing in takes effect without a restart. Other agent features are not marked or gated yet.

## Backends

| Backend | What it does | Cost |
|---|---|---|
| `subscription` | runs `claude -p` with your logged-in account | covered by the subscription |
| `api` | calls the vendor's API with your key | standard price per token |
| `batch` | Claude's Message Batches API | half the API price; results in hours, up to 24 |

Choose a backend, first match wins: the `--backend` option, `$KB_LLM_BACKEND`, then for Claude the subscription when logged in, the API when only a key exists, and the subscription otherwise. Other providers always use `api`. A feature may set its own default if its page says so; relation proposals default to `batch`.

## Tiers

A feature asks for a tier, not a model. The tier never changes the provider or the backend.

| Tier | Meant for | Claude | OpenAI | Gemini |
|---|---|---|---|---|
| `light` | quick answers, abstract skims, line routing | haiku | gpt-4.1-nano | gemini-2.5-flash-lite |
| `standard` | digests, claim fills, video reads | sonnet | gpt-4.1-mini | gemini-2.5-flash |
| `strong` | hard reasoning | opus | gpt-4.1 | gemini-2.5-pro |

Easy digests and line routing use `light`. Full digests, source extraction and the digest jobs use `standard`. Relation proposals, translations and chat still use fixed Claude aliases (sonnet or haiku), so `llm.toml` does not move them. Nothing asks for `strong` by default; pass `--model strong` where a command takes `--model`.

To change what a tier means, copy `src/kb_distillery/kits/base/defaults/llm.example.toml` to `~/.config/kb-distillery/llm.toml` and edit the `[claude]`, `[openai]` and `[gemini]` tables. A value is an alias or a model id. A model the engine has no price for needs a row:

```toml
[prices."gpt-5"]
in = 1.25
out = 10.00
```

Prices are USD per million tokens. The OpenAI and Gemini defaults and prices have not been verified against the vendors' price pages: check them before you rely on a cost estimate for those providers.

## Billing

The chat screen keeps a spend ledger. Digest jobs and relation proposals show an estimate or a total instead, and subscription calls count as zero.

Digest jobs show a preview before they start: the cost and the time for each backend. The default is one choice:

- if you pass a backend, or set `$KB_LLM_BACKEND`, that wins
- a job above `[llm] bulk_threshold` sources (default 5) uses the standard API
- a smaller job uses the subscription when Claude is logged in, otherwise the API
- batch is never the default. You select it per job; the preview shows its wait, a few hours and up to 24, at half the price

Set the threshold in `kb.toml`:

```toml
[llm]
bulk_threshold = 5
```

See also [Digest tiers](digest-tiers.md) (the digest levels, not model tiers), and the CLI: `distill llm ask|submit|status|collect`.
