"""Verify BIS lifecycle status against the BIS e-Sale catalogue.

The local catalogue can lag BIS withdrawals. This service checks the official
search result for an exact BIS designation and keeps a short in-process cache
to avoid repeating requests for duplicate input rows.
"""

from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import re
from threading import Lock
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class _VisibleTextParser(HTMLParser):
    """Collect visible page text while ignoring scripts and styles."""

    _IGNORED = {"head", "script", "style", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._IGNORED:
            self._ignored_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data):
        if self._ignored_depth:
            return
        value = " ".join(str(data or "").split())
        if value:
            self.parts.append(value)


class BISStatusService:
    SEARCH_URL = "https://standardsbis.bsbedge.com/BIS_SearchStandard.aspx"
    CACHE_TTL_SECONDS = 1800
    CACHE_MAX_ENTRIES = 2048
    MAX_WORKERS = 6
    _cache = {}
    _cache_lock = Lock()

    @classmethod
    def verify_rows(cls, rows):
        """Return official lifecycle results keyed by each prepared request."""
        queries = {}
        for row in rows or []:
            if str(row.get("requested_sdo_name") or "").strip().upper() not in {
                "BIS",
                "IS",
            }:
                continue
            query = cls._search_number(row)
            if query:
                queries.setdefault(query, []).append(row["request_key"])

        if not queries:
            return {}

        with ThreadPoolExecutor(max_workers=min(cls.MAX_WORKERS, len(queries))) as pool:
            results = dict(zip(queries, pool.map(cls._lookup, queries)))

        return {
            request_key: results[query]
            for query, request_keys in queries.items()
            for request_key in request_keys
        }

    @staticmethod
    def _search_number(row):
        identity = row.get("identity") or {}
        designation = str(identity.get("core_number") or "").strip()
        if not designation or re.search(r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", designation, re.I):
            return None

        prefix = "IS"
        if str(identity.get("full_base") or "").upper().startswith("IS SP "):
            prefix = "SP"
            designation = designation.removeprefix("SP ")

        parts = [prefix, designation]
        qualifier = str(identity.get("qualifier") or "")
        qualifier_match = re.fullmatch(r"(?i)(PART|SECTION|CHAPTER):(\w+)", qualifier)
        if qualifier_match:
            label = {
                "PART": "Part",
                "SECTION": "Sec",
                "CHAPTER": "Chapter",
            }[qualifier_match.group(1).upper()]
            parts.extend((":", label, qualifier_match.group(2)))

        year = identity.get("year")
        if year:
            parts.extend((":", str(year)))
        return " ".join(parts)

    @classmethod
    def _lookup(cls, standard_number):
        now = time.monotonic()
        with cls._cache_lock:
            cached = cls._cache.get(standard_number)
            if cached and cached[0] > now:
                return cached[1]

        result = cls._fetch_status(standard_number)
        ttl = cls.CACHE_TTL_SECONDS if result["verified"] else 60
        with cls._cache_lock:
            if len(cls._cache) >= cls.CACHE_MAX_ENTRIES:
                cls._cache.pop(next(iter(cls._cache)))
            cls._cache[standard_number] = (now + ttl, result)
        return result

    @classmethod
    def _fetch_status(cls, standard_number):
        query = urlencode({"Standard_Number": standard_number, "id": "0"})
        request = Request(
            f"{cls.SEARCH_URL}?{query}",
            headers={"User-Agent": "StandardsIntelligence/1.0"},
        )
        try:
            with urlopen(request, timeout=8) as response:
                parser = _VisibleTextParser()
                parser.feed(response.read().decode("utf-8", "replace"))
        except Exception:
            return {"status": "STATUS UNVERIFIED", "superseded_by": None, "verified": False}

        text = " ".join(parser.parts)
        if not text.strip():
            return {"status": "STATUS UNVERIFIED", "superseded_by": None, "verified": False}
        status_matches = list(
            re.finditer(
                r"\bStatus\s*:\s*(WITHDRAWN|WTHDRAWN|SUPERSEDED|INACTIVE|DISCONTINUED|ACTIVE)\b",
                text,
                re.IGNORECASE,
            )
        )
        if not status_matches:
            if re.search(r"(?i)\b(?:no\s+(?:matching\s+)?records?|no\s+standards?\s+found)\b", text):
                return {"status": "NOT FOUND", "superseded_by": None, "verified": True}
            return {"status": "STATUS UNVERIFIED", "superseded_by": None, "verified": False}

        status = status_matches[0].group(1).upper()
        superseded_by = None
        result_start = text.rfind("You Searched for", 0, status_matches[0].start())
        result_end = text.find("You Searched for", status_matches[0].end())
        result_text = text[
            result_start if result_start >= 0 else 0 :
            result_end if result_end >= 0 else len(text)
        ]
        price_match = re.search(
            r"(?i)\bPrice(?:\s+within\s+India)?\s*:\s*(?:₹|INR)\s*([\d,]+(?:\.\d{1,2})?)",
            result_text,
        )
        price = (
            float(price_match.group(1).replace(",", ""))
            if price_match
            else None
        )
        replacement = re.search(
            r"(?is)\b(?:Superseeded|Superseded)\s+by\s*:\s*(.*?)"
            r"(?=\s+(?:Status|No\.?\s+of\s+Amendments?|Price\s+(?:within|outside)\s+India|Technical\s+Committee)\s*:|$)",
            result_text,
        )
        if replacement:
            superseded_by = re.sub(r"\s+", " ", replacement.group(1)).strip(" \t\r\n:;|") or None
        return {
            "status": status,
            "superseded_by": superseded_by,
            "verified": True,
            "price": price,
        }
