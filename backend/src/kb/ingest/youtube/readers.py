"""What a kept frame says: local OCR (Apple Vision, free) and, opt-in, a Claude read.

Apple Vision is accurate on printed slides and useless on chalk or handwritten math; the Claude read
gives LaTeX plus one line per graph or diagram, and the transcript around the frame lets it name
things it would otherwise guess ("NN" on an MIT board is nearest neighbours, not a neural net).
The read goes through `claude -p` on the subscription, like kb.metrics.golden.
"""
import json
import os
import subprocess

READ_MODEL = "sonnet"
READ_PROMPT = """Read the image {path}. It is a frame from an educational video.
What the speaker says around this moment (context, may help name things): "{context}"
Transcribe what the frame shows, top to bottom:
- formulas as LaTeX, each on its own line between $$ and $$; text as plain text
- for each graph, plot, diagram or animation, one line starting with "Diagram:" saying what it shows and what it illustrates
Mark text hidden by the speaker or hands as [occluded]. Output only the transcription."""
_SCRUBBED = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


def ocr(img):
    """[(line, confidence)] top to bottom; [] where Apple Vision is unavailable (not macOS)."""
    try:
        from ocrmac import ocrmac
    except ImportError:
        return []
    try:
        res = ocrmac.OCR(img, recognition_level="accurate", language_preference=["en-US"]).recognize()
    except Exception:
        return []
    res.sort(key=lambda r: (-round(r[2][1] + r[2][3], 2), r[2][0]))   # Vision's y grows upwards
    return [(t, float(c)) for t, c, _ in res]


def claude_read(path, context, model=READ_MODEL, timeout=240):
    """One frame → {text, model, tokens_in, tokens_out, usd} (usd as the CLI reports it)."""
    env = {k: v for k, v in os.environ.items() if k not in _SCRUBBED and not k.startswith(("PIXI_", "CONDA_"))}
    cmd = ["claude", "-p", READ_PROMPT.format(path=path, context=context.replace('"', "'")[:3000]),
           "--model", model, "--allowedTools", "Read", "--output-format", "json"]
    try:
        p = subprocess.run(cmd, cwd=os.path.dirname(path), env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        d = json.loads(p.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        return {"text": "", "error": str(e)[:200]}
    usage = d.get("usage") or {}
    last = (usage.get("iterations") or [{}])[-1]          # the turn that saw the image
    return {"text": (d.get("result") or "").strip(), "model": model,
            "tokens_in": (last.get("cache_creation_input_tokens") or 0) + (last.get("input_tokens") or 0),
            "tokens_out": usage.get("output_tokens") or 0, "usd": d.get("total_cost_usd")}
