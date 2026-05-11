import os
import sys
import requests
import subprocess
import threading
from typing import Optional, Dict

# Configuration
# Replace with your actual GitHub owner/repo
GITHUB_REPO = "Ayushman47/final_yr-proj"
CURRENT_VERSION = "2.0.0"

class UpdateManager:
    def __init__(self):
        self.update_info: Optional[Dict] = None
        self.download_progress = 0
        self.is_downloading = False
        self.temp_installer_path: Optional[str] = None

    def check_for_update(self) -> Dict:
        """
        Checks GitHub Releases for a newer version.
        Returns a dict with update status and details.
        """
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return {"available": False, "error": "Could not reach update server"}

            data = response.json()
            latest_version = data.get("tag_name", "0.0.0").replace("v", "")
            
            # Simple version comparison (can be improved with packaging.version)
            if self._is_newer(latest_version, CURRENT_VERSION):
                # Find the .exe asset
                assets = data.get("assets", [])
                download_url = None
                for asset in assets:
                    if asset["name"].endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break
                
                self.update_info = {
                    "available": True,
                    "latest_version": latest_version,
                    "current_version": CURRENT_VERSION,
                    "release_notes": data.get("body", ""),
                    "download_url": download_url
                }
                return self.update_info
            
            return {"available": False, "current_version": CURRENT_VERSION}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def _is_newer(self, latest: str, current: str) -> bool:
        """Compares two version strings like '1.0.0' and '0.9.9'."""
        try:
            l_parts = [int(p) for p in latest.split(".")]
            c_parts = [int(p) for p in current.split(".")]
            return l_parts > c_parts
        except Exception:
            return latest != current

    def start_download(self, download_url: str):
        """Starts the download in a background thread."""
        if self.is_downloading:
            return False
        
        self.is_downloading = True
        self.download_progress = 0
        thread = threading.Thread(target=self._download_thread, args=(download_url,))
        thread.start()
        return True

    def _download_thread(self, url: str):
        try:
            response = requests.get(url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            
            # Save to user's temp directory
            temp_dir = os.path.join(os.environ.get('TEMP', os.getcwd()), "HealthAssistUpdates")
            os.makedirs(temp_dir, exist_ok=True)
            
            installer_name = "HealthAssist_Setup_Update.exe"
            self.temp_installer_path = os.path.join(temp_dir, installer_name)
            
            downloaded_size = 0
            with open(self.temp_installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            self.download_progress = int((downloaded_size / total_size) * 100)
            
            self.download_progress = 100
        except Exception as e:
            print(f"Download error: {e}")
            self.download_progress = -1
        finally:
            self.is_downloading = False

    def apply_update(self):
        """
        Launches the downloaded installer and terminates the current app.
        The installer should be configured to handle file replacement.
        """
        if not self.temp_installer_path or not os.path.exists(self.temp_installer_path):
            return False
        
        try:
            # Inno Setup flags: 
            # /SILENT - Progress bar only
            # /VERYSILENT - No UI at all
            # /SUPPRESSMSGBOXES - Self explanatory
            # /CLOSEAPPLICATIONS - Attempt to close the app if it's running
            # /RESTARTAPPLICATIONS - Restart the app after install (if supported by installer)
            
            subprocess.Popen([self.temp_installer_path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"])
            
            # Give it a second then exit
            sys.exit(0)
        except Exception as e:
            print(f"Failed to launch update: {e}")
            return False

# Singleton instance
updater = UpdateManager()
