"""Suite-wide isolation: tests never mint a real GitHub App token (kb.git.app_token)."""
import os

os.environ["KB_APP_CONFIG"] = os.path.join(os.sep, "nonexistent", "kb-app.toml")
