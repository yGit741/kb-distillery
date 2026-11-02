# 0003. Knowledge lives outside the engine repository

Status: accepted.

## Context

The engine is public code. A knowledge base is personal: it holds what a person read and thought. In the first version, both lived in one repository. That made the repository impossible to publish without removing history, and it tied every change of the code to the data.

## Decision

The engine repository holds code, kits, docs, tests and one sample. Each knowledge base is a separate folder and its own git repository.

- The default place is `~/knowledge/<id>/`. `KB_DISTILLERY_HOME` changes the parent. `--kb <path>` points at any folder with a `kb.toml`.
- The engine finds knowledge bases by that folder layout. The folder name is the id.
- The think journal is one more repository, `~/knowledge/think/`, shared by all knowledge bases.
- The only knowledge base the engine tracks is `examples/demo`. Tests and docs use it.
- Knowledge commits go to the knowledge base's repository, with tags `kb-x.y.z`. Engine changes go to the engine repository through pull requests.
- A privacy scan checks tracked files for personal paths, names and token-shaped strings. A secret scan runs in CI.
- Settings that belong to a person, such as keys and the publisher account, live in `~/.config/kb-distillery/` or in the knowledge base's `kb.toml`. They are not defaults in code. Defaults that remain in the Cloudflare publisher's code are being moved to configuration.

## Consequences

- The repository can be cloned and published without any private data.
- A knowledge base has its own history, undo and snapshots.
- Tools must take the knowledge base as an input: `--kb`, `KB`, or the folder you are in. No code assumes a fixed path.
- Tests need a knowledge base. They use the demo or a temporary one.
- Contributors who work on the engine and on their own knowledge keep the two apart.

## Where

`src/kb_distillery/kbconfig.py`, `src/kb_distillery/lint/privacy.py`, `examples/demo/`, [Knowledge base](../concepts/knowledge-base.md).
