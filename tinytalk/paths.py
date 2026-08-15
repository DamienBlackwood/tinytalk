"""
Where tinytalk keeps its things.

This used to be `.tinytalk/` next to the source tree, which was fine right up
until someone installed with pipx: the folder landed inside site-packages and
every reinstall took the key and the transcripts with it. Now it lives in your
home folder, and TINYTALK_HOME moves it if you'd rather keep it per-project.
"""
import os
import shutil
import sys
from pathlib import Path

_FILES = ("key", "config.json", "transcripts.jsonl")


def _default_home() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "tinytalk"
    return Path.home() / ".tinytalk"


def _pick_home() -> Path:
    override = os.environ.get("TINYTALK_HOME")
    return Path(override).expanduser() if override else _default_home()


HOME        = _pick_home()
CONFIG      = HOME / "config.json"
KEY         = HOME / "key"
TRANSCRIPTS = HOME / "transcripts.jsonl"

# the old spot, back when everything sat beside the package
LEGACY = Path(__file__).resolve().parent.parent / ".tinytalk"


def ensure_home() -> bool:
    try:
        HOME.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    try:
        os.chmod(HOME, 0o700)
    except OSError:
        pass  # windows does ACLs, whatever
    return True


def adopt_legacy() -> None:
    """Pull an old `.tinytalk/` across the first time we see one.

    Copies rather than moves. If any of this goes sideways I'd much rather the
    originals were still sitting where the user left them.
    """
    if LEGACY == HOME or not LEGACY.is_dir():
        return
    pending = [n for n in _FILES if (LEGACY / n).is_file() and not (HOME / n).exists()]
    if not pending or not ensure_home():
        return
    for name in pending:
        try:
            shutil.copy2(LEGACY / name, HOME / name)
        except OSError:
            pass
    try:
        os.chmod(KEY, 0o600)
    except OSError:
        pass
