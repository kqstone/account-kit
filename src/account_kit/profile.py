from __future__ import annotations

from datetime import date
from typing import Optional

from account_kit.i18n import account_error, t

ALLOWED_GENDERS = {"male", "female"}


class BirthError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(t(code))


def parse_birth_year_month(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        parsed = date(value.year, value.month, 1)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            if len(text) == 7:
                parsed = date.fromisoformat(f"{text}-01")
            else:
                raw = date.fromisoformat(text[:10])
                parsed = date(raw.year, raw.month, 1)
        except ValueError as exc:
            raise BirthError("BIRTH_FORMAT_INVALID") from exc
    today = date.today().replace(day=1)
    if parsed > today:
        raise BirthError("BIRTH_IN_FUTURE")
    if parsed.year < 1900:
        raise BirthError("BIRTH_INVALID")
    return parsed


def format_birth_year_month(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%Y-%m")


def birth_year_month_to_date(value: Optional[str]) -> Optional[date]:
    try:
        return parse_birth_year_month(value)
    except BirthError as exc:
        raise account_error(400, exc.code) from exc
    except ValueError as exc:
        raise account_error(400, "BIRTH_INVALID") from exc


def normalize_gender(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if value not in ALLOWED_GENDERS:
        raise account_error(400, "GENDER_INVALID")
    return value
