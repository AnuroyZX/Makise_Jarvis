from __future__ import annotations

import os
import platform
import sys
import psutil

def main() -> None:
    print("=" * 60)
    print("AMADEUS KURISU — HARDWARE & VOICELAB BENCHMARK")
    print("=" * 60)
    print(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
    print(f"Python: {sys.version.split()[0]} ({platform.architecture()[0]})")
    ram = psutil.virtual_memory()
    print(f"System RAM: {ram.total / (1024**3):.2f} GB (Available: {ram.available / (1024**3):.2f} GB)")

    # Test PyTorch & CUDA
    try:
        import torch
        print(f"PyTorch Version: {torch.__version__}")
        cuda_avail = torch.cuda.is_available()
        print(f"CUDA Available: {cuda_avail}")
        if cuda_avail:
            device_count = torch.cuda.device_count()
            for i in range(device_count):
                dev_name = torch.cuda.get_device_name(i)
                cap = torch.cuda.get_device_capability(i)
                total_mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                free_mem, _ = torch.cuda.mem_get_info(i)
                free_gb = free_mem / (1024**3)
                print(f"  GPU {i}: {dev_name}")
                print(f"    Compute Capability: {cap[0]}.{cap[1]}")
                print(f"    Total VRAM: {total_mem:.2f} GB")
                print(f"    Free VRAM: {free_gb:.2f} GB")
                print(f"    FP16 Supported: {cap[0] >= 5}")
                print(f"    BF16 Supported: {torch.cuda.is_bf16_supported()}")
    except ImportError:
        print("PyTorch: Not installed in current environment (expected for lightweight core; installed in voicelab).")

    # Check for audio libraries
    for mod in ("sounddevice", "numpy", "edge_tts", "websockets", "mss"):
        try:
            __import__(mod)
            print(f"Library '{mod}': Available")
        except ImportError:
            print(f"Library '{mod}': NOT installed")

    print("=" * 60)

if __name__ == "__main__":
    main()
