# Phase 4 plan: Think as a standalone journal

Depends on: Phase 3. Unattended-safe: yes.

Think lives outside every kb. `kbd distill <note> --to a,b` sends a note into chosen kbs with provenance on both sides; the note records where it went.

## PRs

1. Think location + config outside the kbs (`kbs/think` today).
2. `kbd distill <note> --to a,b` fan-out with provenance both ways.
3. Migrate existing `think:` citations so they still resolve.

## Billing

**Billing.** Distill proposals go through `kb_distillery.llm`. Default backend: subscription (`claude -p`, your login). `api` and `batch` stay selectable per run (`--backend`, `$KB_LLM_BACKEND`); batch bills the Anthropic key, half price, asynchronous.

## Done when

Distilling into two kbs works; existing `think:` citations resolve.

## Approval gates

- None beyond this plan's approval.

## Standing rules

`KB_SHARE_AUTODEPLOY=0`; the thesis kb is never pushed to the old monorepo URL; every branch merged or deleted, no stale worktrees; tag `phase-4-done` with `ship tag`; every earlier test layer stays green.
