"""scrap-youtube: transcript parsing, sections, comment filter, frame selection, bundle wiring (offline)."""
import json
import os

import numpy as np
import pytest

from kb_distillery.vault.schema import unit_slug_for_raw, unit_type_for_raw
from kb_distillery.ingest.sources.youtube import bundle, frames as fx, transcript as tr
from kb_distillery.ingest.sources.youtube.fetch import pick_subs, video_id

MANUAL = """WEBVTT
Kind: captions
Language: en-US

00:00:01.000 --> 00:00:04.000
Hello and welcome.

00:00:04.000 --> 00:00:09.000
Today we talk about
support vector machines.
"""

AUTO = """WEBVTT
Kind: captions
Language: en

00:00:00.160 --> 00:00:02.000 align:start position:0%

hey<00:00:00.480><c> everyone</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
hey everyone

00:00:02.010 --> 00:00:04.000 align:start position:0%
hey everyone
welcome<00:00:02.500><c> back</c>
"""


def test_parse_vtt_manual_joins_block_lines():
    assert tr.parse_vtt(MANUAL) == [(1.0, "Hello and welcome."),
                                    (4.0, "Today we talk about support vector machines.")]


def test_parse_vtt_auto_keeps_only_new_rolling_lines():
    assert [t for _, t in tr.parse_vtt(AUTO)] == ["hey everyone", "welcome back"]


def test_sections_follow_chapters_and_cut_long_ones_at_sentence_ends():
    cues = [(float(t), f"word {t}." if t % 50 == 0 else f"word {t}") for t in range(0, 600, 10)]
    chapters = [{"title": "Intro", "start_time": 0, "end_time": 100},
                {"title": "Main", "start_time": 100, "end_time": 600}]
    secs = tr.sections(cues, chapters, 600, target=180)
    assert [s["chapter"] for s in secs][0] == "Intro"
    assert {s["chapter"] for s in secs} == {"Intro", "Main"}
    main = [s for s in secs if s["chapter"] == "Main"]
    assert len(main) >= 2 and all(s["text"] for s in main)
    assert secs[-1]["end"] == 600


def test_sections_without_chapters_is_one_unnamed_chapter():
    secs = tr.sections([(0.0, "a."), (5.0, "b.")], None, 10)
    assert len(secs) == 1 and secs[0]["chapter"] == "" and secs[0]["text"] == "a. b."


def test_keep_comments_drops_thank_you_notes():
    cs = [{"parent": "root", "author": "a", "like_count": 500, "text": "thanks Stanford!!!"},
          {"parent": "root", "author": "b", "like_count": 3, "text": "At 15:50 the prior is weighted, why?"},
          {"parent": "x", "author": "c", "like_count": 900, "text": "a reply https://x.y"},
          {"parent": "root", "author": "d", "like_count": 1, "text": "see https://arxiv.org/abs/1"}]
    kept = tr.keep_comments(cs)
    assert [c["author"] for c in kept] == ["b", "d"]
    assert kept[0]["stamps"] == ["15:50"]


@pytest.mark.parametrize("url", ["https://www.youtube.com/watch?v=Ub3GoFaUcds&list=PLx",
                                 "https://youtu.be/Ub3GoFaUcds", "Ub3GoFaUcds"])
def test_video_id(url):
    assert video_id(url) == "Ub3GoFaUcds"


def test_pick_subs_prefers_a_manual_track(tmp_path):
    for lang in ("en", "en-US"):
        (tmp_path / f"abcdefghijk.{lang}.vtt").write_text("WEBVTT\n")
    path, kind = pick_subs(str(tmp_path), "abcdefghijk", {"subtitles": {"en-US": []}})
    assert path.endswith(".en-US.vtt") and kind == "manual"
    path, kind = pick_subs(str(tmp_path), "abcdefghijk", {"subtitles": {}})
    assert path.endswith(".en.vtt") and kind == "auto"


# --- frames -------------------------------------------------------------------------------------

