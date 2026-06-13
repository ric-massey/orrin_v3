# agency/skills/notify_user.py
# Send a desktop notification to the user. Cross-platform:
#   macOS   → osascript "display notification"
#   Windows → PowerShell balloon tip (shown as a toast on Win10/11)
#   Linux   → notify-send (if available)
from __future__ import annotations

import platform
import shutil
import subprocess
from utils.log import log_activity, log_error

_PLATFORM = platform.system()


def _send_macos(message: str, title: str, subtitle: str) -> tuple[bool, str]:
    # Escape double-quotes so osascript doesn't break
    msg = message.replace('"', '\\"')
    ttl = title.replace('"', '\\"')
    sub = subtitle.replace('"', '\\"')
    if sub:
        script = f'display notification "{msg}" with title "{ttl}" subtitle "{sub}"'
    else:
        script = f'display notification "{msg}" with title "{ttl}"'
    r = subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "")


def _send_windows(message: str, title: str) -> tuple[bool, str]:
    # Balloon tip via .NET NotifyIcon — redirected to a native toast on Win10/11.
    safe_msg = message.replace("'", "''")
    safe_ttl = title.replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        f"$n.BalloonTipTitle='{safe_ttl}';"
        f"$n.BalloonTipText='{safe_msg}';"
        "$n.Visible=$true;$n.ShowBalloonTip(5000);Start-Sleep -Seconds 3;$n.Dispose()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       timeout=10, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "")


def _send_linux(message: str, title: str) -> tuple[bool, str]:
    exe = shutil.which("notify-send")
    if not exe:
        return False, "notify-send not available (install libnotify-bin)"
    r = subprocess.run([exe, title, message], timeout=5, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or "")


def notify_user(args=None, **kwargs) -> dict:
    """
    Send a desktop notification (macOS / Windows / Linux).
    args: str message, or dict with keys message/title/subtitle
    """
    if isinstance(args, dict):
        kwargs.update(args)
        args = None

    message = str(args or kwargs.get("message") or kwargs.get("content") or "Orrin has something to tell you")[:200]
    title = str(kwargs.get("title", "Orrin"))
    subtitle = str(kwargs.get("subtitle", ""))

    try:
        if _PLATFORM == "Darwin":
            ok, err = _send_macos(message, title, subtitle)
        elif _PLATFORM == "Windows":
            ok, err = _send_windows(message, title)
        else:
            ok, err = _send_linux(message, title)

        if ok:
            log_activity(f"Notification sent: {message[:80]}")
            return {"success": True, "message": message}
        else:
            log_error(f"notify_user failed on {_PLATFORM}: {err[:200]}")
            return {"success": False, "error": err[:200]}
    except Exception as e:
        log_error(f"notify_user failed: {e}")
        return {"success": False, "error": str(e)}
