from sys import argv, exit
import subprocess
from os import path
import platform
from json import load


def detect_device():
    system = platform.system()
    try:
        _ = subprocess.check_output(["nvidia-smi"], stderr=subprocess.DEVNULL)
        print("✓ NVIDIA CUDA device detected")
        return "cuda"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        _ = subprocess.check_output(["rocm-smi"], stderr=subprocess.DEVNULL)
        print("✓ AMD ROCm device detected")
        return "cuda"  # faster-whisper uses "cuda" for ROCm
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if system == "Windows":
        try:
            result = subprocess.check_output(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if "AMD" in result or "Radeon" in result:
                print("✓ AMD GPU detected (Windows)")
                return "cuda"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    try:
        if system == "Linux":
            result = subprocess.check_output(
                ["lspci"], stderr=subprocess.DEVNULL, text=True
            )
            if "Intel" in result and ("VGA" in result or "Display" in result):
                print("✓ Intel GPU detected")
                # Note: faster-whisper may need special setup for Intel GPUs
                return "cpu"
        elif system == "Windows":
            result = subprocess.check_output(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if "Intel" in result and (
                "Arc" in result or "Iris" in result or "UHD" in result
            ):
                print("✓ Intel GPU detected")
                return "cpu"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if system == "Darwin":
        machine = platform.machine()
        if machine == "arm64":
            print("✓ Apple Silicon detected (M-series chip)")
            return "cpu"
        else:
            print("✓ macOS Intel detected")
    print("ℹ Using CPU (no GPU accelerator detected)")
    return "cpu"


if len(argv) < 2:
    print("Usage: python transcribe_file.py <audio_or_video_file>")
    exit(1)

input_file = argv[1]
# ====== Configuration ======
with open("path.json", "r") as f:
    config_data = load(f)
file_name = path.basename(input_file)
model_path = config_data["whisper_model"]
device = detect_device()
sample_rate = 16000
save_path = config_data["save_path"]
file = save_path + "/" + file_name + ".md"
# ===========================
