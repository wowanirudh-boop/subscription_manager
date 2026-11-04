"""Text helpers: normalisation, date/amount spotting, evidence verification.

The evidence check is what enforces D5 ("never assert a value it did not read"):
a model-proposed value is only kept as *confirmed* if the model's quoted
sentence really occurs in the email and that sentence really contains the value.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from html.parser import HTMLParser
from typing import Iterable, Optional

_WS = re.compile(r"\s+")

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"

_DATE_PATTERNS = [
    # 5 March 2026 / 5th Mar, 2026
    re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON},?\s+(\d{{4}})\b", re.I),
    # March 5, 2026 / Mar 5th 2026
    re.compile(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I),
    # 2026-03-05
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    # 05/03/2026 or 05-03-2026 or 05.03.2026 (ambiguous day/month order)
    re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b"),
]

CURRENCY_SYMBOLS = {
    "₹": "INR",
    "rs.": "INR",
    "rs": "INR",
    "inr": "INR",
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "sgd": "SGD",
    "aed": "AED",
}
_AMOUNT = re.compile(
    r"(?P<cur>₹|rs\.?|inr|us\$|\$|€|£|usd|eur|gbp|sgd|aed)\s?(?P<num>\d+(?:,\d{2,3})*(?:\.\d{1,2})?(?![\d]))"
    r"|(?P<num2>\d+(?:,\d{2,3})*(?:\.\d{1,2})?(?![\d]))\s?(?P<cur2>inr|usd|eur|gbp|sgd|aed)\b",
    re.I,
)


def norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def contains_quote(haystack: str, quote: str) -> bool:
    """Whitespace- and case-insensitive substring test."""
    q = norm(quote)
    return bool(q) and q in norm(haystack)


def find_dates(text: str) -> list[tuple[dt.date, str]]:
    """All (date, surface-text) pairs in ``text``.

    Numeric dd/mm/yyyy is ambiguous: India writes day-first, many foreign
    merchants write month-first. Both readings are returned when valid; the
    verifier accepts the model's value if it matches either, and the ambiguity is
    a known limitation reported by the scorer through field mismatches.
    """
    out: list[tuple[dt.date, str]] = []
    for i, pat in enumerate(_DATE_PATTERNS):
        for m in pat.finditer(text):
            g = m.groups()
            cands: list[tuple[int, int, int]] = []
            if i == 0:
                cands = [(int(g[2]), MONTHS[g[1].lower().rstrip(".")], int(g[0]))]
            elif i == 1:
                cands = [(int(g[2]), MONTHS[g[0].lower().rstrip(".")], int(g[1]))]
            elif i == 2:
                cands = [(int(g[0]), int(g[1]), int(g[2]))]
            else:
                a, b, y = int(g[0]), int(g[1]), int(g[2])
                cands = [(y, b, a), (y, a, b)]  # day-first first (India default)
            for y, mo, d in cands:
                try:
                    date = dt.date(y, mo, d)
                except ValueError:
                    continue
                if (date, m.group(0)) not in out:
                    out.append((date, m.group(0)))
    return out


def parse_amount_str(s: str) -> float:
    return float(s.replace(",", ""))


def find_amounts(text: str) -> list[tuple[float, Optional[str], str]]:
    """All (amount, ISO currency or None, surface-text) in ``text``."""
    out = []
    for m in _AMOUNT.finditer(text):
        num = m.group("num") or m.group("num2")
        cur = (m.group("cur") or m.group("cur2") or "").lower()
        out.append((parse_amount_str(num), CURRENCY_SYMBOLS.get(cur), m.group(0)))
    return out


def quote_supports_date(quote: str, value: dt.date) -> Optional[str]:
    """Return the surface text in ``quote`` that expresses ``value``, else None."""
    for d, surface in find_dates(quote):
        if d == value:
            return surface
    return None


def quote_supports_amount(quote: str, value: float) -> Optional[str]:
    for amt, _cur, surface in find_amounts(quote):
        if abs(amt - value) < 0.005:
            return surface
    # bare number without a currency marker
    for m in re.finditer(r"\d+(?:,\d{2,3})*(?:\.\d{1,2})?(?![\d])", quote):
        if abs(parse_amount_str(m.group(0)) - value) < 0.005:
            return m.group(0)
    return None


def quote_supports_currency(quote: str, value: str) -> bool:
    return any(cur == value.upper() for _a, cur, _s in find_amounts(quote) if cur)


# ---- HTML to text ------------------------------------------------------------------


class _Stripper(HTMLParser):
    _BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._href: Optional[str] = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        if tag == "a":
            self._href = dict(attrs).get("href")
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1
        if tag == "a" and self._href:
            if self._href.startswith("http"):
                self.parts.append(f" ({self._href})")
            self._href = None
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    p = _Stripper()
    p.feed(raw)
    text = html.unescape("".join(p.parts))
    lines = [_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def truncate_tokens(text: str, max_tokens: int = 1500) -> str:
    """R4: body truncated to ~1,500 tokens. Uses ~4 chars/token (approximation)."""
    limit = max_tokens * 4
    return text if len(text) <= limit else text[:limit]


def sentences(text: str) -> Iterable[str]:
    for ln in text.splitlines():
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", ln):
            s = s.strip()
            if s:
                yield s
