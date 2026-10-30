---
name: scrap-data-youtube
description: Turn a YouTube lecture or video into a raw/inbox/video-<name>/ bundle — transcript by chapter, description, filtered comments, and anchors (scored timestamps worth a frame, with thumbnails), 0 LLM. Use for scrap youtube, save this lecture, save this video, a youtube URL. Do NOT catalog or digest from here.
---

# scrap-data / youtube

**LLM tier:** none · **Budget:** 0 tokens (frame reads belong to the digest tiers)

## Triggers

- `scrap <youtube url>`, `save this lecture`, `save this video`, a `youtube.com/watch?v=` or `youtu.be/` link
- A playlist link names one video (`v=`); scrap each lecture of a course on its own

## Do NOT

- Scrap without `resolve` first — `python3 -m kb.ingest resolve <url>` finds a bundle by its YouTube id
- Read frames here — that is `video-digest` (full / deep), which spends LLM tokens
- Scrap animation-led videos such as 3Blue1Brown (Grant Sanderson): the content lives in continuous animation,
  which a frame budget cannot digest well — the owner's call (2026-10-26). Lectures (slides, blackboard), paper-
  and-marker explainers and slide-style explainers (StatQuest) are in scope
- Catalog or digest from here — `catalog raw/inbox/video-<name>` is the next step

## CLI

```bash
python3 -m kb.ingest scrap-youtube <url>            # one standard bundle, 0 LLM
python3 -m kb.ingest scrap-youtube <url> --force    # refresh the bundle of a video already in the vault
```

## Bundle (one format, no tiers)

`raw/inbox/video-<kebab title>/` → after catalog `raw/videos/<kebab title>/` (one nested level):

- `video.md` — the raw item: frontmatter (title, url, channel, duration, transcript kind, anchors), description,
  chapters, top comments (with a timestamp, link or question), then the transcript by chapter in ~3 min sections,
  each followed by its anchors (time, kind, score)
- `video.json` — the same, structured, for the app; `info.json` (slim metadata); `transcript.vtt`
- `a-<seconds>.jpg` — one 640 px thumbnail per anchor (~25 KB), gitignored like every raw image, `asset:` rows of
  `video.md` in `meta/corpus.tsv`; a clone or the shared site has the text, not the images

**Anchors** (`backend/src/kb/ingest/youtube/frames.py`) aim at recall: every timestamp where the screen likely shows
something worth reading, scored, never dropped. Signals: the fullest board before each erase or camera cut
(blackboard lectures), the last frame before each slide change scored by its OCR words (slides), transcript cues
("as you can see", "this equation"), chapter starts, and coverage (the most stable second of any 90 s stretch with
no anchor — paper, screencast, whatever the detectors miss). Audience shots and half-written boards stay with a low score. Expect
~100–150 anchors per hour of blackboard, fewer for slides.

Subtitles: one English track, manual first; YouTube rate-limits subtitle bursts (HTTP 429), so the fetch retries
with backoff for ~10 min and then fails with "rerun later" — the video stays cached, the rerun is cheap. The video
file stays in `.cache/youtube/<id>/` and never enters `raw/`. Local processing ≈ 1 min per 10 min of video.

## Digest tiers for a video page

| tier | command | reads | cost |
|---|---|---|---|
| easy | `easy-digest raw/videos/<name>/video.md` | transcript skim (metadata, chapters, start and end) | ~3k tokens, Haiku |
| full | `video-digest raw/videos/<name>/video.md --tier full` | top anchors ~15/hour, ≥ 2 min apart, each read by Claude with the transcript around it | ~1.4k in + 0.5k out per frame (≈ $0.15 per lecture-hour on the API) |
| deep | `video-digest … --tier deep` | ~30/hour, ≥ 1 min apart, + Connections into the wiki | ≈ twice full |

Frame reads go through `kb.llm`: `--backend subscription|api|batch` (default `$KB_LLM_BACKEND`, then
subscription), `--model` (default sonnet). All of a video's frames are one run, so `--backend batch` is one
half-price Message Batch per video (results within hours; the command waits).

`video-digest` writes `## Frames` on the page (thumbnail + read per frame, math as display blocks) and drafts
`## Key equations` from the reads; the agent then reads `meta/.ingest/video/<sha>/abstract.text` (full transcript +
reads), writes Problem, Main result, Key ideas, curates Key equations, Takeaways (deep: Connections), runs
`pixi run lint` and `pixi run ops -- commit`.

## Next step

`python3 -m kb.ingest catalog raw/inbox/video-<name> [--collection course-…]` (a course lecture joins the course's
Contents table), then a digest tier.

## Commit

`scrap-youtube` commits itself as `kb(import): video <name> into the inbox (kb-x.y.z)` (`--no-commit` to skip).
