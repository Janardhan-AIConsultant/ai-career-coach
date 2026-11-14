"""Narration for the 30 second intro video: synthesises each line with Indian-English neural TTS (edge-tts),
decodes to WAV, and records per-line timing plus a mouth-openness envelope for lip-flap animation.

Only the script text below is sent to the TTS service. Output goes to a work directory.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import wave
from pathlib import Path

import edge_tts
import imageio_ffmpeg
import numpy as np

VOICE = "en-IN-NeerjaNeural"
RATE = "+14%"
LINES = [
    "Hi! I am your AI Career Coach guide.",
    "Paste your resume and a job description, and see your match score and skill gaps in minutes.",
    "Then follow a seven, fifteen, or sixty day roadmap, made just for you.",
    "Practise mock interviews, and ask the coach about your own documents.",
    "Pass assessments to earn certificates you can share and verify.",
    "Start free today. Your next job begins here.",
]


async def synth(work: Path, rate: str) -> None:
    for i, text in enumerate(LINES):
        await edge_tts.Communicate(text, VOICE, rate=rate).save(str(work / f"line{i}.mp3"))


def main(work: Path, rate: str = RATE) -> None:
    work.mkdir(parents=True, exist_ok=True)
    asyncio.run(synth(work, rate))
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    info = []
    for i, text in enumerate(LINES):
        wav = work / f"line{i}.wav"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(work / f"line{i}.mp3"), "-ar", "44100", "-ac", "1", str(wav)], check=True)
        with wave.open(str(wav)) as w:
            n, sr = w.getnframes(), w.getframerate()
            pcm = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
        hop = sr // 60  # 60 envelope samples per second
        env = [float(np.sqrt(np.mean(pcm[j:j + hop] ** 2))) for j in range(0, len(pcm), hop)]
        peak = max(env) or 1.0
        info.append({"text": text, "duration": n / sr, "env": [round(min(1.0, e / peak * 1.4), 3) for e in env]})
    (work / "timing.json").write_text(json.dumps(info), encoding="utf-8")
    print("durations:", [round(i["duration"], 2) for i in info], "sum", round(sum(i["duration"] for i in info), 2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else RATE)
