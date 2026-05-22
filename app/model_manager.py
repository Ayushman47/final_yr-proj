import os
import sys
import json
import subprocess
import threading

# Find bundled ollama path
def get_bundle_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_ollama_exe():
    bundle_dir = get_bundle_dir()
    exe_path = os.path.join(bundle_dir, "ollama_bin", "ollama.exe")
    if os.path.exists(exe_path):
        return exe_path
    return "ollama"

def get_config_path():
    app_data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "HealthAssist")
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "model_config.json")

def get_models_dir():
    app_data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "HealthAssist")
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "models")

def get_active_model():
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                return data.get("active_model", None)
        except:
            pass
    return None

def set_active_model(model_name: str):
    config_path = get_config_path()
    with open(config_path, "w") as f:
        json.dump({"active_model": model_name}, f)

def get_installed_models():
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = get_models_dir()
    try:
        result = subprocess.run(
            [get_ollama_exe(), "list"],
            capture_output=True, encoding='utf-8', errors='replace', env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        lines = result.stdout.strip().split("\n")
        models = []
        if len(lines) > 1:
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 1:
                    name = parts[0]
                    # Filter embedding and system models
                    if "embed" in name.lower() or name.lower() in ["nomic-embed-text", "mxbai-embed-large"]:
                        continue
                    models.append(name)
        return models
    except Exception as e:
        print("Error listing models:", e)
        return []

def delete_model(model_name: str):
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = get_models_dir()
    try:
        subprocess.run(
            [get_ollama_exe(), "rm", model_name],
            check=True, capture_output=True, encoding='utf-8', errors='replace', env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        active = get_active_model()
        if active == model_name:
            set_active_model(None)
        return True
    except subprocess.CalledProcessError as e:
        print("Error deleting model:", e.stderr)
        return False

# Global state for download progress
download_progress = {
    "model": None,
    "status": "idle",
    "percent": 0,
    "downloaded": "",
    "total": "",
    "speed": ""
}

active_pull_process = None

def _pull_model_thread(model_name: str):
    global download_progress, active_pull_process
    download_progress = {"model": model_name, "status": "downloading", "percent": 0, "downloaded": "", "total": "", "speed": ""}
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = get_models_dir()
    try:
        active_pull_process = subprocess.Popen(
            [get_ollama_exe(), "pull", model_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            errors='replace',
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        # Use a local reference to the process to avoid NoneType error if cancelled
        proc_ref = active_pull_process
        
        import re
        for line in iter(proc_ref.stdout.readline, ''):
            if not active_pull_process: # If global is cleared, we were cancelled
                break
            # Match percentage
            pct_match = re.search(r'(\d+)%', line)
            if pct_match:
                download_progress["percent"] = int(pct_match.group(1))
            
            # Match speed (e.g. 10 MB/s or 2.5 KB/s)
            speed_match = re.search(r'([0-9.]+\s*[KMGT]B/s)', line, re.IGNORECASE)
            if speed_match:
                download_progress["speed"] = speed_match.group(1)
                
            # Match downloaded / total size (e.g. 10 MB / 100 MB)
            size_match = re.search(r'([0-9.]+\s*[KMGT]B)\s*/\s*([0-9.]+\s*[KMGT]B)', line, re.IGNORECASE)
            if size_match:
                download_progress["downloaded"] = size_match.group(1)
                download_progress["total"] = size_match.group(2)
                    
        proc_ref.wait()
        
        # If cancelled, status is already updated
        if download_progress["status"] == "cancelled":
            pass
        elif proc_ref.returncode == 0:
            download_progress["status"] = "success"
            download_progress["percent"] = 100
        else:
            download_progress["status"] = "failed"
            
    except Exception as e:
        print("Error pulling model:", e)
        if download_progress["status"] != "cancelled":
            download_progress["status"] = "failed"
    finally:
        active_pull_process = None

def start_pull_model(model_name: str):
    if download_progress["status"] == "downloading":
        return False # Already downloading
    t = threading.Thread(target=_pull_model_thread, args=(model_name,))
    t.daemon = True
    t.start()
    return True

def cancel_pull_model():
    global active_pull_process, download_progress
    if active_pull_process:
        active_pull_process.terminate()
        active_pull_process = None
    if download_progress["status"] == "downloading":
        download_progress["status"] = "cancelled"
    return True

def get_pull_progress():
    return download_progress

