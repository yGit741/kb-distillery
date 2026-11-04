"""Publish tests never run node: a private Worker folder gets a stub where deploy would bundle the OKF checker."""
import pytest


@pytest.fixture(autouse=True)
def _no_okf_bundle(monkeypatch):
    from kb_distillery.publish.cloudflare import deploy
    monkeypatch.setattr(deploy, "build_okf_bundle", lambda out: out.write_text("// stub", encoding="utf-8"))
