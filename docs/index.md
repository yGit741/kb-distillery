# kb-distillery documentation

kb-distillery turns sources you collect into a linked, linted wiki. You keep the sources. An agent writes the pages. A linter checks every page against a schema. An app shows the result as a graph.

## Start here

- [Getting started](getting-started.md): install, create a knowledge base, open the app, run a first digest.
- [Architecture](architecture.md): the parts, the data flow and the rules that do not change.

## Concepts

- [Knowledge base](concepts/knowledge-base.md): the folder you own, its three areas and its git history.
- [Kit](concepts/kit.md): the schema a knowledge base follows.
- [Think](concepts/think.md): one personal journal outside every knowledge base.
- [Digest tiers](concepts/digest-tiers.md): easy, full and deep.
- [Language models](concepts/llm.md): providers, model tiers and billing.
- [Relations and proposals](concepts/relations-and-proposals.md): typed links and how they are proposed.
- [Publishing](concepts/publishing.md): an optional static site.

## Guides

- [Write a kit](guides/write-a-kit.md)
- [Write a skill](guides/write-a-skill.md)
- [Add a storage connector](guides/add-a-storage-connector.md)
- [Add a publisher](guides/add-a-publisher.md)
- [Import a bundle](guides/import-a-bundle.md)
- [The graph shell](guides/graph-shell.md)
- [Run the nightly job](guides/run-the-nightly-job.md)

## Reference

- [CLI](reference/cli.md): every `distill` command.
- [kb.toml](reference/kb-toml.md): the file that makes a folder a knowledge base.
- [Config files and environment](reference/config-files.md)
- [HTTP API](reference/http-api.md)
- [Agent docs](reference/agent-docs.md): the short documents the agents read.

## Project

- [Roadmap](public-roadmap.md)
- [Decision records](adr/0001-single-llm-gateway.md): why the engine is shaped this way.
