# syntax=docker/dockerfile:1
#
# kb-distillery for self-hosting: the app server behind an identity-aware proxy (KB_AUTH=proxy).
#
# Build context: the repo root with a freshly built wheel in dist/ (`pixi run python -m build --wheel`).
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     --build-arg VERSION=<version> --build-arg KB_WEB_BUNDLE_REPO=<owner>/<repo> -t kb-distillery:<version> .
# The web bundle is the release's prebuilt webapp-<version>.tar.gz (kb_distillery.webbuild.fetch_prebuilt), so no
# node toolchain is in the image. The wheel is pure Python and its dependencies ship wheels for amd64 and arm64.
#
# Run (the identity settings are mandatory: without them the server refuses to start, it never serves open):
#   docker run -p 8765:8765 -v kb-data:/data \
#     -e KB_AUTH_EMAIL=me@example.com -e KB_AUTH_JWKS_URL=https://proxy.example.com/keys \
#     -e KB_AUTH_AUDIENCE=<audience> kb-distillery:<version>

ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS build
ARG VERSION
ARG KB_WEB_BUNDLE_REPO
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY dist/ /dist/
RUN test -n "${VERSION}" && python -m venv /opt/venv \
 && /opt/venv/bin/pip install /dist/kb_distillery-${VERSION}-*.whl
# Unpack the prebuilt web bundle into the installed package, unless the wheel already carries one. A missing or
# corrupt bundle fails the build instead of shipping an image without a UI.
RUN /opt/venv/bin/python - <<'PY'
import os, sys
from kb_distillery.config.resources import resource
from kb_distillery.webbuild import fetch_prebuilt

dest = resource("_webapp")
if (dest / "index.html").is_file():
    sys.exit(0)
version = os.environ["VERSION"]
if not fetch_prebuilt(version, dest, repo=os.environ.get("KB_WEB_BUNDLE_REPO") or None):
    sys.exit("no web bundle for v" + version + " (set KB_WEB_BUNDLE_REPO=<owner>/<repo>)")
PY

FROM ${PYTHON_IMAGE} AS runtime
# git: knowledge bases are git repositories and `distill doctor` checks for it
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*' \
 && useradd --system --uid 10001 --create-home --home-dir /home/kb --shell /usr/sbin/nologin kb \
 && mkdir /data && chown kb:kb /data
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    KB_DISTILLERY_HOME=/data \
    XDG_CONFIG_HOME=/data/.config \
    KB_GRAPH_WARM=1 \
    KB_AUTH=proxy
USER kb
WORKDIR /data
VOLUME /data
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=30s --start-period=30s --retries=3 CMD ["distill", "doctor"]
# Binding 0.0.0.0 is allowed only because KB_AUTH=proxy is the image default: the server refuses a non-loopback
# bind in any other mode, and refuses to start in proxy mode without KB_AUTH_EMAIL and an identity source.
CMD ["python", "-m", "kb_distillery.server", "--host", "0.0.0.0", "--port", "8765", "--no-open", "--no-build"]
