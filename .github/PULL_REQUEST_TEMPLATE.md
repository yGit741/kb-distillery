## What changed

<!-- One concern per pull request. Say what and why. -->

## How it was checked

<!-- Tests added or run, commands, screenshots for web changes. -->

## Checklist

- [ ] Branch made with `pixi run ship -- start`; no direct commit to `main`
- [ ] Tests added or updated next to the code
- [ ] `pixi run test`, `lint`, `lint-skills`, `lint-imports` pass; `web-check` if `web/` changed
- [ ] No knowledge base content, local paths, names or keys in tracked files
- [ ] LLM calls go through `kb_distillery.llm`
- [ ] `CHANGELOG.md` updated under Unreleased
- [ ] Docs updated if behavior or commands changed
