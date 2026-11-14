"""Structural checks of the self-hosting Dockerfile and .dockerignore (the image build itself runs in the release workflow)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def instructions(text=None):
    """(INSTRUCTION, argument) pairs: comments dropped, `\\` continuations and heredoc bodies folded into one entry."""
    text = DOCKERFILE.read_text(encoding="utf-8") if text is None else text
    out, buf, heredoc = [], "", None
    for line in text.splitlines():
        if heredoc:
            buf += "\n" + line
            if line.strip() == heredoc:
                heredoc = None
                out.append(buf)
                buf = ""
            continue
        if not buf and (not line.strip() or line.lstrip().startswith("#")):
            continue
        if line.lstrip().startswith("#"):
            continue
        buf += (" " if buf else "") + line.rstrip("\\").strip()
        if line.rstrip().endswith("\\"):
            continue
        m = re.search(r"<<-?['\"]?(\w+)['\"]?", buf)
        if m:
            heredoc = m.group(1)
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return [tuple(i.split(None, 1)) + ("",) * (len(i.split(None, 1)) == 1) for i in out]


def final_stage():
    ins = instructions()
    start = max(i for i, (k, _) in enumerate(ins) if k.upper() == "FROM")
    return ins[start:]


def of(kind, ins=None):
    return [a for k, a in (final_stage() if ins is None else ins) if k.upper() == kind]


def test_files_exist():
    assert DOCKERFILE.is_file()
    assert DOCKERIGNORE.is_file()


def test_multi_stage_build_with_runtime_stage():
    froms = [a for k, a in instructions() if k.upper() == "FROM"]
    assert len(froms) >= 2
    assert froms[0].lower().endswith(" as build") and froms[-1].lower().endswith(" as runtime")


def test_no_platform_pin_so_the_image_builds_for_amd64_and_arm64():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "--platform" not in "\n".join(a for k, a in instructions() if k.upper() == "FROM")
    assert "amd64" in text and "arm64" in text          # the build command documents both


def test_installs_wheel_and_prebuilt_web_bundle():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"pip install .*\.whl", text)
    assert "fetch_prebuilt" in text
    assert re.search(r"COPY dist/", text)
    assert "node" not in " ".join(a for k, a in instructions() if k.upper() == "RUN").lower()


def test_exposes_the_server_port_and_runs_it():
    assert of("EXPOSE") == ["8765"]
    cmd = " ".join(of("CMD"))
    assert "kb_distillery.server" in cmd and "8765" in cmd and "--no-open" in cmd


def test_data_volume_and_home():
    assert of("VOLUME") == ["/data"]
    env = " ".join(of("ENV"))
    assert re.search(r"KB_DISTILLERY_HOME=/data\b", env)


def test_runs_as_non_root():
    users = of("USER")
    assert users and users[-1] not in {"root", "0", "0:0", "root:root"}
    runs = " ".join(of("RUN"))
    assert "useradd" in runs or "adduser" in runs


def test_healthcheck_runs_doctor():
    hc = of("HEALTHCHECK")
    assert len(hc) == 1 and "distill" in hc[0] and "doctor" in hc[0]
    assert "NONE" not in hc[0].upper().split()[:1]


def test_healthcheck_probes_the_port_the_server_listens_on():
    (hc,) = of("HEALTHCHECK")
    assert "create_connection" in hc
    (port,) = re.findall(r"\('127\.0\.0\.1', (\d+)\)", hc)
    assert re.search(rf"\"--port\",\s*\"{port}\"", " ".join(of("CMD"))), "healthcheck port differs from the CMD --port"
    assert port in " ".join(of("EXPOSE")).split()


def test_proxy_auth_is_the_image_default():
    env = " ".join(of("ENV"))
    assert re.search(r"\bKB_AUTH=proxy\b", env)
    # the all-interfaces bind is only acceptable because the default mode is proxy (security.assert_loopback_bind)
    assert "0.0.0.0" in " ".join(of("CMD"))


def test_no_identity_or_secret_values_baked_in():
    text = DOCKERFILE.read_text(encoding="utf-8")
    declared = " ".join(a for k, a in instructions() if k.upper() in {"ENV", "ARG"})
    for var in ("KB_AUTH_EMAIL", "KB_AUTH_JWKS_URL", "KB_AUTH_AUDIENCE", "KB_AUTH_JWT_KEY", "KB_AUTH_HEADER"):
        assert var not in declared, f"{var} must come from the run command"
    forbidden = re.compile(r"(api[_-]?key|secret|token|password|BEGIN [A-Z ]*PRIVATE KEY|sk-ant-|ghp_|AKIA)", re.I)
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    assert not forbidden.search(code)


def test_no_personal_strings():
    text = DOCKERFILE.read_text(encoding="utf-8") + DOCKERIGNORE.read_text(encoding="utf-8")
    assert not re.search(r"/Users/|/home/(?!kb\b)\w+", text)
    assert not re.search(r"[\w.+-]+@(?!example\.com)[\w-]+\.\w+", text)


def ignored():
    return {l.strip().rstrip("/") for l in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.lstrip().startswith("#")}


@pytest.mark.parametrize("name", [".git", ".claude", "raw", "wiki", "think", "node_modules"])
def test_dockerignore_excludes(name):
    assert name in ignored()


def test_dockerignore_keeps_the_wheel_directory():
    assert "dist" not in ignored() and not any(p in ignored() for p in ("*", "**"))


def test_files_are_registered_as_tooling():
    from kb_distillery.vault.schema import TOOLING_PATHS, lane_of
    assert "Dockerfile" in TOOLING_PATHS and ".dockerignore" in TOOLING_PATHS
    assert lane_of("Dockerfile") == "tooling" and lane_of(".dockerignore") == "tooling"
