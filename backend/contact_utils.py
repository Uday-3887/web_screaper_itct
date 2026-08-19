from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)")
METRIC_WORDS = ("followers", "following", "likes", "views", "reviews", "posts", "members", "ratings")


def clean(value: str | None) -> str:
    return " ".join((value or "").replace("\u200b", " ").split())


def unique(values) -> list[str]:
    output, seen = [], set()
    for value in values:
        value = clean(str(value)).strip(" ,.;|()[]")
        key = value.casefold()
        if value and key not in seen:
            seen.add(key); output.append(value)
    return output


def root_host(url: str) -> str:
    return urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")


def unwrap_redirect(url: str) -> str:
    url = clean(url)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("u", "url", "q", "target", "dest"):
        if query.get(key):
            candidate = unquote(query[key][0])
            if urlparse(candidate).scheme in {"http", "https"}:
                return candidate
    return url


def emails_from_text(text: str) -> list[str]:
    values = unique(EMAIL_RE.findall(text or ""))
    return [value for value in values if not re.search(r"\.(png|jpg|jpeg|gif|webp|svg)$", value, re.I)]


def phones_from_text(text: str) -> list[str]:
    values = []
    for match in PHONE_RE.finditer(text or ""):
        candidate = clean(match.group(0))
        digits = re.sub(r"\D", "", candidate)
        after = text[match.end():match.end() + 25].casefold()
        if not 8 <= len(digits) <= 15:
            continue
        if any(word in after for word in METRIC_WORDS):
            continue
        if re.fullmatch(r"20\d{2}[\s./-]\d{1,2}[\s./-]\d{1,2}", candidate):
            continue
        values.append(candidate)
    return unique(values)


def normalize_company(value: str) -> str:
    value = re.sub(r"\b(private|pvt|limited|ltd|llp|incorporated|inc|company|co)\b", " ", clean(value), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def platform_for_social(url: str) -> str:
    return {
        "facebook.com": "Facebook",
        "instagram.com": "Instagram",
        "linkedin.com": "LinkedIn",
    }.get(root_host(url), "")


def is_company_social_url(url: str) -> bool:
    parsed = urlparse(url)
    host = root_host(url)
    parts = [part.casefold() for part in parsed.path.split("/") if part]
    if parsed.scheme not in {"http", "https"}:
        return False
    if host == "linkedin.com":
        return len(parts) >= 2 and parts[0] in {"company", "school"}
    if host == "instagram.com":
        return bool(parts) and parts[0] not in {"p", "reel", "reels", "stories", "explore", "accounts"}
    if host == "facebook.com":
        return bool(parts) and parts[0] not in {"login", "watch", "reel", "share", "groups", "events", "marketplace"}
    return False

