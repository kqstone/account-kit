from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException

ALLOWED_GENDERS = {"male", "female"}


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
            raise ValueError("出生年月格式无效") from exc
    today = date.today().replace(day=1)
    if parsed > today:
        raise ValueError("出生年月不能晚于当前月份")
    if parsed.year < 1900:
        raise ValueError("出生年月无效")
    return parsed


def format_birth_year_month(value: Optional[date]) -> Optional[str]:
    if value is None:
        return None
    return value.strftime("%Y-%m")


def birth_year_month_to_date(value: Optional[str]) -> Optional[date]:
    try:
        return parse_birth_year_month(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def normalize_gender(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if value not in ALLOWED_GENDERS:
        raise HTTPException(status_code=400, detail="性别无效")
    return value
