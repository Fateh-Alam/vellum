"""Pure helpers for canonical and human-readable tag segments."""

from __future__ import annotations

import re
import unicodedata


ORDER_PREFIX = re.compile(r"^(?:\d{1,3}|[A-Z])(?:[._\- ]+)(?=\S)", re.IGNORECASE)
WHITESPACE = re.compile(r"\s+")
ANKING_CONTAINER = re.compile(
    r"^#?AK_(?:Step\d?|MCAT|PANCE|Other).*?(?:_v\d+)?$", re.IGNORECASE
)


def split_hierarchical_tag(tag: str) -> tuple[str, ...]:
    return tuple(segment.strip() for segment in tag.split("::") if segment.strip())


def match_key(segment: str) -> str:
    value = unicodedata.normalize("NFKC", segment).strip()
    value = value.lstrip("#")
    value = value.replace("_", " ")
    return WHITESPACE.sub(" ", value).casefold()


def source_key(segment: str) -> str:
    """Normalize common source-root spelling variants without version pinning."""

    key = match_key(segment)
    compact = re.sub(r"[^a-z0-9]+", "", key)
    if compact in {"bb", "bnb", "boardsandbeyond"}:
        return "bnb"
    if compact.startswith("sketchy"):
        return "sketchy"
    return compact


def canonical_segment(segment: str) -> str:
    """Return a stable identifier component independent of display renames."""

    value = unicodedata.normalize("NFKC", segment).strip().lstrip("#")
    value = ORDER_PREFIX.sub("", value)
    value = value.replace("_", " ")
    return WHITESPACE.sub(" ", value).strip().casefold()


def display_segment(segment: str) -> str:
    value = unicodedata.normalize("NFKC", segment).strip().lstrip("#")
    value = ORDER_PREFIX.sub("", value)
    value = value.replace("_", " ")
    return WHITESPACE.sub(" ", value).strip()


def is_anking_container(segment: str) -> bool:
    return bool(ANKING_CONTAINER.fullmatch(segment.strip()))


def is_probably_utility_root(segment: str) -> bool:
    key = match_key(segment)
    return (
        segment.startswith(("$", "^", "!"))
        or key.startswith(("ankingadds", "ankingupdates", "ankihub deleted"))
        or key
        in {
            "flag these cards",
            "marked",
            "duplicate",
            "only step",
            "potential duplicate",
        }
    )
