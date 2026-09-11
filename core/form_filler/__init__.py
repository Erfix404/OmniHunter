from pathlib import Path
from typing import Any

from core.form_filler.base_filler import BaseFormFiller
from core.form_filler.ponisha_filler import PonishaFormFiller
from core.form_filler.parscoders_filler import ParscodersFormFiller

# ponytail: static factory mapping over dynamic plug-in registration; upgrade to entry_points if adding 3rd party plugins.


def get_form_filler(platform: str) -> BaseFormFiller:
    """Factory function returning the appropriate BaseFormFiller subclass for platform."""
    norm = (platform or "").strip().lower()
    if norm == "ponisha":
        return PonishaFormFiller()
    elif norm == "parscoders":
        return ParscodersFormFiller()
    else:
        raise ValueError(f"Unsupported form filler platform: '{platform}'")


def fill_application(
    project: dict[str, Any],
    session_path: str | Path | None = None,
    dry_run: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """Top-level convenience wrapper to fill a project application.

    Determines platform from project.get('platform'), resolves the appropriate
    form filler via get_form_filler, and delegates execution.
    """
    if not isinstance(project, dict):
        return {
            "status": "error",
            "platform": "",
            "url": "",
            "bid": None,
            "delivery_days": None,
            "submitted": False,
            "details": "Project must be a dictionary",
        }

    platform = str(project.get("platform") or "").strip()
    if not platform:
        return {
            "status": "error",
            "platform": "",
            "url": str(project.get("url") or ""),
            "bid": project.get("suggested_bid"),
            "delivery_days": project.get("delivery_days"),
            "submitted": False,
            "details": "Missing 'platform' in project dictionary",
        }

    try:
        filler = get_form_filler(platform)
    except ValueError as e:
        return {
            "status": "error",
            "platform": platform,
            "url": str(project.get("url") or ""),
            "bid": project.get("suggested_bid"),
            "delivery_days": project.get("delivery_days"),
            "submitted": False,
            "details": str(e),
        }

    return filler.fill_application(
        project=project,
        session_path=session_path,
        dry_run=dry_run,
        **kwargs,
    )


__all__ = [
    "BaseFormFiller",
    "PonishaFormFiller",
    "ParscodersFormFiller",
    "get_form_filler",
    "fill_application",
]

