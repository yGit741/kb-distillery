"""yt-dlp download into .cache/youtube/<id>/ (0 LLM): metadata, subtitles, comments, the video."""
import glob
import os
import re
import sys

from ..paths import ROOT

CACHE = os.path.join(ROOT, ".cache", "youtube")
SUB_LANGS = ("en", "en-US", "en-GB", "en-orig")
AUTO_LANGS = ("en-orig", "en", "en-US", "en-GB")    # auto captions: the original ASR track first
_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})")
# what info.json keeps: enough to rebuild video.md, nothing per-format
INFO_KEYS = ("id", "title", "channel", "uploader", "upload_date", "duration", "description", "chapters",
             "webpage_url", "tags", "comment_count", "view_count", "channel_url")


def video_id(url):
    """`https://www.youtube.com/watch?v=Ub3GoFaUcds&list=…` → `Ub3GoFaUcds`."""
    m = _ID.search(url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    raise ValueError(f"not a YouTube video URL: {url}")


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class Fetched:
    def __init__(self, vid, folder, info, subs, subs_kind, mp4):
        self.id, self.folder, self.info, self.subs, self.subs_kind, self.mp4 = vid, folder, info, subs, subs_kind, mp4


def pick_subs(folder, vid, info):
    """The transcript file: a manual track first (punctuated, accurate), then auto captions."""
    manual = set((info.get("subtitles") or {}).keys())
    files = {os.path.basename(p)[len(vid) + 1:-4]: p for p in glob.glob(os.path.join(folder, f"{vid}.*.vtt"))}
    for lang in SUB_LANGS:
        if lang in files and lang in manual:
            return files[lang], "manual"
    for lang in AUTO_LANGS:                        # the order wanted_track fetches in
        if lang in files:
            return files[lang], "auto"
    return None, None


SUB_WAITS = (0, 30, 90, 180, 300)       # seconds before each subtitle attempt: YouTube answers bursts with 429


def _base_opts(folder):
    return {"outtmpl": os.path.join(folder, "%(id)s.%(ext)s"), "noplaylist": True,
            "retries": 5, "extractor_retries": 3, "quiet": True, "no_warnings": True, "noprogress": True}


def wanted_track(info):
    """(lang, manual?) of the one English track to fetch: a manual track first, then auto captions."""
    manual, auto = info.get("subtitles") or {}, info.get("automatic_captions") or {}
    for lang in SUB_LANGS:
        if lang in manual:
            return lang, True
    for lang in AUTO_LANGS:
        if lang in auto:
            return lang, False
    return None, None


def fetch_subs(vid, info, folder, waits=SUB_WAITS, sleep=None):
    """Download only the chosen English track, retrying with backoff on HTTP 429. Returns its path or None."""
    import time
    import yt_dlp
    lang, manual = wanted_track(info)
    if not lang:
        return None
    path = os.path.join(folder, f"{vid}.{lang}.vtt")
    if os.path.isfile(path):
        return path
    opts = {**_base_opts(folder), "skip_download": True, "subtitlesformat": "vtt", "subtitleslangs": [lang],
            "writesubtitles": manual, "writeautomaticsub": not manual}
    last = None
    for wait in waits:
        if wait:
            print(f"subtitles rate-limited — retrying in {wait}s", file=sys.stderr)
            (sleep or time.sleep)(wait)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True)
        except yt_dlp.utils.DownloadError as e:
            last = e
            if "429" not in str(e) and "Too Many Requests" not in str(e):
                break                                      # not a rate limit: waiting will not help
            continue
        if os.path.isfile(path):
            return path
    raise RuntimeError(f"subtitles for {vid} could not be downloaded after {len(waits)} tries ({last}) — "
                       "the video is cached, rerun later")


def fetch(url, video=True, comments=True, cache=CACHE, subs=True):
    """Video, metadata and comments first, then the one English subtitle track (with backoff). Reruns reuse
    the cache: yt-dlp skips files already there."""
    import yt_dlp
    vid = video_id(url)
    folder = os.path.join(cache, vid)
    os.makedirs(folder, exist_ok=True)
    opts = {**_base_opts(folder),
            "skip_download": not video,
            "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/b",
            "merge_output_format": "mp4",
            "ffmpeg_location": ffmpeg_exe(),
            "getcomments": comments,
            "extractor_args": {"youtube": {"max_comments": ["40", "all", "0"], "comment_sort": ["top"]}}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.sanitize_info(ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True))
    if subs:
        fetch_subs(vid, info, folder)
    subs, kind = pick_subs(folder, vid, info)
    videos = [p for p in glob.glob(os.path.join(folder, f"{vid}.*"))
              if os.path.splitext(p)[1] in (".mp4", ".webm", ".mkv", ".mov")]   # a non-merged format keeps its own
    videos.sort(key=lambda p: not p.endswith(".mp4"))
    return Fetched(vid, folder, info, subs, kind, videos[0] if videos else None)


def has_english(info):
    """YouTube lists an English track (manual or auto) for this video."""
    tracks = set((info.get("subtitles") or {}).keys()) | set((info.get("automatic_captions") or {}).keys())
    return bool(tracks & set(SUB_LANGS))


def slim_info(info):
    return {k: info[k] for k in INFO_KEYS if info.get(k) is not None}
