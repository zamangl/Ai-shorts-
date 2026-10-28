---
 title: Free AI Shorts Studio
 emoji: 🎬
 colorFrom: blue
 colorTo: purple
 sdk: docker
 app_port: 7860
---

# Free AI Shorts Studio (prototype)

A small Streamlit app for turning a user-owned long video into vertical candidate clips with automatic speech captions.

## What it does
- Accepts video files from 2 to 60 minutes (MP4, MOV, MKV, WEBM)
- Uses Faster-Whisper on CPU for transcription
- Creates candidate clips around scene changes / regular intervals
- Optionally crops to 9:16, burns captions, and applies light visual cleanup
- Lets the user preview and download each clip

## Important limitations
- This is a working prototype, not a full commercial AI editor.
- It does **not** guarantee viral clips or copyright-free output. Use only footage/audio you own or are licensed to use.
- Scene-change detection is a heuristic; it does not understand which moments are most engaging.
- The enhancement toggle is a mild SDR filter, not real HDR conversion or AI upscaling.
- Free hosting has CPU, memory, storage, and execution-time limits. Long videos can fail or take a long time.
- Uploaded files are written to the app's temporary `work/` directory. On hosted free Spaces, storage may be ephemeral. Do not upload sensitive videos.

## Run locally
Install Python 3.10 or 3.11 and FFmpeg, then:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy free on Hugging Face Spaces
1. Create or sign in at https://huggingface.co/
2. Choose **New Space**.
3. Select **Docker** as the SDK, choose a CPU free hardware option if available, and create the Space.
4. Upload `app.py`, `requirements.txt`, `Dockerfile`, and this README.
5. Wait for the build to finish and open the Space URL.

Free hardware and quotas can change. If your Space is sleeping or exceeds CPU/RAM/time limits, processing may stop. The app does not require a paid API key.

## Copyright risk
No software can promise a 99% or 100% absence of claims. Content ID can detect copyrighted audio/video even after edits. The safest workflow is to use original recordings, permissioned footage, and music with a license covering your platform and monetization.
