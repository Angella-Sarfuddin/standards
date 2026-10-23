"""Read current ISO deliverable metadata from ISO's openly licensed feed."""

import json
import threading
import time
from urllib.request import Request, urlopen

from app.utils.standard_identity import normalize_identity_core, parse_identity


class ISOOpenDataService:
    """Serve ISO metadata from an indexed cache without blocking searches."""

    # ISO's open metadata feed contains publication and committee details but
    # no catalogue prices. Keep verified prices for official published
    # editions here, keyed by (SDO, normalized core, year); never reuse a draft
    # or withdrawn local record's amount for a synthetic current-edition row.
    OFFICIAL_PRICES = {
        ("ISO", "17025", 2017): {
            "price": 179.0,
            "currency": "CHF",
            "source_url": "https://committee.iso.org/standard/66912.html?browse=tc",
        },
        ("ISO/IEC", "17025", 2017): {
            "price": 179.0,
            "currency": "CHF",
            "source_url": "https://committee.iso.org/standard/66912.html?browse=tc",
        },
        ("ISO", "9001", 2026): {
            "price": 196.0,
            "currency": "CHF",
            "source_url": "https://www.iso.org/standard/9001",
        },
    }
    VERIFIED_CURRENT_RELEASES = {
        ("ISO", "9001"): {
            "id": 88464,
            "reference": "ISO 9001:2026",
            "title": {
                "en": "Quality management systems — Requirements",
            },
            "ownerCommittee": "ISO/TC 176/SC 2",
            "currentStage": "6060",
            "publicationDate": "2026-09-16",
            "edition": 6,
        },
    }

    URL = (
        "https://isopublicstorageprod.blob.core.windows.net/opendata/"
        "_latest/iso_deliverables_metadata/json/"
        "iso_deliverables_metadata.jsonl"
    )
    CACHE_SECONDS = 24 * 60 * 60
    FAILURE_CACHE_SECONDS = 5 * 60
    SDOS = ("ISO/IEC", "ISO/TS", "ISO/TR", "ISO")
    _lock = threading.Lock()
    _records = None
    _index = None
    _loaded_at = 0
    _refreshing = False

    @classmethod
    def metadata_available(cls):
        """Whether a usable official snapshot is present in memory."""
        return cls._get_records() is not None

    @classmethod
    def latest_published(cls, sdo_name, designation):
        """Return the newest published ISO edition for this part, if known."""
        sdo = str(sdo_name or "").strip().upper()
        if sdo not in {"ISO", "ISO/IEC", "ISO/TS", "ISO/TR"}:
            return None

        requested = parse_identity(sdo, designation)
        requested_core = normalize_identity_core(
            requested.get("core_number") or ""
        )
        requested_qualifier = str(requested.get("qualifier") or "")
        if not requested_core:
            return None

        records = cls._get_records()  # Starts a refresh in the background when needed.
        with cls._lock:
            index = cls._index
        # Also handles callers that provide a record snapshot directly (for
        # example, an in-process preload) before the background refresh builds
        # the shared index.
        if index is None and records is not None:
            index = cls._build_index(records)
        record = (index or {}).get(
            (sdo, requested_core, requested_qualifier)
        )
        if record is not None:
            return record
        # Keep verified current releases available when ISO's open-data feed
        # is still loading or temporarily unreachable after a process restart.
        if not requested_qualifier:
            return cls.VERIFIED_CURRENT_RELEASES.get(
                (sdo, requested_core)
            )
        return None

    @classmethod
    def official_price(cls, sdo_name, designation):
        """Return a verified official price for a published ISO edition."""
        sdo = str(sdo_name or "").strip().upper()
        identity = parse_identity(sdo, designation)
        core = normalize_identity_core(
            identity.get("core_number") or ""
        )
        year = identity.get("year")
        if not sdo or not core or year is None:
            return None
        return cls.OFFICIAL_PRICES.get((sdo, core, int(year)))

    @classmethod
    def _get_records(cls):
        """Return the current snapshot immediately and refresh it off-thread."""
        now = time.monotonic()
        with cls._lock:
            cache_seconds = (
                cls.CACHE_SECONDS if cls._records is not None else cls.FAILURE_CACHE_SECONDS
            )
            stale = not cls._loaded_at or now - cls._loaded_at >= cache_seconds
            if stale and not cls._refreshing:
                cls._refreshing = True
                threading.Thread(
                    target=cls._refresh_records,
                    name="iso-open-data-refresh",
                    daemon=True,
                ).start()
            return cls._records

    @classmethod
    def _refresh_records(cls):
        try:
            request = Request(
                cls.URL,
                headers={"User-Agent": "StandardsIntelligence/1.0"},
            )
            with urlopen(request, timeout=12) as response:
                records = [
                    json.loads(line)
                    for line in response.read().decode("utf-8").splitlines()
                    if line.strip()
                ]
            index = cls._build_index(records)
        except Exception:
            # Keep serving the last successful snapshot across transient errors.
            with cls._lock:
                cls._loaded_at = time.monotonic()
                cls._refreshing = False
            return

        with cls._lock:
            cls._records = records
            cls._index = index
            cls._loaded_at = time.monotonic()
            cls._refreshing = False

    @classmethod
    def _build_index(cls, records):
        """Keep only the newest published record for each ISO part identity."""
        index = {}
        for record in records:
            if (
                str(record.get("currentStage") or "") != "6060"
                or record.get("supplementType")
            ):
                continue
            reference = str(record.get("reference") or "").strip()
            upper_reference = reference.upper()
            for sdo in cls.SDOS:
                if not upper_reference.startswith(sdo):
                    continue
                identity = parse_identity(sdo, reference)
                core = normalize_identity_core(identity.get("core_number") or "")
                if not core:
                    continue
                qualifier = str(identity.get("qualifier") or "")
                key = (sdo, core, qualifier)
                previous = index.get(key)
                record_rank = (
                    str(record.get("publicationDate") or ""),
                    int(record.get("edition") or 0),
                )
                if previous is None or record_rank > previous[0]:
                    index[key] = (record_rank, record)
        return {key: value[1] for key, value in index.items()}
