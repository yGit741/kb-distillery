"""YouTube lectures and videos: one standard raw bundle at ingest, frame reads at digest.

    scrap-youtube <url>              → raw/inbox/video-<dir>/ (0 LLM): video.md, video.json, info.json,
                                       transcript.vtt, a-<seconds>.jpg (one thumbnail per anchor)
    catalog raw/inbox/video-<dir>    → raw/videos/<dir>/ (one nested level, like raw/emails/)
    easy-digest raw/videos/<dir>/video.md               transcript skim (Haiku)
    video-digest raw/videos/<dir>/video.md --tier full  top anchors ~15/hour read by Claude → ## Frames
    video-digest … --tier deep                          ~30/hour, plus Connections

Anchors (frames.py) are scored timestamps where the screen likely shows something worth reading — recall
first; the digest tiers decide how many to read (digest.py). The video file stays in .cache/youtube/<id>/.
"""
