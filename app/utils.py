from __future__ import annotations

import re
import uuid
from pathlib import Path


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ").replace("\u00a0", " ")
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def one_line(text: str | None, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", clean_text(text))
    if limit and len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def normalize_for_compare(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("«", '"').replace("»", '"')
    value = re.sub(r"[^0-9a-zа-я\" ]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def unique_preserve(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        v = one_line(value, 700)
        key = v.lower()
        if v and key not in seen:
            seen.add(key)
            out.append(v)
    return out


def safe_filename(name: str) -> str:
    name = Path(name or "file").name.strip()
    name = re.sub(r"[^A-Za-zА-Яа-яЁё0-9._()\-\s]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or f"file_{uuid.uuid4().hex}"


def find_context_line(text: str, start: int, end: int, max_len: int = 600) -> str:
    left = text.rfind("\n", 0, start)
    right = text.find("\n", end)
    if left < 0:
        left = max(0, start - 160)
    if right < 0:
        right = min(len(text), end + 160)
    return one_line(text[left:right], max_len)
