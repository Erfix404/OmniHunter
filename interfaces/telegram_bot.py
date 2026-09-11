import logging
from typing import Any
import requests

from core.report import format_telegram_message

logger = logging.getLogger(__name__)

# ponytail: synchronous requests/urllib Telegram API over python-telegram-bot/aiogram; ceiling ~10 msgs/sec, upgrade to async webhook framework if scaled.
# ponytail: in-memory update offset over database persistence; upgrade to DB-backed offset if bot restarts frequently.


def send_project_alert(
    project: dict[str, Any],
    token: str,
    chat_id: str | int,
    base_url: str = "https://api.telegram.org",
) -> dict[str, Any]:
    """Send formatted telegram alert for a project with inline action buttons.

    Buttons:
    - [ ✅ آماده‌سازی پیشنهاد ] (callback: apply:<id>)
    - [ ❌ رد کردن ] (callback: reject:<id>)
    """
    if not token or not chat_id:
        return {"ok": False, "error": "Missing token or chat_id"}
    if not isinstance(project, dict) or not project:
        return {"ok": False, "error": "Invalid project data"}

    text = format_telegram_message(project)
    project_id = (
        project.get("id")
        or project.get("job_hash")
        or project.get("platform_id")
        or "0"
    )

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ آماده‌سازی پیشنهاد",
                    "callback_data": f"apply:{project_id}",
                },
                {
                    "text": "❌ رد کردن",
                    "callback_data": f"reject:{project_id}",
                },
            ]
        ]
    }

    url = f"{base_url.rstrip('/')}/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Failed to send telegram alert: {e}")
        return {"ok": False, "error": str(e)}


def answer_callback_query(
    token: str,
    callback_query_id: str,
    text: str = "",
    base_url: str = "https://api.telegram.org",
) -> dict[str, Any]:
    """Acknowledge a Telegram callback query to dismiss client-side loading indicator."""
    if not token or not callback_query_id:
        return {"ok": False, "error": "Missing token or callback_query_id"}

    url = f"{base_url.rstrip('/')}/bot{token}/answerCallbackQuery"
    payload = {
        "callback_query_id": str(callback_query_id),
        "text": text,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")
        return {"ok": False, "error": str(e)}


def poll_updates(
    token: str,
    db: Any = None,
    offset: int | None = None,
    limit: int = 10,
    base_url: str = "https://api.telegram.org",
    timeout: int = 1,
) -> list[dict[str, Any]]:
    """Poll Telegram for new updates and process callback queries.

    Handles inline button clicks:
    - apply:<id> -> update project status in DB (or trigger filler)
    - reject:<id> -> update project status to 'rejected' in DB
    """
    if not token:
        return []

    url = f"{base_url.rstrip('/')}/bot{token}/getUpdates"
    params: dict[str, Any] = {"limit": limit, "timeout": timeout}
    if offset is not None:
        params["offset"] = offset

    try:
        response = requests.get(url, params=params, timeout=timeout + 5)
        if response.status_code != 200:
            return []
        data = response.json()
        updates = data.get("result", [])
    except Exception as e:
        logger.error(f"Failed to poll telegram updates: {e}")
        return []

    handled_actions: list[dict[str, Any]] = []

    for upd in updates:
        if not isinstance(upd, dict):
            continue
        update_id = upd.get("update_id")

        if "callback_query" in upd:
            cb = upd["callback_query"]
            cb_id = cb.get("id")
            cb_data = str(cb.get("data") or "")

            if cb_data.startswith("apply:"):
                target_id = cb_data.split(":", 1)[1]
                if db is not None:
                    db.update_status(target_id, "applied")
                answer_callback_query(
                    token=token,
                    callback_query_id=cb_id,
                    text="آماده‌سازی پیشنهاد ثبت شد",
                    base_url=base_url,
                )
                handled_actions.append(
                    {
                        "action": "apply",
                        "job_id": target_id,
                        "update_id": update_id,
                    }
                )
            elif cb_data.startswith("reject:"):
                target_id = cb_data.split(":", 1)[1]
                if db is not None:
                    db.update_status(target_id, "rejected")
                answer_callback_query(
                    token=token,
                    callback_query_id=cb_id,
                    text="پروژه رد شد",
                    base_url=base_url,
                )
                handled_actions.append(
                    {
                        "action": "reject",
                        "job_id": target_id,
                        "update_id": update_id,
                    }
                )
            else:
                handled_actions.append(
                    {
                        "action": "unknown",
                        "data": cb_data,
                        "update_id": update_id,
                    }
                )
        else:
            handled_actions.append(
                {
                    "action": "ignore",
                    "update_id": update_id,
                }
            )

    return handled_actions
