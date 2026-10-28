import os
import re
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).parent
WORK_DIR = APP_DIR / "work"
WORK_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="Free AI Shorts Studio", page_icon="🎬", layout="wide")

st.title("🎬 Free AI Shorts Studio")
st.caption("Upload a video, find candidate highlights, add captions, and export vertical clips.")

st.warning(
    "Copyright note: this app cannot guarantee that a video is copyright-free or prevent claims. "
    "Use videos you own or have permission to edit, and use licensed music. Cropping, captions, "
    "filters, or changing audio do not remove copyright."
)

def have_ffmpeg():
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True)

def probe_duration(path):
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ])
    return float(out.stdout.strip())

def transcribe(path, model_name="tiny", language=None):
    # Loaded only when user starts transcription to keep app startup light.
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    kwargs = {}
    if language and language != "Auto detect":
        kwargs["language"] = {"English": "en", "Urdu": "ur", "Hindi": "hi", "Spanish": "es",
                              "Arabic": "ar", "French": "fr"}[language]
    segments, info = model.transcribe(str(path), vad_filter=True, **kwargs)
    result = []
    for s in segments:
        text = (s.text or "").strip()
        if text:
            result.append({"start": float(s.start), "end": float(s.end), "text": text})
    return result, getattr(info, "language", None)

def srt_time(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def write_srt(segments, start, end, out_path):
    lines, idx = [], 1
    for seg in segments:
        a, b = max(seg["start"], start), min(seg["end"], end)
        if b <= a:
            continue
        text = re.sub(r"\s+", " ", seg["text"]).strip()
        lines += [str(idx), f"{srt_time(a-start)} --> {srt_time(b-start)}", text, ""]
        idx += 1
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")

def detect_scenes(path):
    # Scene-change timestamps are only candidate boundaries, not a guarantee of interesting content.
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(path), "-vf",
        "select='gt(scene,0.30)',showinfo", "-an", "-f", "null", "-"
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    times = []
    for line in p.stderr.splitlines():
        if "pts_time:" in line:
            try:
                times.append(float(line.split("pts_time:")[1].split()[0]))
            except Exception:
                pass
    return sorted(set(times))

def build_candidates(duration, scenes, clip_len, max_clips):
    # Use scene changes near regular target intervals; if none exist, use regular intervals.
    candidates = []
    target = clip_len
    while target < duration and len(candidates) < max_clips * 3:
        nearby = [x for x in scenes if abs(x - target) <= clip_len * 0.45 and x > 0]
        start = max(0, (min(nearby, key=lambda x: abs(x-target)) if nearby else target) - clip_len * 0.35)
        end = min(duration, start + clip_len)
        if end - start >= min(clip_len, 10):
            candidates.append((start, end))
        target += clip_len * 0.8
    if not candidates and duration > 0:
        step = max(clip_len, duration / max(1, max_clips))
        t = 0
        while t < duration and len(candidates) < max_clips:
            candidates.append((t, min(duration, t + clip_len)))
            t += step
    # De-duplicate near-identical candidates
    unique = []
    for c in candidates:
        if not any(abs(c[0]-u[0]) < 3 for u in unique):
            unique.append(c)
    return unique[:max_clips]

def export_clip(src, start, end, out_mp4, srt_file=None, vertical=True, enhance=False):
    duration = max(0.1, end-start)
    vf = []
    if vertical:
        # Center crop to 9:16. This is a simple center crop, not face tracking.
        vf.append("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
    if enhance:
        vf.append("hqdn3d=1.5:1.5:6:6,eq=contrast=1.04:saturation=1.05,unsharp=5:5:0.5:3:3:0.0")
    if srt_file and Path(srt_file).exists() and Path(srt_file).stat().st_size:
        # FFmpeg subtitles filter needs escaped path. Use a simple temporary directory path.
        sub = str(Path(srt_file).resolve()).replace("\\", "/").replace(":", r"\:")
        vf.append(f"subtitles='{sub}':force_style='FontSize=20,Outline=2,Shadow=1,Alignment=2,MarginV=100'")
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(src), "-t", str(duration),
           "-vf", ",".join(vf) if vf else "null", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "22", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_mp4)]
    run(cmd)