def _board_frame(chalk_lines=4):
    g = np.full((fx.H, fx.W), 200, np.uint8)            # bright wall
    g[10:120, 20:300] = 40                               # dark board
    for k in range(chalk_lines):
        g[25 + 20 * k, 40:260] = 230                     # chalk strokes
    return g


def test_board_mask_and_chalk():
    g = _board_frame()
    m = fx.board_mask(g)
    assert m.mean() > fx.MIN_BOARD
    assert fx.ink_map(g, m).sum() > 400
    blank = np.full((fx.H, fx.W), 200, np.uint8)
    assert fx.board_mask(blank).mean() == 0


def _analysis(ink, change, board=0.6):
    n = len(ink)
    return {"fr": np.zeros((n, fx.H, fx.W), np.uint8), "board": np.full(n, board),
            "ink": np.array(ink), "change": np.array(change, float), "delta": np.zeros(n)}


def test_board_candidates_keep_the_fullest_state_before_an_erase_and_a_cut():
    ink = [300, 500, 800, 900, 100, 100, 100, 100, 400, 700, 700, 50, 400, 600, 650, 660]
    change = [1.0] + [0.01] * 10 + [0.9] + [0.01] * 4          # camera cut at t=11
    cands = fx.board_candidates(_analysis(ink, change))
    assert [(c["t"], c["end"]) for c in cands] == [(3, "erase"), (9, "cut"), (15, "cut")]


def test_slide_candidates_are_last_frames_before_a_change():
    a = _analysis([0] * 20, [0.0] * 20)
    a["delta"] = np.array([255] + [0] * 7 + [20] + [0] * 6 + [20] + [0] * 3, float)
    assert [c["t"] for c in fx.slide_candidates(a)] == [7, 14]


def test_dedup_slides_keeps_the_fullest_build_and_separates_templated_slides():
    w = lambda s: set(s.split())
    cands = [{"t": 1, "words": w("attention mechanism query key")},
             {"t": 5, "words": w("attention mechanism query key value softmax")},
             {"t": 9, "words": w("transformer encoder decoder layers stack")},
             {"t": 12, "words": w("speaker")}]
    kept = fx.dedup_slides(cands)
    assert [k["t"] for k in kept] == [5, 9]


def test_signals_merge_into_anchors_with_reasons_and_summed_scores():
    a = _analysis([0] * 400, [0.0] * 400)
    a["delta"] = np.zeros(400)
    a["delta"][[50, 200]] = 20                                      # two slide changes
    cues = [(45.0, "and as you can see here"), (300.0, "nothing to see")]
    sig = fx.signals(a, "slides", cues, [{"title": "Intro", "start_time": 0}])
    anchors = fx.merge(sig)
    first = [x for x in anchors if abs(x["t"] - 52) <= fx.MERGE_S][0]
    assert set(first["why"]) == {"slide-change", "cue: as you can see"} and first["score"] == 4
    assert any(x["why"] == ["chapter: Intro"] for x in anchors)


def test_cover_fills_every_long_gap_with_its_most_stable_second():
    delta = np.full(400, 9.0)
    delta[150] = 0.5
    out = fx.cover([{"t": 10, "why": ["x"], "score": 3}], delta, cover_s=90)
    ts = [x["t"] for x in out]
    assert 150 in ts and all(b - a <= 90 for a, b in zip(ts, ts[1:] + [399]))
    assert all(x["score"] == 0 for x in out if x["why"] == ["coverage"])


def test_mode_of_needs_a_board_and_chalk_on_it():
    board = np.array([0.6] * 7 + [0.0] * 3)
    assert fx.mode_of({"board": board, "ink": np.full(10, 1500)}) == "board"
    assert fx.mode_of({"board": board, "ink": np.full(10, 4)}) == "slides"       # a black table under paper
    assert fx.mode_of({"board": np.array([0.0] * 9 + [0.6]), "ink": np.full(10, 1500)}) == "slides"


