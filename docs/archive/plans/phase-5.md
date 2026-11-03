# Phase 5 plan: `kbd init` / `kbd doctor` + LLM opt-in

Depends on: Phase 4. Unattended-safe: yes.

A fresh clone becomes a working dashboard in minutes without any LLM, and AI features switch on only when you add a login or key.

## PRs

1. `kbd init`: storage, optional LLM, first kb from a template.
2. `kbd doctor`: checks environment and kb, suggests fixes.
3. AI features greyed out until a subscription login or a keychain API key exists; all three backends selectable.

## Billing

**Billing.** No LLM call happens without opt-in. Default backend subscription; `api` / `batch` selectable per run. The key is read from the keychain by the user's tool only.

## Done when

Fresh clone on a clean user: `pixi install && kbd init` gives a working dashboard, no LLM.

## Approval gates

- None beyond this plan's approval.

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-5-done` with `ship tag`; every earlier test layer stays green.
