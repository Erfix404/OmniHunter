"""Persian writing engine: orthography, punctuation, and natural proposal humanizer.

Zero-external-dependency, pure-Python regex module implementing
``persian-writing`` rules (ZWNJ / نیم‌فاصله, de-AIing, orthography,
Persian punctuation).
"""

import re

ZWNJ = "‌"

# Pre-compiled patterns (module level for reuse).
_ARABIC_YEH = "ي"  # U+064A
_PERSIAN_YEH = "ی"  # U+06CC
_ARABIC_KEH = "ك"  # U+0643
_PERSIAN_KEH = "ک"  # U+06A9
_ARABIC_TEH_MARBUTA = "ة"  # U+0629

_FA_LETTER = "[؀-ۿ]"

# می / نمی + space + verb stem (spaced forms only; attached forms like
# «میشود» are left alone to avoid false positives on nouns like میان/میز).
_VERB_PREFIX_RE = re.compile(r"\b(می|نمی)\s+(" + _FA_LETTER + ")")

# Suffixes: ها / های, تر / ترین (longer alternative first).
_HA_RE = re.compile(r"(" + _FA_LETTER + r")\s+(های|ها)\b")
_TAR_RE = re.compile(r"(" + _FA_LETTER + r")\s+(ترین|تر)\b")

# Prefix بی + word (almost always a compound in modern Persian).
_BI_RE = re.compile(r"\bبی\s+(" + _FA_LETTER + "+)")

# هم + word: only for known هم‌ compounds to avoid breaking the
# conjunction هم (= also/too), e.g. «در ساعات شلوغی هم بدون افت».
_HAM_COMPOUNDS = {
    "زمان",
    "مسیر",
    "جهت",
    "سو",
    "گام",
    "رده",
    "فکر",
    "نظر",
    "دل",
    "درد",
    "راه",
    "کار",
    "کلاس",
    "گروه",
    "تیم",
    "سفر",
    "اتاق",
    "خانه",
    "بنیان",
    "آوا",
    "آهنگ",
    "سرنوشت",
    "بازی",
    "مسلک",
    "قافیه",
    "وزن",
    "دوره",
    "عصر",
    "نسل",
    "رشته",
    "صنف",
    "قطار",
    "سطح",
    "تراز",
}
_HAM_RE = re.compile(r"\bهم\s+(" + "|".join(sorted(_HAM_COMPOUNDS)) + r")\b")

# Lexicalized multi-word compounds.
_COMPOUNDS = [
    ("دست کم", "دست‌کم"),
    ("راه حل", "راه‌حل"),
    ("پیش نیاز", "پیش‌نیاز"),
    ("پایگاه داده", "پایگاه‌داده"),
]

# De-AI patterns.
_MIBASHAD_RE = re.compile(r"می[‌\s]?باشد")
_MIGARDAD_RE = re.compile(r"می[‌\s]?گردد")
_GARDAD_RE = re.compile(r"(?<![؀-ۿ])گردد\b")
_BE_SHOMAR_RE = re.compile(r"به شمار می[‌\s]?رود")
_MAHSOOB_RE = re.compile(r"محسوب می[‌\s]?شود")
_DAR_RASTAYE_RE = re.compile(r"در راستای")
_LAZEM_RE = re.compile(r"لازم به ذکر است( که)?")
_SHAYAN_RE = re.compile(r"شایان ذکر است( که)?")
_AHAMIAT_RE = re.compile(r"از اهمیت ویژه[‌\s]?ای برخوردار است")

# Punctuation.
_QUOTE_RE = re.compile(r'"([^"]+)"')
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([،؛.؟!»:])")
# One space after ،؛؟! — but never before a closing mark (» ) . ، ؛ ؟ !).
_SPACE_AFTER_PUNCT_RE = re.compile(r"([،؛؟!])(?=[^\s\n»\)\].،؛؟!:])")
_FA_AFTER_DOT_RE = re.compile(r"\.([آ-ی])")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def fix_arabic_glyphs(text: str) -> str:
    """Replace Arabic glyphs with their Persian counterparts."""
    if not text:
        return text
    text = text.replace(_ARABIC_YEH, _PERSIAN_YEH)
    text = text.replace(_ARABIC_KEH, _PERSIAN_KEH)
    text = text.replace(_ARABIC_TEH_MARBUTA, "ه")
    return text


def fix_zwnj(text: str) -> str:
    """Insert ZWNJ (نیم‌فاصله) where Persian orthography requires it."""
    if not text:
        return text
    # Verbs: می / نمی + stem.
    text = _VERB_PREFIX_RE.sub(r"\1" + ZWNJ + r"\2", text)
    # Suffixes.
    text = _HA_RE.sub(r"\1" + ZWNJ + r"\2", text)
    text = _TAR_RE.sub(r"\1" + ZWNJ + r"\2", text)
    # Prefix بی + word.
    text = _BI_RE.sub(r"بی" + ZWNJ + r"\1", text)
    # Prefix هم + known compound only (conjunction هم stays separate).
    text = _HAM_RE.sub(r"هم" + ZWNJ + r"\1", text)
    # Lexicalized compounds.
    for wrong, right in _COMPOUNDS:
        text = text.replace(wrong, right)
    return text


def fix_persian_punctuation(text: str) -> str:
    """Normalize punctuation to Persian forms and fix spacing."""
    if not text:
        return text
    # Em/en dashes have no place in Persian prose — use ،.
    text = text.replace("—", "،").replace("–", "،")
    # ASCII punctuation -> Persian.
    text = text.replace(",", "،").replace(";", "؛").replace("?", "؟")
    # ASCII double quotes -> Persian guillemets.
    text = _QUOTE_RE.sub(r"«\1»", text)
    # Spacing: no space before ،؛.؟!:», one space after ،؛؟!.
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _SPACE_AFTER_PUNCT_RE.sub(r"\1 ", text)
    # Dot: add missing space only before Persian letters (protects 3.x / 3.12).
    text = _FA_AFTER_DOT_RE.sub(r". \1", text)
    # Collapse accidental double spaces (common AI artifact), keep newlines.
    text = _MULTI_SPACE_RE.sub(" ", text)
    return text


def de_ai_persian(text: str) -> str:
    """Strip bureaucratic/AI tells, keeping the meaning."""
    if not text:
        return text
    text = _MIBASHAD_RE.sub("است", text)
    text = _MIGARDAD_RE.sub("می‌شود", text)
    # Standalone گردد (e.g. تضمین گردد) -> شود.
    text = _GARDAD_RE.sub("شود", text)
    text = _BE_SHOMAR_RE.sub("است", text)
    text = _MAHSOOB_RE.sub("است", text)
    text = _DAR_RASTAYE_RE.sub("برای", text)
    text = _LAZEM_RE.sub("", text)
    text = _SHAYAN_RE.sub("", text)
    text = _AHAMIAT_RE.sub("", text)
    # Clean up gaps left by removals.
    text = re.sub(r"\s+([،؛.؟!])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def humanize_persian(text: str) -> str:
    """Run the full cleanup pipeline."""
    if not text:
        return text
    text = fix_arabic_glyphs(text)
    text = de_ai_persian(text)
    text = fix_zwnj(text)
    text = fix_persian_punctuation(text)
    return text.strip()
