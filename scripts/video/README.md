# Intro video (30 s, 3840x2160)

Rebuild with an isolated virtualenv (these tools are not app dependencies):

    python -m venv .vvenv && .vvenv/Scripts/pip install -r requirements.txt
    .vvenv/Scripts/python narration.py WORK_DIR       # Indian-English neural TTS (edge-tts), timing + lip-sync data
    .vvenv/Scripts/python render_intro.py WORK_DIR OUT_DIR

* The presenter is an **illustrated character**, not a real person; the match score, chips and certificate shown
  are illustrations (the certificate is labelled SAMPLE).
* Narration uses the free, unofficial Microsoft Edge online TTS via `edge-tts`; only the script text in
  `narration.py` is sent. It needs internet and may change without notice.
* Output files go to `frontend/public/video/` (1080p for the page, 4K for download, poster, captions).
