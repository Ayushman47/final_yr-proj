import os
import sys
import subprocess
import time
import threading
import webview
import uvicorn
import socket

if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "health-assist-default-secret-key-123"

# Fix stdout/stderr for pyinstaller windowed mode
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from app.main import app

def get_bundle_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def wait_for_port(port, timeout_seconds=15):
    """Poll a local port until it begins accepting connections."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (socket.error, socket.timeout):
            time.sleep(0.5)
    return False

def start_ollama():
    bundle_dir = get_bundle_dir()
    ollama_exe = os.path.join(bundle_dir, "ollama_bin", "ollama.exe")
    models_dir = os.path.join(bundle_dir, "models")
    
    if os.path.exists(ollama_exe):
        print("Starting local Ollama server...")
        os.environ["OLLAMA_MODELS"] = models_dir
        subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        print("Waiting for local AI engine to initialize...")
        wait_for_port(11434, 15)
    else:
        print("Bundled Ollama not found. Checking for system installation...")
        wait_for_port(11434, 5)

def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8001, use_colors=False, log_level="error")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

if __name__ == "__main__":
    start_ollama()
    
    if is_port_in_use(8001):
        print("Error: Port 8001 is already in use. App might already be running.")
        sys.exit(1)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    print("Waiting for backend application to start...")
    if not wait_for_port(8001, 10):
        print("Error: Backend server failed to respond.")
        sys.exit(1)
    
    print("Launching PyWebView window...")
    window = webview.create_window(
        'Health Assist', 
        'http://127.0.0.1:8001', 
        width=1280, 
        height=850, 
        min_size=(1000, 700)
    )
    webview.start()
