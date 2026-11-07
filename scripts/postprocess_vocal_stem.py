from __future__ import annotations

import io
import math
from pathlib import Path
import wave
import numpy as np
import noisereduce as nr
import scipy.signal

def process_vocal_stem(
    input_wav: Path,
    output_dir: Path,
    prefix: str = "kurisu_dub",
    min_segment_sec: float = 2.0,
    max_segment_sec: float = 12.0,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 65)
    print("VOCAL STEM POST-PROCESSING & NOISE / ECHO REDUCTION")
    print(f"Input: {input_wav}")
    print(f"Output: {output_dir}")
    print("=" * 65)

    with wave.open(str(input_wav), "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        frames = wf.readframes(n_frames)

    # Convert to float32 mono
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)

    print(f"Loaded: {len(audio) / sr:.2f}s audio at {sr} Hz.")

    # 1. Spectral Denoising (remove room echo and background hiss)
    print("Applying spectral noise reduction...")
    cleaned = nr.reduce_noise(
        y=audio,
        sr=sr,
        stationary=False,
        prop_decrease=0.85,
        n_fft=1024,
        win_length=1024,
        hop_length=512,
    )

    # 2. Bandpass filtering (85 Hz to 8000 Hz)
    print("Applying voice bandpass filter (85 Hz - 8000 Hz)...")
    sos = scipy.signal.butter(4, [85, min(8000, sr // 2 - 500)], btype="bandpass", fs=sr, output="sos")
    filtered = scipy.signal.sosfilt(sos, cleaned)

    # 3. Peak normalization
    max_val = np.max(np.abs(filtered))
    if max_val > 1e-4:
        filtered = filtered / max_val * 0.95

    # 4. Voice Activity Detection & Segmentation by Silence
    # Calculate RMS in 50ms windows
    win_size = int(sr * 0.05)
    hop_size = int(sr * 0.025)
    num_windows = (len(filtered) - win_size) // hop_size
    rms = np.zeros(num_windows)
    for i in range(num_windows):
        start = i * hop_size
        rms[i] = np.sqrt(np.mean(filtered[start : start + win_size] ** 2))

    silence_thresh = max(0.015, np.percentile(rms, 35))
    is_speech = rms > silence_thresh

    # Group into speech segments
    segments: list[tuple[int, int]] = []
    in_seg = False
    seg_start = 0
    silence_count = 0
    max_silence_hops = int(0.4 / 0.025)  # 400ms pause separates sentences

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

    # Filter segments by duration
    saved_files: list[Path] = []
    idx = 1
    for s_start, s_end in segments:
        dur = (s_end - s_start) / sr
        if dur < min_segment_sec:
            continue
        # Split overly long segments if necessary
        chunk_starts = range(s_start, s_end, int(sr * max_segment_sec))
        for c_start in chunk_starts:
            c_end = min(s_end, c_start + int(sr * max_segment_sec))
            c_dur = (c_end - c_start) / sr
            if c_dur < min_segment_sec:
                continue

            chunk = filtered[c_start:c_end]
            # Fade in and fade out 20ms to prevent clicks
            fade_len = int(sr * 0.02)
            if len(chunk) > 2 * fade_len:
                chunk[:fade_len] *= np.linspace(0, 1, fade_len)
                chunk[-fade_len:] *= np.linspace(1, 0, fade_len)

            out_pcm = (chunk * 32767.0).astype(np.int16).tobytes()
            target_wav = output_dir / f"{prefix}_{idx:03d}.wav"
            with wave.open(str(target_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(out_pcm)

            print(f"  Segment [{idx:03d}] {c_dur:.2f}s -> {target_wav.name}")
            saved_files.append(target_wav)
            idx += 1

    total_clean_dur = sum((Path(f).stat().st_size - 44) / (sr * 2) for f in saved_files)
    print("=" * 65)
    print(f"Processed: {len(saved_files)} clean vocal clips ({total_clean_dur:.2f}s / {total_clean_dur/60.0:.2f} min)")
    print("=" * 65)
    return saved_files

if __name__ == "__main__":
    stem_wav = Path("temp_stems/htdemucs/VOZ DE KURISU MAKISE - ESPAÑOL LATINO STEINS;GATE/vocals.wav")
    target_dir = Path("dataset/kurisu_latin_dub/wavs")
    process_vocal_stem(stem_wav, target_dir)
