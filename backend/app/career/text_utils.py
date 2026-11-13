"""Text helpers: section detection, bullet extraction, evidence snippets, date ranges."""

from __future__ import annotations

import re
from datetime import UTC, datetime

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "professional summary", "profile", "objective", "about me", "career objective"),
    "experience": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history"),
    "education": ("education", "academic background", "academics", "qualifications"),
    "skills": ("skills", "technical skills", "key skills", "core competencies", "technologies",
               "skills summary"),
    "projects": ("projects", "personal projects", "key projects", "academic projects"),
    "certifications": ("certifications", "certificates", "licenses", "licenses and certifications"),
    "achievements": ("achievements", "accomplishments", "awards", "honors", "awards and achievements"),
}
_HEADING_TO_SECTION = {a: k for k, v in SECTION_ALIASES.items() for a in v}

BULLET = re.compile(r"^\s*(?:[-*•▪●‣◦–]|\d+[.)])\s+")
YEAR = r"(?:19|20)\d{2}"
MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
RANGE = re.compile(
    rf"(?:(?:{MONTH})\s+)?({YEAR})\s*(?:-|–|—|to)\s*(?:(?:{MONTH})\s+)?({YEAR}|present|current|now|till date)",
    re.IGNORECASE,
)


def heading_of(line: str) -> str | None:
    cleaned = re.sub(r"[:\-–—_=#*\s]+$", "", line.strip().lower())
    cleaned = re.sub(r"^[#*\s]+", "", cleaned)
    if len(cleaned) > 40:
        return None
    return _HEADING_TO_SECTION.get(cleaned)


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "header"
    for line in text.splitlines():
        h = heading_of(line)
        if h:
            current = h
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def bullets_of(block: str) -> list[str]:
    out = []
    for line in block.splitlines():
        if BULLET.match(line):
            out.append(BULLET.sub("", line).strip())
    return out


def evidence_snippet(text: str, match: re.Match[str], width: int = 160) -> str:
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    line = text[start : end if end != -1 else len(text)].strip()
    line = BULLET.sub("", line)
    if len(line) <= width:
        return line
    mid = match.start() - start
    lo = max(0, mid - width // 2)
    return ("…" if lo else "") + line[lo : lo + width].strip() + "…"


def parse_year(value: str, now: datetime | None = None) -> int:
    if value.lower() in {"present", "current", "now", "till date"}:
        return (now or datetime.now(UTC)).year
    return int(value)


def years_from_ranges(text: str, now: datetime | None = None) -> float | None:
    """Union of year ranges (so overlapping jobs are not double counted)."""
    intervals = []
    for m in RANGE.finditer(text):
        start, end = int(m.group(1)), parse_year(m.group(2), now)
        if 1970 <= start <= end <= (now or datetime.now(UTC)).year + 1:
            intervals.append((start, end))
    if not intervals:
        return None
    intervals.sort()
    total, (cur_s, cur_e) = 0, intervals[0]
    for s, e in intervals[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    total += cur_e - cur_s
    return float(total)


def sentence_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]
