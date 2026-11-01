# Engine development skills

Skills for working on the kb-distillery engine itself (tooling PRs, the React app, the API, the site). They live in the engine repo only and never reach a knowledge base; the skills a kb gets are in `src/kb_distillery/kits/<kit>/skills/`. How to write a skill: `docs/guides/write-a-skill.md`.

## Token budgets

| Skill | LLM tier | Budget (in) | Runs without asking |
|-------|----------|-------------|---------------------|
| `infra-pr` | none | 0 | only when the user asks to ship / open / merge a PR |
| `app-ui` | none | 0 | `port the <screen>`, `add a screen`, `frontend`, `app shell` |
| `backend-api` | none | 0 | `add an endpoint`, `new router`, `change the API`, `api-schema` |
| `share-kb` | none | 0 | `share the site`, `publish`, `deploy main`, `rollback the site`, `deploy status` (not `export-kb`) |
| `guided-tour` | light | ~2–4k | `guided tour`, `walkthrough`, `onboarding tour` |
| `send-to-backlog` | none | 0 | `send to backlog`, `backlog this`, `save this plan for later` |

## Skills

| Skill | Purpose |
|-------|---------|
| [guided-tour](guided-tour/SKILL.md) | Spotlight guided tours over the real app (`?tour=<name>`), fixed Back / Next dock |
| [send-to-backlog](send-to-backlog/SKILL.md) | Park an idea, bug or unstarted plan as a card in the local `.backlog/` (0 LLM); plan cards show drift |
| [infra-pr](infra-pr/SKILL.md) | Ship tooling/schema via `infra/*` branch + PR, never squash (0 LLM, on request) |
| [share-kb](share-kb/SKILL.md) | Deploy main to the private Cloudflare site, status, rollback; snapshots later (0 LLM) |
| [create-skill](create-skill/SKILL.md) | Author new skills; runs through `lint-skills` gate (0 LLM) |
| [backend-api](backend-api/SKILL.md) | Add/change a FastAPI router, model, service and tests under `src/kb_distillery/`; regenerate `schema.d.ts` (0 LLM) |
| [app-ui](app-ui/SKILL.md) | Conventions for building screens in `web/` (tokens, palette, data-model words, porting checklist; 0 LLM) |