def test_adjust_sinks_room_shots_in_a_slide_lecture_and_sponsor_stretches():
    anchors = [{"t": t, "score": 9, "why": ["slide-change"], "flat": f} for t, f in
               [(10, 0.8), (20, 0.75), (30, 0.36), (40, 0.7), (980, 0.8)]]
    fx.adjust(anchors, "slides", [{"title": "Talent", "start_time": 900, "end_time": 960}], 1000)
    by = {x["t"]: x for x in anchors}
    assert by[30]["score"] == 6 and "camera shot" in by[30]["why"] and by[10]["score"] == 9
    assert by[980]["score"] == 5                                   # last 3% of the video
    paper = [{"t": t, "score": 5, "why": [], "flat": 0.44} for t in range(0, 500, 50)]
    fx.adjust(paper, "slides", [], 1000)
    assert all(x["score"] == 5 for x in paper)                     # no clean slides: nothing is a room shot


# --- bundle and vault wiring --------------------------------------------------------------------

META = {"id": "abcdefghijk", "title": "Lecture 16: SVM", "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "channel": "MIT", "duration": 600, "uploaded": "2014-01-10", "description": "See https://ocw.mit.edu",
        "chapters": [{"title": "Intro", "start": 0, "end": 300}], "subs_kind": "manual"}


def test_render_md_lists_anchors_under_their_section():
    secs = [{"chapter": "Intro", "start": 10, "end": 300, "text": "Hello."},
            {"chapter": "Intro", "start": 300, "end": 600, "text": "Lagrange."}]
    anchors = [{"t": 4, "thumb": "a-00004.jpg", "kind": "board", "score": 0},
               {"t": 400, "thumb": "a-00400.jpg", "kind": "board", "score": 7}]
    md = bundle.render_md(META, secs, anchors, [])
    assert md.startswith("---\ntitle: \"Lecture 16: SVM\"") and "anchors: 2" in md
    assert md.index("Hello.") < md.index("a-00004.jpg") < md.index("Lagrange.") < md.index("a-00400.jpg")
    assert md.count("## Intro") == 1 and "## Chapters" in md


def test_abstract_reads_the_bundle_data(tmp_path):
    d = {**META, "sections": [{"chapter": "Intro", "start": 0, "end": 600, "text": " ".join(["w"] * 2000)}]}
    (tmp_path / "video.json").write_text(json.dumps(d))
    text = bundle.abstract(str(tmp_path / "video.md"))
    assert "Title: Lecture 16: SVM" in text and "Chapters:" in text and "[…]" in text


def test_dir_name_is_kebab_and_unique(tmp_path):
    assert bundle.dir_name("Lecture 16: Support Vector Machines!", "abcdefghijk", str(tmp_path)) == \
        "lecture-16-support-vector-machines"
    os.makedirs(tmp_path / "raw" / "videos" / "lecture-16-support-vector-machines")
    assert bundle.dir_name("Lecture 16: Support Vector Machines!", "AbC_defghij", str(tmp_path)) == \
        "lecture-16-support-vector-machines-abc-defghij"


def test_existing_finds_a_bundle_by_youtube_id(tmp_path):
    d = tmp_path / "raw" / "videos" / "svm"
    d.mkdir(parents=True)
    (d / "info.json").write_text(json.dumps({"id": "abcdefghijk"}))
    assert bundle.existing("abcdefghijk", str(tmp_path)) == ["raw/videos/svm"]
    assert bundle.existing("zzzzzzzzzzz", str(tmp_path)) == []


def test_a_video_bundle_is_a_video_source_named_by_its_folder():
    rel = "raw/videos/lecture-16-svm/video.md"
    assert unit_type_for_raw(rel) == "video"
    assert unit_slug_for_raw(rel) == "video-lecture-16-svm"


def test_lint_binds_bundle_files_to_video_md():
    from kb_distillery.lint.lint import asset_source
    on_disk = {"raw/videos/svm/video.md", "raw/videos/svm/a-00042.jpg", "raw/videos/svm/video.json"}
    assert asset_source("raw/videos/svm/a-00042.jpg", on_disk) == "raw/videos/svm/video.md"
    assert asset_source("raw/videos/svm/video.json", on_disk) == "raw/videos/svm/video.md"
    assert asset_source("raw/videos/svm/video.md", on_disk) is None
    assert asset_source("raw/videos/other/a-00001.jpg", on_disk) is None


