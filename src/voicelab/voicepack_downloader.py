from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import sys
import zipfile
import httpx

from amadeus.config import AmadeusSettings, get_default_data_dir


def download_voicepack(
    repo_id: str = "zecto/amadeus-kurisu-voicepack",
    target_dir: Path | None = None,
    hf_token: str = "",
) -> bool:
    target = target_dir or (get_default_data_dir() / "models" / "rvc")
    target.mkdir(parents=True, exist_ok=True)
    pth_file = target / "kurisu.pth"

    if pth_file.exists():
        print(f"Voicepack already installed at: {pth_file}")
        return True

    settings = AmadeusSettings.load()
    token = hf_token or settings.hf_token or os.environ.get("HF_TOKEN", "")

    urls = [
        f"https://huggingface.co/{repo_id}/resolve/main/kurisu_voicepack.zip",
        "https://github.com/AnuroyZX/Makise_Jarvis/releases/latest/download/kurisu_voicepack.zip",
    ]

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for url in urls:
        print(f"Trying download from: {url}")
        try:
            with httpx.Client(timeout=180.0, follow_redirects=True) as client:
                req_headers = headers if "huggingface.co" in url else {}
                with client.stream("GET", url, headers=req_headers) as resp:
                    if resp.status_code in (401, 403, 404):
                        print(f"Source unavailable (HTTP {resp.status_code}), trying next...")
                        continue
                    resp.raise_for_status()

                    total = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    buf = io.BytesIO()

                    for chunk in resp.iter_bytes(chunk_size=65536):
                        buf.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = (downloaded / total) * 100
                            print(f"\rProgress: {pct:.1f}% ({downloaded // (1024*1024)} MB / {total // (1024*1024)} MB)", end="", flush=True)

                    print("\nExtracting voicepack...")
                    buf.seek(0)
                    with zipfile.ZipFile(buf, "r") as zf:
                        zf.extractall(target)
                    print(f"Voicepack installed successfully into {target}")
                    return True
        except Exception as exc:
            print(f"\nDownload attempt from {url} failed: {exc}")

    print("ERROR: All voicepack download mirrors failed.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Amadeus Kurisu Voicepack from HuggingFace")
    parser.add_argument("--repo", type=str, default="zecto/amadeus-kurisu-voicepack", help="Hugging Face Repository ID")
    parser.add_argument("--token", type=str, default="", help="Hugging Face Access Token (hf_...)")
    parser.add_argument("--dir", type=str, default="", help="Custom output directory")
    args = parser.parse_args()

    target_dir = Path(args.dir) if args.dir else None
    success = download_voicepack(repo_id=args.repo, target_dir=target_dir, hf_token=args.token)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
