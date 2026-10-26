"""yt-dlp download into .cache/youtube/<id>/ (0 LLM): metadata, subtitles, comments, the video."""
import glob
import os
import re

from ..paths import ROOT

CACHE = os.path.join(ROOT, ".cache", "youtube")
SUB_LANGS = ("en", "en-US", "en-GB", "en-orig")
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
    for lang in SUB_LANGS:
        if lang in files:
            return files[lang], "auto"
    return None, None


def fetch(url, video=True, comments=True, cache=CACHE):
    """Download what a tier needs. Reruns reuse the cache (yt-dlp skips files already there)."""
    import yt_dlp
    vid = video_id(url)
    folder = os.path.join(cache, vid)
    os.makedirs(folder, exist_ok=True)
    opts = {
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "writesubtitles": True, "writeautomaticsub": True,
        "subtitleslangs": list(SUB_LANGS), "subtitlesformat": "vtt",
        "skip_download": not video,
        "format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_exe(),
        "getcomments": comments,
        "extractor_args": {"youtube": {"max_comments": ["40", "all", "0"], "comment_sort": ["top"]}},
        "sleep_interval_subtitles": 5,          # YouTube answers fast subtitle pulls with HTTP 429
        "quiet": True, "no_warnings": True, "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.sanitize_info(ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True))
    subs, kind = pick_subs(folder, vid, info)
    mp4 = os.path.join(folder, f"{vid}.mp4")
    return Fetched(vid, folder, info, subs, kind, mp4 if os.path.isfile(mp4) else None)


def slim_info(info):
    return {k: info[k] for k in INFO_KEYS if info.get(k) is not None}
