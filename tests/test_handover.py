"""Tests for the Client Handover & Escrow Release Pack (core/handover.py)."""

import os
import stat
from pathlib import Path

from core.handover import HANDOVER_FILES, generate_handover_pack


FULL_PROJECT = {
    "platform": "ponisha",
    "platform_id": "handover_1",
    "title": "ربات تلگرام فروشگاهی",
    "description": "ربات تلگرام با قابلیت ثبت سفارش و اتصال به درگاه پرداخت.",
    "scope": "bots",
    "delivery_days": 3,
    "suggested_bid": 4500000,
    "prerequisites": ["توکن ربات از BotFather", "نمونه جریان تعامل"],
}


def test_handover_creates_all_four_files(tmp_path):
    out = tmp_path / "pack_full"
    res = generate_handover_pack(dict(FULL_PROJECT), output_dir=out)

    assert res["status"] == "success"
    assert res["output_dir"] == str(out)
    assert res["files"] == HANDOVER_FILES
    assert len(res["handover_message"]) > 50

    for fname in HANDOVER_FILES:
        assert (out / fname).exists(), f"Missing handover file: {fname}"


def test_handover_guide_content(tmp_path):
    out = tmp_path / "pack_guide"
    generate_handover_pack(dict(FULL_PROJECT), output_dir=out)

    guide = (out / "راهنمای_ساده_اجرا.md").read_text(encoding="utf-8")
    assert FULL_PROJECT["title"] in guide
    assert "پایتون" in guide
    assert "run.bat" in guide
    assert "run.sh" in guide
    assert "توکن" in guide or "API" in guide
    assert "پشتیبانی" in guide
    # Project prerequisites surface in the guide.
    assert "توکن ربات از BotFather" in guide


def test_handover_launchers_structure(tmp_path):
    out = tmp_path / "pack_launch"
    generate_handover_pack(dict(FULL_PROJECT), output_dir=out)

    bat = (out / "run.bat").read_text(encoding="utf-8")
    assert "python" in bat.lower()
    assert "requirements" in bat.lower()

    sh = (out / "run.sh").read_text(encoding="utf-8")
    assert "python3" in sh
    assert "requirements" in sh
    # run.sh must be executable.
    mode = os.stat(out / "run.sh").st_mode
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_handover_message_content(tmp_path):
    out = tmp_path / "pack_msg"
    res = generate_handover_pack(dict(FULL_PROJECT), output_dir=out)

    msg_file = (out / "پیام_تحویل_نهایی.txt").read_text(encoding="utf-8")
    assert msg_file == res["handover_message"]
    assert "طبق توافق" in msg_file
    assert "تست" in msg_file
    assert "راهنما" in msg_file
    assert "پشتیبانی" in msg_file
    assert "Escrow" in msg_file or "بیعانه" in msg_file
    assert "۵ ستاره" in msg_file
    assert "تایید" in msg_file


def test_handover_graceful_with_missing_data(tmp_path):
    # Empty dict: all sections fall back to defaults without raising.
    out = tmp_path / "pack_empty"
    res = generate_handover_pack({}, output_dir=out)
    assert res["status"] == "success"
    for fname in HANDOVER_FILES:
        assert (out / fname).exists()
    assert "پروژه" in res["handover_message"]

    # None project entirely.
    out2 = tmp_path / "pack_none"
    res2 = generate_handover_pack(None, output_dir=out2)
    assert res2["status"] == "success"
    assert len(res2["handover_message"]) > 50

    # Partial project: only a title.
    out3 = tmp_path / "pack_partial"
    res3 = generate_handover_pack({"title": "فقط عنوان"}, output_dir=out3)
    assert res3["status"] == "success"
    guide = (out3 / "راهنمای_ساده_اجرا.md").read_text(encoding="utf-8")
    assert "فقط عنوان" in guide


def test_handover_default_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = generate_handover_pack(dict(FULL_PROJECT))
    expected = Path("handovers") / "ponisha_handover_1"
    assert Path(res["output_dir"]) == expected
    assert expected.is_dir()
    for fname in HANDOVER_FILES:
        assert (expected / fname).exists()
