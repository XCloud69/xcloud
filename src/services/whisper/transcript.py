import sys
import numpy as np
from faster_whisper import WhisperModel
import subprocess
import time
from .configuration import device, model_path, sample_rate, save_path

model = WhisperModel(model_path, device=device)


async def transcribe_audio(audio_bytes: bytes):
    begin = time.perf_counter()

    process = subprocess.Popen(
        [
            "ffmpeg", "-loglevel", "quiet",
            "-i", "pipe:0",
            "-ar", str(sample_rate),
            "-ac", "1",
            "-f", "s16le", "-",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    pcm_bytes, _ = process.communicate(input=audio_bytes)
    audio_data = np.frombuffer(
        pcm_bytes, np.int16).astype(np.float32) / 32768.0

    segments_iter, info = model.transcribe(audio_data, beam_size=1)

    full_transcript = []
    for s in segments_iter:
        line = f"({s.start:.2f}s → {s.end:.2f}s) {s.text}"
        print(line)
        full_transcript.append(line)

    final = time.perf_counter()
    print(f"Execution time: {(final - begin) / 60:.2f} minutes")

    return "\n".join(full_transcript)


if __name__ == "__main__":
    import os

    if len(sys.argv) < 2:
        print("Usage: python -m services.whisper.transcript <audio_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    with open(filepath, "rb") as f:
        audio_bytes = f.read()

    import asyncio
    transcript = asyncio.run(transcribe_audio(audio_bytes))

    out_file = os.path.join(save_path, os.path.splitext(os.path.basename(filepath))[0] + ".txt")
    with open(out_file, "w") as f:
        f.write(transcript)
    print(f"Saved: {out_file}")
