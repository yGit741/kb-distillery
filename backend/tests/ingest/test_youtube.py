"""scrap-youtube: transcript parsing, sections, comment filter, frame selection, bundle wiring (offline)."""
import json
import os

import numpy as np
import pytest

from kb.core.schema import unit_slug_for_raw, unit_type_for_raw
from kb.ingest.youtube import bundle, frames as fx, transcript as tr
from kb.ingest.youtube.fetch import pick_subs, video_id

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


def test_budget_shares_frames_over_sections():
    secs = [{"start": 0, "end": 1800}, {"start": 1800, "end": 3600}]
    frames = [{"t": t, "score": t % 7} for t in range(0, 3600, 60)]
    out = fx.budget(frames, secs, per_hour=10, duration=3600)
    assert len(out) == 10
    assert sum(f["t"] < 1800 for f in out) == 5


def test_pick_vibe_one_per_third():
    scored = [{"t": t, "score": s} for t, s in [(10, 1), (20, 9), (40, 0), (70, 3), (80, 5)]]
    assert [p["t"] for p in fx.pick_vibe(scored, 90)] == [20, 80]


def test_mode_of():
    assert fx.mode_of({"board": np.array([0.6] * 7 + [0.0] * 3)}) == "board"
    assert fx.mode_of({"board": np.array([0.0] * 9 + [0.6])}) == "slides"


# --- bundle and vault wiring --------------------------------------------------------------------

META = {"id": "abcdefghijk", "title": "Lecture 16: SVM", "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "channel": "MIT", "duration": 600, "uploaded": "2014-01-10", "description": "See https://ocw.mit.edu",
        "chapters": [{"title": "Intro", "start": 0, "end": 300}], "subs_kind": "manual", "tier": "frames"}


def test_render_md_puts_frames_in_their_section():
    secs = [{"chapter": "Intro", "start": 0, "end": 300, "text": "Hello."},
            {"chapter": "Intro", "start": 300, "end": 600, "text": "Lagrange."}]
    frames = [{"t": 400, "file": "frame-00400.jpg", "kind": "board", "ocr": ["L = 1/2 w"],
               "read": {"text": "$$L = \\tfrac12\\|w\\|^2$$"}}]
    md = bundle.render_md(META, secs, frames, [])
    assert md.startswith("---\ntitle: \"Lecture 16: SVM\"")
    assert md.index("Lagrange.") < md.index("frame-00400.jpg") and "$$L" in md
    assert "## Intro" in md and md.count("## Intro") == 1 and "## Chapters" in md


def test_abstract_reads_the_bundle_data(tmp_path):
    d = {**META, "sections": [{"chapter": "Intro", "start": 0, "end": 600, "text": " ".join(["w"] * 2000)}],
         "frames": [{"t": 5, "ocr": ["SUPPORT VECTOR MACHINES"]}]}
    (tmp_path / "video.json").write_text(json.dumps(d))
    text = bundle.abstract(str(tmp_path / "video.md"))
    assert "Title: Lecture 16: SVM" in text and "SUPPORT VECTOR MACHINES" in text and "[…]" in text


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
    from kb.lint.lint import asset_source
    on_disk = {"raw/videos/svm/video.md", "raw/videos/svm/frame-00042.jpg", "raw/videos/svm/video.json"}
    assert asset_source("raw/videos/svm/frame-00042.jpg", on_disk) == "raw/videos/svm/video.md"
    assert asset_source("raw/videos/svm/video.json", on_disk) == "raw/videos/svm/video.md"
    assert asset_source("raw/videos/svm/video.md", on_disk) is None
    assert asset_source("raw/videos/other/frame-1.jpg", on_disk) is None


def test_catalog_detects_a_video_bundle(tmp_path, monkeypatch):
    from kb.ingest import catalog
    d = tmp_path / "raw" / "inbox" / "video-svm"
    d.mkdir(parents=True)
    monkeypatch.setattr(catalog, "ROOT", str(tmp_path))
    with pytest.raises(ValueError):
        catalog.detect_format("raw/inbox/video-svm")          # no video.md yet: not a bundle
    (d / "video.md").write_text("# SVM\n")
    assert catalog.detect_format("raw/inbox/video-svm") == "videos"


def test_ops_target_of_a_video_bundle_is_its_folder():
    from kb.ops.wrap import _target
    assert _target(["raw/inbox/video-svm/frame-00042.jpg", "raw/inbox/video-svm/video.md"], ["scrap-youtube"]) == "svm"


def test_budget_keeps_frames_without_sections_and_before_the_first_caption():
    frames = [{"t": t, "score": 1} for t in range(0, 3600, 60)]
    assert len(fx.budget(frames, [], per_hour=30, duration=3600)) == 30          # no transcript
    secs = [{"start": 100, "end": 3600}]
    out = fx.budget(frames, secs, per_hour=30, duration=3600)
    assert len(out) == 30


def test_budget_over_many_short_sections_keeps_the_best_across_the_video():
    secs = [{"start": i * 90, "end": (i + 1) * 90} for i in range(40)]
    frames = [{"t": i * 90 + 10, "score": i % 4} for i in range(40)]
    out = fx.budget(frames, secs, per_hour=10, duration=3600)
    assert len(out) == 10 and max(f["t"] for f in out) > 1800 and all(f["score"] == 3 for f in out)


def test_force_reuses_the_videos_own_inbox_folder(tmp_path):
    d = tmp_path / "raw" / "inbox" / "video-svm-lecture"
    d.mkdir(parents=True)
    (d / "info.json").write_text(json.dumps({"id": "abcdefghijk"}))
    assert bundle.dir_name("SVM lecture", "abcdefghijk", str(tmp_path)) == "svm-lecture"


def test_parse_vtt_auto_without_word_tags():
    rolling = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nhello\n\n00:00:02.000 --> 00:00:04.000\nhello\nworld\n"
    assert [t for _, t in tr.parse_vtt(rolling, auto=True)] == ["hello", "world"]


def test_resolve_prints_a_bundle_without_a_page():
    from kb.ingest.resolve import ResolveResult, format_human
    text = format_human(ResolveResult(status="found", matches=[{"slug": None, "raw": "raw/videos/x/video.md",
                                                                "reason": "youtube:abcdefghijk"}], query="q"))
    assert "wiki/None" not in text and "(no page yet)" in text
