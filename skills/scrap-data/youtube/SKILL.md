---
name: scrap-data-youtube
description: Turn a YouTube lecture or video into a raw/inbox/video-<name>/ bundle — transcript by chapter, description, filtered comments and key frames (0 LLM unless --read). Use for scrap youtube, save this lecture, save this video, youtube URL. Do NOT catalog or digest from here.
---

# scrap-data / youtube

**LLM tier:** none (`--read`: Sonnet, ~2k tokens per frame) · **Budget:** 0 tokens by default

## Triggers

- `scrap <youtube url>`, `save this lecture`, `save this video`, a `youtube.com/watch?v=` or `youtu.be/` link
- A playlist link names one video (`v=`); scrap each lecture of a course on its own

## Do NOT

- Scrap without `resolve` first — `python3 -m kb.ingest resolve <url>` finds a bundle by its YouTube id
- Use `--read` unless the user asked for frame reads (it spends LLM tokens: about $0.01 per frame on the API, $0.08 through the CLI)
- Catalog or digest from here — `catalog raw/inbox/video-<name>` is the next step

## CLI

```bash
python3 -m kb.ingest scrap-youtube <url>                      # tier vibe (default): transcript + 1-3 frames
python3 -m kb.ingest scrap-youtube <url> --tier transcript    # transcript, description, chapters, comments only
python3 -m kb.ingest scrap-youtube <url> --tier frames        # full frame selection, budget 30/hour, local OCR
python3 -m kb.ingest scrap-youtube <url> --tier frames --read # + a Claude read of each frame (LaTeX + diagrams)
python3 -m kb.ingest scrap-youtube <url> --force              # again, although the video is in the vault
```

## Tiers

| tier | what | cost | typical size |
|---|---|---|---|
| `transcript` | subtitles (manual track first, else auto captions), description + links, chapters, top comments with a timestamp/link/question | 0 LLM, no video download | ~10–14k tokens per hour |
| `vibe` | + 1–3 frames: 24 evenly spaced samples, the most informative per third (OCR words or board chalk), local OCR | 0 LLM, 720p download | + ~0.3k |
| `frames` | + slides: last frame before each change, deduplicated on OCR words; blackboards: fullest board before each erase or camera cut, close-ups kept; budget per chapter | 0 LLM, ~1 min of analysis per 5 min of video | + ~0.1k per frame |
| `frames --read` | + Claude read per frame with the nearby transcript as context | ~1.5k in + 0.6k out per frame | + ~0.6k per frame |

The mode (slides or board) is decided per video from a 1 fps pass (`backend/src/kb/ingest/youtube/frames.py`).
Paper-and-marker, animation (3Blue1Brown) and screencast videos fall back to the slide picker; their own pickers
are follow-ups.

## Bundle

`raw/inbox/video-<kebab title>/` → after catalog `raw/videos/<kebab title>/`:

- `video.md` — the raw item an agent reads: frontmatter (title, url, channel, duration, transcript kind, tier),
  description, chapters, top comments, then the transcript by chapter in ~3 min sections, each frame inline in the
  section where it was shown with its read (or OCR)
- `video.json` — the same, structured, for the app; `info.json` (slim yt-dlp metadata); `transcript.vtt`
- `frame-<seconds>.jpg` — gitignored binaries like PDFs (git stays text-only), `asset:` rows of `video.md` in
  `meta/corpus.tsv`; a clone or the shared site has the text and the frame links, not the images

The video file stays in `.cache/youtube/<id>/` and never enters `raw/`.

## Next step

`python3 -m kb.ingest catalog raw/inbox/video-<name> [--collection course-…]` (a course lecture joins the course's
Contents table), then a digest tier — `easy-digest raw/videos/<name>/video.md` writes the `video-<name>` page.

## Commit

`scrap-youtube` commits itself as `kb(import): video <name> into the inbox (kb-x.y.z)` (`--no-commit` to skip).
