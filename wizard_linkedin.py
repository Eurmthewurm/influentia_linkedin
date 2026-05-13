"""
LinkedIn login flow for the wizard.

This module provides a function to open a Playwright browser for LinkedIn login
and save the session, separate from the main linkedin_client.py automation flow.
It's designed to be called from the wizard's "Connect LinkedIn" button.
"""
import os
import json
import logging
import subprocess
import sys
import time
import signal
from pathlib import Path

log = logging.getLogger(__name__)

# Profile dir for the wizard login session
_HERE = os.path.dirname(os.path.abspath(__file__))
WIZARD_PROFILE_DIR = os.path.join(_HERE, "linkedin_wizard_profile")
PROFILE_STATE_FILE = os.path.join(WIZARD_PROFILE_DIR, "state.json")
LOGIN_PID_FILE = os.path.join(WIZARD_PROFILE_DIR, ".login_pid")
LOGIN_STATUS_FILE = os.path.join(WIZARD_PROFILE_DIR, ".login_status.json")


def get_login_status() -> dict:
    """Check the current LinkedIn login status."""
    # Check if there's a saved session
    has_session = os.path.exists(PROFILE_STATE_FILE)
    
    # Check if a login process is running
    is_running = False
    if os.path.exists(LOGIN_PID_FILE):
        try:
            with open(LOGIN_PID_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if process is still alive
            os.kill(pid, 0)
            is_running = True
        except (OSError, ValueError):
            # Process is dead, clean up
            try:
                os.remove(LOGIN_PID_FILE)
            except OSError:
                pass
    
    # Check status file for result
    status = {"connected": has_session, "running": is_running, "error": None}
    if os.path.exists(LOGIN_STATUS_FILE):
        try:
            with open(LOGIN_STATUS_FILE, "r") as f:
                status.update(json.load(f))
        except Exception:
            pass
    
    return status


def start_login_flow() -> dict:
    """
    Start the LinkedIn login flow in a background Playwright process.
    Returns immediately with status.
    """
    # If already connected, return
    if os.path.exists(PROFILE_STATE_FILE):
        return {"ok": True, "connected": True, "message": "Already connected."}
    
    # If already running, return
    status = get_login_status()
    if status["running"]:
        return {"ok": True, "running": True, "message": "Login window already open."}
    
    # Start the login script as a background process
    login_script = os.path.join(_HERE, "_linkedin_login.py")
    
    # Create the login script if it doesn't exist
    _ensure_login_script()
    
    # Launch background process
    proc = subprocess.Popen(
        [sys.executable, login_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # Detach from parent
    )
    
    # Save PID
    os.makedirs(WIZARD_PROFILE_DIR, exist_ok=True)
    with open(LOGIN_PID_FILE, "w") as f:
        f.write(str(proc.pid))
    
    log.info(f"Started LinkedIn login flow (PID {proc.pid})")
    return {"ok": True, "started": True, "message": "LinkedIn login window opened."}


def _ensure_login_script():
    """Create the standalone LinkedIn login script if it doesn't exist."""
    login_script = os.path.join(_HERE, "_linkedin_login.py")
    if os.path.exists(login_script):
        return
    
    script_content = '''#!/usr/bin/env python3
"""
Standalone LinkedIn login script for the wizard.
Opens a visible browser, waits for login, saves session.
"""
import os
import sys
import json
import time
import logging
from pathlib import Path

# Setup paths
_HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(_HERE, "linkedin_wizard_profile")
STATE_FILE = os.path.join(PROFILE_DIR, "state.json")
STATUS_FILE = os.path.join(PROFILE_DIR, ".login_status.json")
PID_FILE = os.path.join(PROFILE_DIR, ".login_pid")
LOG_FILE = os.path.join(PROFILE_DIR, "login.log")

os.makedirs(PROFILE_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

def write_status(**kwargs):
    try:
        data = {}
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE) as f:
                data = json.load(f)
        data.update(kwargs)
        with open(STATUS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log.error(f"Failed to write status: {e}")

def main():
    # Write status: started
    write_status(status="started", message="Opening LinkedIn login window…")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        write_status(status="error", error="Playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)
    
    # Check if already connected
    if os.path.exists(STATE_FILE):
        write_status(status="connected", message="Already connected.")
        return
    
    write_status(status="waiting", message="Waiting for you to log in…")
    
    HEADLESS = False  # Always visible for login
    
    try:
        with sync_playwright() as pw:
            os.makedirs(PROFILE_DIR, exist_ok=True)
            
            browser = pw.chromium.launch(
                headless=HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--window-size=1280,900",
                ],
            )
            
            ctx_kwargs = dict(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
            )
            
            context = browser.new_context(**ctx_kwargs)
            
            # Navigate to LinkedIn login
            page = context.new_page()
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            
            write_status(status="waiting", message="LinkedIn login page opened. Please log in…")
            
            # Wait for successful login (redirect to feed or mynetwork)
            logged_in = False
            max_wait = 300  # 5 minutes
            check_interval = 2
            
            for i in range(0, max_wait, check_interval):
                time.sleep(check_interval)
                try:
                    url = page.url
                    if any(x in url for x in ["/feed", "/mynetwork", "/in/", "/notifications"]):
                        logged_in = True
                        break
                    # Also check if we're still on login page
                    if "linkedin.com/login" not in url and "linkedin.com/checkpoint" not in url:
                        logged_in = True
                        break
                except Exception:
                    pass
            
            if logged_in:
                # Save the session
                context.storage_state(path=STATE_FILE)
                write_status(status="connected", message="Successfully connected to LinkedIn!")
                log.info("LinkedIn login successful, session saved.")
            else:
                write_status(status="timeout", error="Login timed out after 5 minutes. Please try again.")
                log.warning("Login timed out.")
            
            # Keep browser open briefly so user sees confirmation
            time.sleep(3)
            try:
                browser.close()
            except Exception:
                pass
    
    except Exception as e:
        log.error(f"Login flow error: {e}")
        write_status(status="error", error=str(e))

if __name__ == "__main__":
    main()
'''
    
    with open(login_script, "w") as f:
        f.write(script_content)
    
    os.chmod(login_script, 0o755)
    log.info(f"Created login script: {login_script}")


def copy_wizard_profile_to_client():
    """
    Copy the wizard login profile to the main linkedin_profile directory
    so the automation client can use it.
    """
    main_profile_dir = os.path.join(_HERE, "linkedin_profile")
    main_state_file = os.path.join(main_profile_dir, "state.json")
    
    if not os.path.exists(PROFILE_STATE_FILE):
        return False
    
    try:
        os.makedirs(main_profile_dir, exist_ok=True)
        # Copy state file
        with open(PROFILE_STATE_FILE, "r") as f:
            state_data = json.load(f)
        with open(main_state_file, "w") as f:
            json.dump(state_data, f, indent=2)
        
        # Also copy the entire profile directory
        import shutil
        if os.path.exists(main_profile_dir):
            shutil.rmtree(main_profile_dir)
        shutil.copytree(WIZARD_PROFILE_DIR, main_profile_dir)
        
        log.info("Copied wizard profile to main linkedin_profile")
        return True
    except Exception as e:
        log.error(f"Failed to copy profile: {e}")
        return False
