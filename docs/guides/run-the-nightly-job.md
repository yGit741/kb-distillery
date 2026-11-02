# Run the nightly job

The nightly job keeps the knowledge base's git history in order. It commits human edits to the think journal, commits labelled leftovers when no session is open, and pushes `main` with its tags. Each knowledge operation already commits itself, so the job is a backstop.

After the sync, it runs the hygiene checks and sends the nightly report when something is wrong.

## What you need

- macOS with launchd.
- A checkout of this repository with `pixi install` done.

## Install

```bash
pixi run install-sync
```

This fills the plist template `examples/launchd/*daily-sync.plist` with your paths and loads it as a user agent. It runs `pixi run daily-sync` every day at 22:00 local time. A run missed during sleep starts on wake.

To remove it:

```bash
pixi run install-sync -- --uninstall
```

## Run by hand

```bash
pixi run daily-sync -- --dry-run     # print the actions, write nothing
pixi run daily-sync -- --no-push     # commit but do not push
pixi run hygiene                     # the checks alone; exit 1 on an error-level finding
pixi run nightly-report              # a text preview of the report
pixi run nightly-report -- --html report.html
```

`nightly-report --send` sends the mail now.

## Mail

The mail is optional. Configure it in `meta/ops/sync.toml` of the knowledge base:

```toml
[notify]
email = "you@example.org"
mode = "problems"             # "digest" mails every night, "problems" only when something needs fixing
on = ["error", "warn"]
min_interval_hours = 20
```

The password is a macOS keychain item named `kb-distillery-gmail` for that address. The job sends through Gmail SMTP over SSL. It never prints or stores the password. `pixi run notify-test` sends a one-line test mail and says when the keychain item is missing.

## Check that it runs

```bash
pixi run distill ops status --kb my-kb
```

The status shows whether the nightly sync is installed and when it last ran.

## Choose the knowledge base

The job works on the knowledge base that `--kb` or `KB` selects. With one knowledge base, no setting is needed. With several, add `--kb <id>` to the command in the installed plist.

## Notes

- The job must run on the machine that holds the edits. A cloud agent cannot see local files.
- Pushing needs a remote on the knowledge base repository. `--no-push` or `KB_NO_PUSH=1` skips it.

More: [lifecycle.md](../../src/kb_distillery/kits/base/defaults/docs/lifecycle.md)
