import os
import json

# Navigate from src/services/whisper/path_config.py to project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PATH_JSON = os.path.join(PROJECT_ROOT, "path.json")

def ensure_directories(config: dict):
    """Ensure that the directories specified in the config exist, and clone models if missing."""
    dir_keys = ["WATCH_DIR", "save_path"]
    
    for key in dir_keys:
        if key in config:
            dir_path = os.path.join(PROJECT_ROOT, config[key])
            os.makedirs(dir_path, exist_ok=True)
            
    if "whisper_model" in config:
        model_dir = os.path.join(PROJECT_ROOT, config["whisper_model"])
        os.makedirs(model_dir, exist_ok=True)
        
        # Check if the directory is empty (model not downloaded)
        if not os.listdir(model_dir):
            print("Whisper model not found locally. Downloading from HuggingFace...")
            try:
                from huggingface_hub import snapshot_download
                snapshot_download(repo_id="Systran/faster-whisper-base", local_dir=model_dir)
                print("Whisper model downloaded successfully.")
            except ImportError:
                print("huggingface_hub is not installed. Trying to install and download...")
                import subprocess
                subprocess.run([config.get("PYTHON_EXEC", "python"), "-m", "pip", "install", "huggingface_hub"], check=True)
                from huggingface_hub import snapshot_download
                snapshot_download(repo_id="Systran/faster-whisper-base", local_dir=model_dir)
                print("Whisper model downloaded successfully.")
            except Exception as e:
                print(f"Failed to download whisper model: {e}")

def load_path_config() -> dict:
    default_config = {
        "whisper_model": "./whisperModels/faster-whisper-base",
        "PYTHON_EXEC": "./.venv/bin/python",
        "TRANSCRIPT_SCRIPT": "services.whisper.transcript",
        "save_path": ".",
        "WATCH_DIR": "./input"
    }
    
    config = default_config.copy()
    
    if not os.path.exists(PATH_JSON):
        with open(PATH_JSON, "w") as f:
            json.dump(default_config, f, indent=4)
    else:
        try:
            with open(PATH_JSON, "r") as f:
                loaded_config = json.load(f)
                updated = False
                for key, val in default_config.items():
                    if key not in loaded_config:
                        loaded_config[key] = val
                        updated = True
                config = loaded_config
                
                if updated:
                    with open(PATH_JSON, "w") as f:
                        json.dump(config, f, indent=4)
        except (json.JSONDecodeError, OSError):
            with open(PATH_JSON, "w") as f:
                json.dump(default_config, f, indent=4)
                
    ensure_directories(config)
    
    return config