if not have_ffmpeg():
    st.error("FFmpeg/FFprobe were not found. The Hugging Face Space configuration in README installs them.")
    st.stop()

uploaded = st.file_uploader("Upload your own video (MP4, MOV, MKV, WEBM)", type=["mp4", "mov", "mkv", "webm"])
col1, col2, col3 = st.columns(3)
with col1:
    clip_len = st.selectbox("Short length", [15, 30, 45, 60, 90], index=1)
with col2:
    max_clips = st.slider("Maximum clips to create", 1, 10, 5)
with col3:
    model_name = st.selectbox("Caption model (CPU)", ["tiny", "base", "small"], index=0)

language = st.selectbox("Spoken language", ["Auto detect", "English", "Urdu", "Hindi", "Spanish", "Arabic", "French"])
vertical = st.checkbox("Export vertical 9:16", value=True)
burn_captions = st.checkbox("Burn captions into each clip", value=True)
enhance = st.checkbox("Light visual enhancement (not true HDR)", value=False)

if uploaded:
    suffix = Path(uploaded.name).suffix.lower() or ".mp4"
    src = WORK_DIR / ("uploaded_video" + suffix)
    src.write_bytes(uploaded.getvalue())
    try:
        duration = probe_duration(src)
    except Exception:
        st.error("Could not read this video. Try a standard MP4 file.")
        st.stop()

    st.info(f"Video duration: {duration/60:.1f} minutes")
    if duration < 120 or duration > 3600:
        st.error("Please upload a video between 2 minutes and 60 minutes.")
        st.stop()

    if st.button("✨ Analyze video and create Shorts", type="primary"):
        with st.spinner("Transcribing audio for captions… This can take a while on free CPU hosting."):
            try:
                segments, detected_lang = transcribe(src, model_name, language)
                st.session_state["segments"] = segments
                st.session_state["detected_lang"] = detected_lang
            except Exception as e:
                st.error("Transcription failed. Try the tiny model or a shorter video. Details: " + str(e))
                st.stop()

        with st.spinner("Finding scene changes and preparing candidate clips…"):
            scenes = detect_scenes(src)
            candidates = build_candidates(duration, scenes, int(clip_len), int(max_clips))
            out_dir = WORK_DIR / "exports"
            out_dir.mkdir(exist_ok=True)
            exports = []
            progress = st.progress(0)
            for i, (start, end) in enumerate(candidates, 1):
                srt_path = out_dir / f"clip_{i:02}.srt"
                if burn_captions:
                    write_srt(segments, start, end, srt_path)
                else:
                    srt_path = None
                mp4 = out_dir / f"short_{i:02}.mp4"
                try:
                    export_clip(src, start, end, mp4, srt_path, vertical, enhance)
                    exports.append({"path": str(mp4), "start": start, "end": end})
                except Exception as e:
                    st.warning(f"Clip {i} failed: {e}")
                progress.progress(i / len(candidates))
            st.session_state["exports"] = exports
            st.session_state["source_name"] = uploaded.name
        st.success(f"Finished: created {len(exports)} clip(s).")

if "exports" in st.session_state and st.session_state["exports"]:
    st.subheader("Your Shorts")
    for i, item in enumerate(st.session_state["exports"], 1):
        p = Path(item["path"])
        if p.exists():
            st.markdown(f"**Clip {i}** — {item['start']:.1f}s to {item['end']:.1f}s")
            st.video(str(p))
            st.download_button(f"Download clip {i}", data=p.read_bytes(), file_name=p.name, mime="video/mp4", key=f"dl_{i}")

st.caption("Prototype note: candidate clips are scene/interval-based, not semantic viral-moment ranking. Free CPU hosting may time out on long videos. HDR conversion is not included; the enhancement toggle is a light SDR filter only.")
