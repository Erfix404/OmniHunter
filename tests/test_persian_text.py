from core.persian_text import (
    de_ai_persian,
    fix_arabic_glyphs,
    fix_persian_punctuation,
    fix_zwnj,
    humanize_persian,
)


def test_fix_arabic_glyphs():
    assert fix_arabic_glyphs("عليرضا با كيفيت عاليه") == "علیرضا با کیفیت عالیه"
    assert "ي" not in fix_arabic_glyphs("علي")
    assert "ك" not in fix_arabic_glyphs("كتاب")
    assert "ة" not in fix_arabic_glyphs("مدرسة")
    assert fix_arabic_glyphs("") == ""


def test_fix_zwnj_verbs():
    assert fix_zwnj("می شود") == "می‌شود"
    assert fix_zwnj("نمی شود") == "نمی‌شود"
    assert fix_zwnj("می کنم") == "می‌کنم"
    assert fix_zwnj("می توان") == "می‌توان"


def test_fix_zwnj_suffixes():
    assert fix_zwnj("پروژه ها") == "پروژه‌ها"
    assert fix_zwnj("سایت های") == "سایت‌های"
    assert fix_zwnj("سریع تر") == "سریع‌تر"
    assert fix_zwnj("دقیق تر") == "دقیق‌تر"


def test_fix_zwnj_prefixes():
    assert fix_zwnj("بی نقص") == "بی‌نقص"
    assert fix_zwnj("بی دردسر") == "بی‌دردسر"
    assert fix_zwnj("هم زمان") == "هم‌زمان"


def test_fix_zwnj_compounds():
    assert fix_zwnj("دست کم") == "دست‌کم"
    assert fix_zwnj("راه حل") == "راه‌حل"
    assert fix_zwnj("پیش نیاز") == "پیش‌نیاز"
    assert fix_zwnj("پایگاه داده") == "پایگاه‌داده"


def test_fix_persian_punctuation():
    out = fix_persian_punctuation("متن , با علائم ; مختلف ?")
    assert "،" in out and "," not in out
    assert "؛" in out and ";" not in out
    assert "؟" in out and "?" not in out
    assert "متن،" in out
    assert "علائم؛" in out

    quoted = fix_persian_punctuation('او گفت "سلام" و رفت')
    assert "«سلام»" in quoted
    assert '"' not in quoted

    dashed = fix_persian_punctuation("متن — ادامه")
    assert "—" not in dashed
    assert "–" not in dashed
    assert "،" in dashed


def test_de_ai_persian():
    assert "است" in de_ai_persian("این سیستم می‌باشد")
    assert "می‌باشد" not in de_ai_persian("این سیستم می‌باشد")
    assert "میباشد" not in de_ai_persian("این سیستم میباشد")
    assert "می‌شود" in de_ai_persian("ارائه می‌گردد")
    assert "می‌گردد" not in de_ai_persian("ارائه می‌گردد")
    assert "میگردد" not in de_ai_persian("ارائه میگردد")


def test_humanize_persian_end_to_end():
    raw = "اين پروژه ها می شود , با کيفيت می‌باشد"
    out = humanize_persian(raw)
    assert "ي" not in out
    assert "ك" not in out
    assert "می‌باشد" not in out
    assert "پروژه‌ها" in out
    assert "می‌شود" in out
    assert "،" in out
