"""One TLS setup for every ingest HTTP call (scrap, arXiv, Semantic Scholar).

Behind a TLS-inspecting corporate proxy Python's CA bundle lacks the proxy root and urllib fails
with CERTIFICATE_VERIFY_FAILED. Trust order: `truststore` (the OS trust store) → the macOS
keychain roots with VERIFY_X509_STRICT cleared (Python 3.13+ rejects common proxy certs with
"Missing Authority Key Identifier") → the default context. Chain and hostname checks stay on.
"""
import ssl
import subprocess
import sys
import urllib.request

MAC_KEYCHAINS = ["/Library/Keychains/System.keychain",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"]
_CTX = None


def keychain_pem():
    """macOS system keychain roots as PEM text (what curl trusts); "" elsewhere or on failure."""
    if sys.platform != "darwin":
        return ""
    try:
        return subprocess.run(["security", "find-certificate", "-a", "-p", *MAC_KEYCHAINS],
                              capture_output=True, text=True, timeout=10).stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _build_context():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:           # not installed / unsupported platform
        pass
    ctx = ssl.create_default_context()
    pem = keychain_pem()
    if pem:
        try:
            ctx.load_verify_locations(cadata=pem)
            ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        except ssl.SSLError:
            pass
    return ctx


def ssl_context():
    global _CTX
    if _CTX is None:
        _CTX = _build_context()
    return _CTX


def opener():
    """A urllib opener whose HTTPS handler uses ssl_context()."""
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context()))


def urlopen(req, timeout=None):
    """Drop-in for urllib.request.urlopen with the shared context."""
    return opener().open(req, timeout=timeout) if timeout is not None else opener().open(req)


def install():
    """Make plain `urllib.request.urlopen` (arxiv_meta's default opener, anything else in the
    process) use ssl_context(). Idempotent; called once from the ingest CLI."""
    ssl._create_default_https_context = ssl_context
