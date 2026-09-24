"""Client Handover & Escrow Release Pack.

Generates a non-technical delivery bundle for freelance clients:
a Persian run guide, 1-click launchers (Windows/Linux), and a polite
final-delivery message that asks for escrow release and a 5-star review.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


HANDOVER_FILES = [
    "راهنمای_ساده_اجرا.md",
    "run.bat",
    "run.sh",
    "پیام_تحویل_نهایی.txt",
]


def _safe(value: Any, default: str = "-") -> str:
    text = str(value).strip() if value is not None else ""
    return text if text else default


def generate_handover_pack(
    project: dict[str, Any] | None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build the client handover pack for a project.

    Handles missing or partial project data gracefully.
    """
    proj: dict[str, Any] = dict(project) if isinstance(project, dict) else {}
    platform = str(proj.get("platform") or "project").strip() or "project"
    platform_id = str(proj.get("platform_id") or proj.get("id") or "general").strip() or "general"

    if output_dir is None:
        out_path = Path("handovers") / f"{platform}_{platform_id}"
    else:
        out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    title = _safe(proj.get("title"), "پروژه تحویل‌شده")
    description = _safe(proj.get("description"), "طبق توافق انجام‌شده در شرح پروژه.")
    scope = _safe(proj.get("scope"), "عمومی")
    delivery_days = _safe(proj.get("delivery_days"), "-")
    suggested_bid = proj.get("suggested_bid")
    bid_text = _safe(suggested_bid, "-")
    prerequisites = proj.get("prerequisites")
    if isinstance(prerequisites, list) and prerequisites:
        prereq_lines = "\n".join(f"- {str(p).strip()}" for p in prerequisites if str(p).strip())
        if not prereq_lines:
            prereq_lines = "- مورد خاصی لازم نیست."
    else:
        prereq_lines = "- پایتون نسخه 3.10 یا جدیدتر\n- اتصال اینترنت\n- دسترسی‌ها و توکن‌هایی که در چت اعلام شده است"

    guide = f"""# راهنمای ساده اجرای {title}

## ۱. این پروژه چه چیزی تحویل می‌دهد؟
{description}

- عنوان پروژه: {title}
- حوزه کاری: {scope}
- مدت تحویل توافقی: {delivery_days} روز

## ۲. پیش‌نیازهای اولیه
{prereq_lines}

## ۳. نحوه اجرای سریع با ۱ کلیک
- در ویندوز: روی فایل `run.bat` دو بار کلیک کنید.
- در لینوکس یا مک: در ترمینال وارد پوشه شوید و دستور زیر را اجرا کنید:
  `bash run.sh`
- برنامه خودش پایتون را بررسی می‌کند، نیازمندی‌ها را نصب می‌کند و اجرا را شروع می‌کند.

## ۴. نحوه تنظیم توکن‌ها یا کلیدهای API
1. فایل تنظیمات یا متنی که در چت اعلام شده را باز کنید.
2. توکن یا کلید API را در جای مشخص‌شده وارد کنید.
3. برنامه را دوباره با همان ۱ کلیک اجرا کنید.
4. اگر خطای «توکن نامعتبر» دیدید، توکن را دوباره بررسی و جایگزین کنید.

## ۵. سوالات احتمالی و پشتیبانی اولیه
- اگر برنامه باز نشد: مطمئن شوید پایتون نصب است و اینترنت وصل است.
- اگر خطایی دیدید: متن خطا را برای من ارسال کنید تا بررسی کنم.
- پشتیبانی اولیه شامل رفع باگ احتمالی در دوره توافقی است و خوشحال می‌شوم کمک کنم.
"""

    run_bat = """@echo off
chcp 65001 >nul
echo Checking Python...
python --version
IF ERRORLEVEL 1 (
  echo Python is not installed. Please install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)
IF EXIST requirements.txt (
  echo Installing requirements...
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
)
echo Starting the program...
IF EXIST main.py (
  python main.py
) ELSE (
  echo main.py not found. Please contact support for the run instructions.
)
pause
"""

    run_sh = """#!/usr/bin/env bash
set -e
echo "Checking Python..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 is not installed. Please install Python 3.10+ first."
  exit 1
fi
python3 --version
if [ -f requirements.txt ]; then
  echo "Installing requirements..."
  python3 -m pip install --upgrade pip
  python3 -m pip install -r requirements.txt
fi
echo "Starting the program..."
if [ -f main.py ]; then
  python3 main.py
else
  echo "main.py not found. Please contact support for the run instructions."
fi
"""

    handover_text = f"""سلام وقت بخیر،
خوشحالم اعلام کنم که تعهدات پروژه «{title}» طبق توافق انجام شد.
تست‌های فنی را انجام دادم و از عملکرد صحیح خروجی اطمینان حاصل شده است.
فایل «راهنمای ساده اجرا» را ضمیمه کردم تا بدون نیاز به دانش فنی بتوانید برنامه را اجرا کنید.
در دوره پشتیبانی اولیه، اگر باگ احتمالی مشاهده شد حتماً اطلاع دهید تا سریع رفع کنم.
ممنون می‌شوم تحویل نهایی را تایید کنید، پرداخت امن (بیعانه/Escrow) را آزاد کنید و بازخورد ۵ ستاره ثبت کنید.
سپاس از همکاری شما!"""

    files_content = {
        "راهنمای_ساده_اجرا.md": guide,
        "run.bat": run_bat,
        "run.sh": run_sh,
        "پیام_تحویل_نهایی.txt": handover_text,
    }
    for fname, content in files_content.items():
        (out_path / fname).write_text(content, encoding="utf-8")
    # Executable mode for the Linux/Mac launcher.
    try:
        os.chmod(out_path / "run.sh", 0o755)
    except OSError:
        pass

    return {
        "status": "success",
        "output_dir": str(out_path),
        "files": list(HANDOVER_FILES),
        "handover_message": handover_text,
    }