def _bundle(folder, vid, anchors=True):
    folder.mkdir(parents=True)
    (folder / "video.md").write_text("# v\n")
    (folder / "info.json").write_text(json.dumps({"id": vid}))
    (folder / "video.json").write_text(json.dumps({"title": "SVM", "anchors": [{"t": 1}] if anchors else []}))


def test_catalog_refresh_keeps_the_old_bundle_aside_and_refuses_strangers(tmp_path, monkeypatch):
    from kb_distillery.ingest import catalog
    monkeypatch.setattr(catalog, "ROOT", str(tmp_path))
    monkeypatch.setattr(catalog, "_run_lint", lambda: None)
    monkeypatch.setattr(catalog, "_join", lambda *a: None)
    _bundle(tmp_path / "raw" / "videos" / "svm", "abcdefghijk")
    (tmp_path / "raw" / "videos" / "svm" / "old-read.txt").write_text("paid")
    _bundle(tmp_path / "raw" / "inbox" / "video-svm", "abcdefghijk")
    catalog.catalog_video("raw/inbox/video-svm")                   # same video: refreshed
    assert not (tmp_path / "raw" / "videos" / "svm" / "old-read.txt").exists()
    kept = list((tmp_path / "_quarantine").glob("videos-svm-*/old-read.txt"))
    assert kept and kept[0].read_text() == "paid"                  # the old bundle is kept, not deleted
    _bundle(tmp_path / "raw" / "inbox" / "video-svm", "zzzzzzzzzzz")
    with pytest.raises(ValueError, match="destination exists"):     # another video with the same name
        catalog.catalog_video("raw/inbox/video-svm")
    import shutil
    shutil.rmtree(tmp_path / "raw" / "inbox" / "video-svm")
    _bundle(tmp_path / "raw" / "inbox" / "video-svm", "abcdefghijk", anchors=False)
    with pytest.raises(ValueError, match="no anchors"):            # would replace anchors with none
        catalog.catalog_video("raw/inbox/video-svm")
    assert (tmp_path / "raw" / "videos" / "svm" / "video.md").exists()


