"""YouTube lectures and videos → a raw/videos/<dir>/ bundle (0 LLM by default).

    scrap-youtube <url> [--tier transcript|vibe|frames] [--read]
        → raw/inbox/video-<dir>/   video.md (what an agent reads), video.json (what the app reads),
                                   transcript.vtt, info.json, frame-<seconds>.jpg
    catalog raw/inbox/video-<dir> → raw/videos/<dir>/ (one nested level, like raw/emails/)

Tiers:
    transcript  transcript + description + chapters + filtered comments; no video download
    vibe        + 1–3 representative frames with local OCR (the default; still 0 LLM)
    frames      + a full frame selection (slides: the fullest slide before each change; boards: the
                fullest board before each erase or camera cut), a budget per chapter, local OCR;
                `--read` adds a Claude read of each frame (LaTeX + one line per diagram)

The video file itself stays in .cache/youtube/<id>/ and never enters raw/.
"""
