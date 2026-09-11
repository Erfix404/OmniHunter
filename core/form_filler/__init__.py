from core.form_filler.base_filler import BaseFormFiller
from core.form_filler.ponisha_filler import PonishaFormFiller
from core.form_filler.parscoders_filler import ParscodersFormFiller


def get_form_filler(platform: str) -> BaseFormFiller:
    """Factory function returning the appropriate BaseFormFiller subclass for platform."""
    norm = (platform or "").strip().lower()
    if norm == "ponisha":
        return PonishaFormFiller()
    elif norm == "parscoders":
        return ParscodersFormFiller()
    else:
        raise ValueError(f"Unsupported form filler platform: '{platform}'")


__all__ = [
    "BaseFormFiller",
    "PonishaFormFiller",
    "ParscodersFormFiller",
    "get_form_filler",
]
