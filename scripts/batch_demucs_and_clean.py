from __future__ import annotations

import glob
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import wave
import av
import numpy as np
import noisereduce as nr
import scipy.signal

def convert_to_wav(input_path: Path, output_wav: Path) -> bool:
    try:
        container = av.open(str(input_path))
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="s16", layout="stereo", rate=44100)
        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            for frame in container.decode(stream):
                for rf in resampler.resample(frame):
                    wf.writeframes(rf.to_ndarray().tobytes())
        output_wav.write_bytes(out_buf.getvalue())
        return True
    except Exception as exc:
        print(f"Error converting {input_path} to wav: {exc}")
        return False

def clean_and_slice_vocal_wav(
    vocal_wav: Path,
    output_dir: Path,
    prefix: str,
    min_dur: float = 1.8,
    max_dur: float = 12.0,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with wave.open(str(vocal_wav), "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)

    # Spectral noise reduction
    cleaned = nr.reduce_noise(
        y=audio,
        sr=sr,
        stationary=False,
        prop_decrease=0.85,
        n_fft=1024,
        win_length=1024,
        hop_length=512,
    )

    # Bandpass 85Hz - 8000Hz
    sos = scipy.signal.butter(4, [85, min(8000, sr // 2 - 500)], btype="bandpass", fs=sr, output="sos")
    filtered = scipy.signal.sosfilt(sos, cleaned)

    # Normalize
    max_v = np.max(np.abs(filtered))
    if max_v > 1e-4:
        filtered = filtered / max_v * 0.95

    # VAD segmentation
    win_size = int(sr * 0.05)
    hop_size = int(sr * 0.025)
    num_windows = (len(filtered) - win_size) // hop_size
    rms = np.zeros(num_windows)
    for i in range(num_windows):
        start = i * hop_size
        rms[i] = np.sqrt(np.mean(filtered[start : start + win_size] ** 2))

    silence_thresh = max(0.015, np.percentile(rms, 35))
    is_speech = rms > silence_thresh

    segments: list[tuple[int, int]] = []
    in_seg = False
    seg_start = 0
    silence_count = 0
    max_silence_hops = int(0.4 / 0.025)

    for i, active in enumerate(is_speech):
        if active:
            if not in_seg:
                in_seg = True
                seg_start = max(0, i * hop_size - int(sr * 0.1))
            silence_count = 0
        else:
            if in_seg:
                silence_count += 1
                if silence_count >= max_silence_hops:
                    seg_end = min(len(filtered), (i - silence_count) * hop_size + int(sr * 0.15))
                    segments.append((seg_start, seg_end))
                    in_seg = False
                    silence_count = 0

    if in_seg:
        segments.append((seg_start, len(filtered)))

    saved_files: list[Path] = []
    idx = 1
    for s_start, s_end in segments:
        dur = (s_end - s_start) / sr
        if dur < min_dur:
            continue
        chunk_starts = range(s_start, s_end, int(sr * max_dur))
        for c_start in chunk_starts:
            c_end = min(s_end, c_start + int(sr * max_dur))
            c_dur = (c_end - c_start) / sr
            if c_dur < min_dur:
                continue

            chunk = filtered[c_start:c_end]
            fade_len = int(sr * 0.02)
            if len(chunk) > 2 * fade_len:
                chunk[:fade_len] *= np.linspace(0, 1, fade_len)
                chunk[-fade_len:] *= np.linspace(1, 0, fade_len)

            out_pcm = (chunk * 32767.0).astype(np.int16).tobytes()
            target_wav = output_dir / f"{prefix}_{idx:03d}.wav"
            with wave.open(str(target_wav), "wb") as out_wf:
                out_wf.setnchannels(1)
                out_wf.setsampwidth(2)
                out_wf.setframerate(sr)
                out_wf.writeframes(out_pcm)
            saved_files.append(target_wav)
            idx += 1

    return saved_files

def main() -> None:
    raw_dir = Path("temp_downloads")
    stems_dir = Path("temp_stems/batch")
    clean_wavs_dir = Path("dataset/kurisu_latin_dub/wavs")
    stems_dir.mkdir(parents=True, exist_ok=True)
    clean_wavs_dir.mkdir(parents=True, exist_ok=True)

    input_files = list(raw_dir.glob("*.webm")) + list(raw_dir.glob("*.m4a")) + list(raw_dir.glob("*.mp3"))
    print(f"Found {len(input_files)} raw files to isolate and clean.")

    for i, file_path in enumerate(input_files, 1):
        print("=" * 65)
        print(f"[{i}/{len(input_files)}] Processing: {file_path.name}")
        wav_intermediate = stems_dir / f"input_{i}.wav"
        if not wav_intermediate.exists():
            print("  Converting to PCM WAV...")
            if not convert_to_wav(file_path, wav_intermediate):
                continue

        # Demucs separation
        target_vocal_wav = stems_dir / "htdemucs" / f"input_{i}" / "vocals.wav"
        if not target_vocal_wav.exists():
            print("  Running Demucs vocal stem isolation on CUDA...")
            cmd = [
                sys.executable,
                "-m",
                "demucs.separate",
                "-n",
                "htdemucs",
                "--two-stems",
                "vocals",
                "-d",
                "cuda",
                "-o",
                str(stems_dir),
                str(wav_intermediate),
            ]
            subprocess.run(cmd, check=True)

        if target_vocal_wav.exists():
            print("  Post-processing and noise-reducing vocal stem...")
            prefix = f"kurisu_raw_{i}"
            slices = clean_and_slice_vocal_wav(target_vocal_wav, clean_wavs_dir, prefix=prefix)
            print(f"  Extracted {len(slices)} clean speech clips.")

    # Measure total dataset
    all_clean = list(clean_wavs_dir.glob("*.wav"))
    total_dur = 0.0
    for w in all_clean:
        with wave.open(str(w), "rb") as wf:
            total_dur += wf.getnframes() / float(wf.getframerate())

    print("=" * 65)
    print(f"BATCH CLEANING COMPLETE!")
    print(f"Total Vocal Clips: {len(all_clean)}")
    print(f"Total Clean Duration: {total_dur:.2f}s ({total_dur / 60.0:.2f} minutes)")
    print(f"Directory: {clean_wavs_dir}")
    print("=" * 65)

if __name__ == "__main__":
    main()
