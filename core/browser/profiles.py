"""Discover Chrome profiles from the local system."""
import json
import os
from typing import Any

def get_chrome_profiles() -> dict[str, dict[str, Any]]:
    """Parse Chrome's Local State to return available profiles.

    Returns a dict mapping directory names (e.g. 'Profile 1') to profile info.
    """
    if os.name != "nt":
        return {}

    local_state_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State")

    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        return {}

    profile_data = data.get("profile", {})
    info_cache = profile_data.get("info_cache", {})
    last_used = profile_data.get("last_used", "")

    result = {}
    for dir_name, info in info_cache.items():
        result[dir_name] = {
            "name": info.get("name", "Unknown"),
            "email": info.get("user_name", ""),
            "is_last_used": (dir_name == last_used)
        }

    return result
