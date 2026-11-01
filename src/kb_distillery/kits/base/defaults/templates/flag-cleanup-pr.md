# chore(flags): remove <name>

PR template for retiring a feature flag (lint errors once a flag in `meta/flags.toml` is past `expires`).
Run it as an `infra-pr`: `pixi run ship -- start flag-cleanup-<name> --worktree`, title `chore(flags): remove <name>`.

## Decide the winner

- [ ] Winning state: **on** (the feature stays) or **off** (the feature goes) — owner: <owner>

## Steps

1. [ ] Delete the `[[flag]]` table for `<name>` from `meta/flags.toml`.
2. [ ] Delete every gated code path, keeping only the winning branch: `grep -rn '"<name>"' backend web/src`
       (`flag(` / `useFlag(` / route `flag:` / `kb_distillery.flags.value(`). A `screen.<id>` flag that wins *on*
       becomes an unflagged route; one that wins *off* takes `web/src/features/<id>/` with it.
3. [ ] `pixi run flags-gen` — regenerates `web/src/flags/registry.gen.ts` and `routes/modules.share-*.ts`.
4. [ ] Remove the tests of the dead state (`withFlag("<name>", …)` / `@pytest.mark.flag("<name>", …)`);
       keep the winning state's tests as plain tests, without the flag wrapper.
5. [ ] `pixi run flags-check`, `pixi run test`, `pixi run web-check`, `pixi run lint`.
6. [ ] `pixi run ship -- commit "chore(flags): remove <name>"`, then `ship -- pr` and `ship -- merge`.