def test_catalog_detects_a_video_bundle(tmp_path, monkeypatch):
    from kb_distillery.ingest import catalog
    d = tmp_path / "raw" / "inbox" / "video-svm"
    d.mkdir(parents=True)
    monkeypatch.setattr(catalog, "ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        catalog.detect_format("raw/inbox/video-svm")          # no video.md yet: not a bundle
    (d / "video.md").write_text("# SVM\n")
    assert catalog.detect_format("raw/inbox/video-svm") == "videos"


def test_ops_target_of_a_video_bundle_is_its_folder():
    from kb_distillery.ops.wrap import _target
    assert _target(["raw/inbox/video-svm/a-00042.jpg", "raw/inbox/video-svm/video.md"], ["scrap-youtube"]) == "svm"


def test_pick_reads_nothing_when_no_anchor_is_worth_it(tmp_path):
    from kb_distillery.ingest.sources.youtube import digest
    anchors = _thumbs(tmp_path, [{"t": t, "score": 0} for t in (10, 200, 400)])
    assert digest.pick(anchors, duration=600, tier="full", root=str(tmp_path)) == []


def test_render_md_without_a_transcript_still_lists_the_anchors():
    md = bundle.render_md(META, [], [{"t": 4, "thumb": "a-00004.jpg", "kind": "slide", "score": 3}], [])
    assert "No English transcript" in md and "## Anchors" in md and "a-00004.jpg" in md


def _tiny_video(path, seconds=260):
    """A 1 fps grey H.264 mp4, like a yt-dlp download: a dark 'board' whose chalk lines grow, so analyse has
    something to measure. Encoded by the bundled ffmpeg, not cv2.VideoWriter, whose mp4v writer produces no
    readable file on Intel Macs (and production never writes video with OpenCV)."""
    import subprocess
    from kb_distillery.ingest.sources.youtube.fetch import ffmpeg_exe
    raw = b"".join(_board_frame(chalk_lines=1 + (s // 40) % 5).tobytes() for s in range(seconds))
    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{fx.W}x{fx.H}",
                    "-r", "1", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], input=raw, check=True)
    assert os.path.getsize(path) > 0
    return str(path)


def test_analyse_runs_the_board_pass_in_worker_processes(tmp_path):
    from kb_distillery.ingest.sources.youtube.fetch import ffmpeg_exe
    mp4 = _tiny_video(tmp_path / "v.mp4")
    a = fx.analyse(mp4, ffmpeg_exe(), workers=2)                      # 260 frames = 3 chunks → the pool path
    assert len(a["board"]) == len(a["ink"]) == len(a["delta"]) == len(a["fr"]) >= 250
    assert float(a["board"].mean()) > fx.MIN_BOARD and int(a["ink"].max()) > 0
    assert fx.mode_of(a) == "board"


def _digest_env(tmp_path, monkeypatch, reads):
    """A vault in tmp_path with one bundle + page, the video and the Claude reads stubbed."""
    from kb_distillery.ingest import easy_digest as ed, course
    from kb_distillery.ingest.sources.youtube import digest, readers
    folder = tmp_path / "raw" / "videos" / "svm"
    folder.mkdir(parents=True)
    anchors = _thumbs(folder, [{"t": t, "score": 5, "kind": "board", "why": ["board-erase"], "ocr": []}
                               for t in (30, 200)])
    for x in anchors:
        x["thumb"] = x.pop("thumb_path")
    (folder / "video.json").write_text(json.dumps({**META, "sections": [{"chapter": "", "start": 0, "end": 260,
                                                                         "text": "Lagrange."}], "anchors": anchors}))
    (folder / "video.md").write_text("# SVM\n")
    (tmp_path / "wiki").mkdir()
    page = tmp_path / "wiki" / "video-svm.md"
    page.write_text("---\ntype: video\nlayer: source\nmaturity: digested\ndepth: deep\nraw: raw/videos/svm/video.md\n---\n\n"
                    "# SVM\n\n## Key equations\n\n## Takeaways for my thesis\n\n## My notes\n\nmine\n")
    monkeypatch.setattr(digest, "ROOT", str(tmp_path))
    monkeypatch.setattr(digest, "CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(digest, "sha1_file", lambda rel: "sha")
    monkeypatch.setattr(digest, "_video", lambda url: _tiny_video(tmp_path / "v.mp4"))
    monkeypatch.setattr(ed, "_resolve_raw", lambda arg: "raw/videos/svm/video.md")
    monkeypatch.setattr(ed, "existing_digest_for_raw", lambda raw: "wiki/video-svm.md")
    monkeypatch.setattr(course, "hub_row_for_raw", lambda raw: (None, None, None))
    calls = []
    monkeypatch.setattr(readers, "claude_reads", lambda frames, model, backend=None, workers=4: (
        calls.append({"frames": frames, "model": model, "backend": backend}), [dict(reads) for _ in frames])[1])
    digest.read_calls = calls
    return digest, page


def test_video_digest_reads_all_frames_in_one_run_on_the_chosen_backend(tmp_path, monkeypatch):
    digest, page = _digest_env(tmp_path, monkeypatch, {"text": "$$x$$", "tokens_in": 10, "tokens_out": 5,
                                                         "usd": 0.01, "backend": "batch"})
    digest.video_digest("raw/videos/svm/video.md", tier="full", model="haiku", backend="batch")
    (call,) = digest.read_calls
    assert call["backend"] == "batch" and call["model"] == "haiku" and len(call["frames"]) == 2
    assert all(p.endswith(".jpg") and isinstance(ctx, str) for p, ctx in call["frames"])
    stats = json.loads((tmp_path / "cache" / "sha" / "reads.json").read_text())["stats"]
    assert stats["backend"] == "batch" and stats["usd"] == 0.02 and stats["read"] == 2


def test_claude_reads_builds_image_requests(tmp_path, monkeypatch):
    from kb_distillery import llm
    from kb_distillery.ingest.sources.youtube import readers
    img = tmp_path / "f-00030.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    seen = []

    def run(reqs, backend=None, workers=4):
        seen.append((reqs, backend))
        return [llm.Result(id=reqs[0].id, text=" $$a$$ \n", usd=0.003, backend="api", model="claude-sonnet-5-5",
                           usage={"input_tokens": 1500, "output_tokens": 40}),
                llm.Result(id=reqs[1].id, error="API 400: image too large", backend="api", model="claude-sonnet-5-5")]
    monkeypatch.setattr(llm, "run", run)
    out = readers.claude_reads([(str(img), 'he says "Lagrange"'), (str(img), "")], backend="api")
    (reqs, backend), = seen
    assert backend == "api" and [r.images for r in reqs] == [(str(img),), (str(img),)]
    assert reqs[0].effort == readers.READ_EFFORT and "he says 'Lagrange'" in reqs[0].prompt
    assert "Read the image" not in reqs[0].prompt           # kb_distillery.llm attaches the image per backend
    assert out[0] == {"text": "$$a$$", "model": "claude-sonnet-5-5", "backend": "api", "tokens_in": 1500,
                      "tokens_out": 40, "usd": 0.003}
    assert out[1]["text"] == "" and out[1]["error"] == "API 400: image too large"


def test_claude_read_subscription_counts_the_turn_that_saw_the_image():
    from kb_distillery import llm
    from kb_distillery.ingest.sources.youtube import readers
    r = llm.Result(id="f0", text="ok", backend="subscription", model="claude-sonnet-5-5", usage={
        "output_tokens": 90, "iterations": [{"input_tokens": 3, "cache_creation_input_tokens": 50},
                                            {"input_tokens": 2, "cache_creation_input_tokens": 1700}]})
    assert readers._read(r)["tokens_in"] == 1702


def test_video_digest_writes_frames_and_never_downgrades_depth(tmp_path, monkeypatch):
    digest, page = _digest_env(tmp_path, monkeypatch, {"text": "$$L = \\tfrac12\\|w\\|^2 - \\sum_i \\alpha_i$$",
                                                         "tokens_in": 1000, "tokens_out": 300})
    digest.video_digest("raw/videos/svm/video.md", tier="full")
    text = page.read_text()
    assert "depth: deep" in text                                       # full over deep keeps deep
    assert text.count("### [") == 2 and "../raw/videos/svm/a-00030.jpg" in text
    assert text.index("## Frames") < text.index("## Takeaways") < text.index("## My notes") and "mine" in text
    assert "_Draft from the frame reads" in text


def test_video_digest_leaves_the_page_alone_when_no_read_succeeds(tmp_path, monkeypatch):
    digest, page = _digest_env(tmp_path, monkeypatch, {"text": "", "error": "usage limit"})
    before = page.read_text()
    with pytest.raises(ValueError, match="no frame could be read"):
        digest.video_digest("raw/videos/svm/video.md", tier="full")
    assert page.read_text() == before


def _thumbs(tmp_path, anchors, same=()):
    """Write a distinct (or, for `same`, an identical) picture per anchor; returns the anchors with paths."""
    from PIL import Image
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (90, 160), dtype=np.uint8)
    for x in anchors:
        px = base if x["t"] in same else rng.integers(0, 255, (90, 160), dtype=np.uint8)
        Image.fromarray(px).save(tmp_path / f"a-{x['t']:05d}.jpg")
        x["thumb_path"] = f"a-{x['t']:05d}.jpg"
    return anchors


def test_pick_takes_the_best_anchors_with_a_gap_and_no_repeated_picture(tmp_path):
    from kb_distillery.ingest.sources.youtube import digest
    anchors = _thumbs(tmp_path, [{"t": t, "score": s} for t, s in
                                 [(100, 9), (150, 8), (400, 7), (900, 7), (1500, 0), (2000, 6), (2600, 6)]],
                      same=(900, 2600))
    chosen = digest.pick(anchors, duration=3600, tier="full", root=str(tmp_path))
    ts = [x["t"] for x in chosen]
    assert 150 not in ts                       # 50 s after a better one: full keeps 2 min apart
    assert 1500 not in ts                      # score 0 (coverage only) is never read
    assert not (900 in ts and 2600 in ts)      # the same picture shown twice is read once
    assert ts == sorted(ts) and 100 in ts and 400 in ts


def test_frames_section_and_drafted_equations():
    from kb_distillery.ingest.sources.youtube import digest
    chosen = [{"t": 1311, "kind": "board", "thumb_path": "raw/videos/svm/a-01311.jpg",
               "read": {"text": "$$y_i(\\vec w\\cdot x_i + b) \\geq 1$$ and text\n$$\nL = \\tfrac12\\|w\\|^2\n$$"}},
              {"t": 1877, "kind": "board", "thumb_path": "raw/videos/svm/a-01877.jpg",
               "read": {"text": "$$y_i(\\bar w \\cdot x_i+b)\\ \\ge 1$$"}}]
    sec = digest.frames_section(chosen, "https://www.youtube.com/watch?v=abcdefghijk")
    assert "![0:21:51](../raw/videos/svm/a-01311.jpg)" in sec and "\n$$\ny_i(\\vec w\\cdot x_i + b) \\geq 1\n$$\n" in sec
    assert len(digest.equations(chosen)) == 2                    # \geq and \ge are one formula
    page = "# T\n\n## Key equations\n\n## Takeaways for my thesis\n\n## Links out\n- x\n"
    page = digest.put_section(page, "## Frames", sec)
    assert page.index("## Frames") < page.index("## Takeaways") and digest.section_empty(page, "## Key equations")
    again = digest.put_section(page, "## Frames", "## Frames\n\nnew\n")
    assert again.count("## Frames") == 1 and "new" in again and "a-01311" not in again


def test_force_reuses_the_videos_own_folder(tmp_path):
    d = tmp_path / "raw" / "inbox" / "video-svm-lecture"
    d.mkdir(parents=True)
    (d / "info.json").write_text(json.dumps({"id": "abcdefghijk"}))
    assert bundle.dir_name("SVM lecture", "abcdefghijk", str(tmp_path)) == "svm-lecture"
    c = tmp_path / "raw" / "videos" / "svm-2014"
    c.mkdir(parents=True)
    (c / "info.json").write_text(json.dumps({"id": "zyxwvutsrqp"}))
    assert bundle.dir_name("Other title", "zyxwvutsrqp", str(tmp_path)) == "svm-2014"   # a cataloged one


def test_subtitles_retry_after_a_rate_limit(tmp_path, monkeypatch):
    import yt_dlp
    from kb_distillery.ingest.sources.youtube import fetch
    calls, waits = [], []

    class FakeYDL:
        def __init__(self, opts): self.opts = opts
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download):
            calls.append(self.opts["subtitleslangs"])
            if len(calls) < 3:
                raise yt_dlp.utils.DownloadError("HTTP Error 429: Too Many Requests")
            (tmp_path / "abcdefghijk.en-US.vtt").write_text("WEBVTT\n")
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    info = {"subtitles": {"en-US": []}, "automatic_captions": {"en": []}}
    path = fetch.fetch_subs("abcdefghijk", info, str(tmp_path), waits=(0, 1, 2, 3), sleep=waits.append)
    assert path.endswith(".en-US.vtt") and calls == [["en-US"]] * 3 and waits == [1, 2]


def test_parse_vtt_auto_without_word_tags():
    rolling = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello\n\n00:00:02.000 --> 00:00:04.000\nhello\nworld\n"
    assert [t for _, t in tr.parse_vtt(rolling, auto=True)] == ["hello", "world"]


def test_resolve_prints_a_bundle_without_a_page():
    from kb_distillery.ingest.resolve import ResolveResult, format_human
    text = format_human(ResolveResult(status="found", matches=[{"slug": None, "raw": "raw/videos/x/video.md",
                                                                "reason": "youtube:abcdefghijk"}], query="q"))
    assert "wiki/None" not in text and "(no page yet)" in text
