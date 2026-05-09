import os
import sys

# Set default SECRET_KEY immediately (must happen before importing 'app')
if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "health-assist-default-secret-key-123"

# Fix for Windowed mode: ensure stdout/stderr exist even if no terminal
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import subprocess
import time
import threading
import webview
import uvicorn
from app.main import app

def get_bundle_dir():
    """Returns the directory where the application is running, 
    handling both normal Python and PyInstaller environments."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def start_ollama():
    """Starts the bundled Ollama engine in the background."""
    bundle_dir = get_bundle_dir()
    
    # Path to the bundled ollama.exe
    ollama_exe = os.path.join(bundle_dir, "ollama_bin", "ollama.exe")
    
    # Path to the bundled models folder
    models_dir = os.path.join(bundle_dir, "models")
    
    if os.path.exists(ollama_exe):
        print(f"--- Starting AI Engine (Ollama) ---")
        # Set environment variable so Ollama uses our bundled models
        os.environ["OLLAMA_MODELS"] = models_dir
        
        # Start Ollama server quietly in the background
        subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        # Give it a moment to initialize
        time.sleep(3)
    else:
        print("--- Note: Bundled Ollama not found. Using system Ollama if available. ---")

def start_server():
    """Start the FastAPI server in a separate thread."""
    uvicorn.run(app, host="127.0.0.1", port=8000, use_colors=False, log_level="error")

if __name__ == "__main__":
    # 1. Initialize the AI Engine
    start_ollama()
    
    # 2. Start the FastAPI server in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # 3. Wait a moment for the server to spin up
    time.sleep(2)
    
    # 4. Open the Native Desktop Window
    print("--- Launching Health Assist Native Window ---")
    webview.create_window('Health Assist AI', 'http://127.0.0.1:8000', width=1200, height=800)
    webview.start()
