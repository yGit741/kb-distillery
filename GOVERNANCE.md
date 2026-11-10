# Governance

kb-distillery is a small project with a single maintainer. This file says who decides what, so that contributors know what to expect.

## Roles

| Role | Who | Can |
|---|---|---|
| Maintainer | the repository owner | merge, release, change the schema, enforce the code of conduct |
| Invited contributor | anyone the maintainer invites to work on core | open pull requests against core |
| Contributor | everyone | open issues and discussions; open pull requests against docs and examples; publish extensions |

## Decisions

- Day to day changes are decided by the maintainer in review.
- A change to the page model (schema) or to the paradigm is held until the maintainer approves it explicitly, and ships with a migration.
- Larger ideas start as an issue. The maintainer replies with accept, defer or decline and a reason. Silence beyond two weeks is a reason to ask again.
- Disagreements are settled in the issue, in public, by the maintainer. The goal is a clear answer, not a vote.

## Becoming an invited contributor

Core pull requests are by invitation (see [CONTRIBUTING.md](CONTRIBUTING.md)). The usual path: report issues, improve docs and examples, publish an extension, then ask. The maintainer invites people whose work shows they understand the layer contract and the hard rules in `AGENTS.md`.

## Releases

The maintainer cuts releases from `main`; `CHANGELOG.md` is the record. Versions follow `0.x` until the interfaces settle.

## Conduct and reporting contact

- Conduct reports: see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Vulnerability reports: the repository's private vulnerability reporting, described in [.github/SECURITY.md](.github/SECURITY.md).
- Placeholder: the maintainer adds a monitored private contact address here before the repository goes public.

## Changing this file

By pull request, approved by the maintainer. If the project grows beyond one maintainer, this file is updated first.
