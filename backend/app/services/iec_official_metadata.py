"""Verified IEC Webstore lifecycle and committee metadata overrides.

The local IEC catalogue feed contains records whose dates are publication
dates rather than IEC designations, and several legacy records have stale
ACTIVE flags or no committee assignments. Keep public Webstore facts in one
small, source-linked registry and apply them by normalized IEC identity.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class IECOfficialMetadata:
    designation: str
    title: str
    publication_year: int
    tc: str
    tc_description: str
    url: str
    lifecycle_status: str = "ACTIVE"
    lifecycle_detail: str | None = None
    price: float | None = None
    currency: str | None = None


_CATALOG = {
    # IEC Webstore marks the 2002 edition withdrawn on 2026-07-09. The local
    # mirror still labels it ACTIVE, so use the verified lifecycle metadata
    # when deciding whether it can be included in a series expansion.
    "600764": IECOfficialMetadata(
        designation="IEC 60076-4:2002",
        title="Power transformers - Part 4: Guide to the lightning impulse and switching impulse testing - Power transformers and reactors",
        publication_year=2002,
        tc="TC 14",
        tc_description="Power transformers",
        url="https://webstore.iec.ch/en/publication/602",
        lifecycle_status="WITHDRAWN",
        lifecycle_detail=(
            "IEC Webstore lists this edition as withdrawn on 2026-07-09; "
            "a newer edition is available."
        ),
    ),
    # A publication date of 2001 is rendered by IEC as the 1994 edition with
    # amendments 1 and 2, not as a standalone "IEC 60168:2001" edition.
    "60168": IECOfficialMetadata(
        designation="IEC 60168:1994+AMD1:1997+AMD2:2000 CSV",
        title="Tests on indoor and outdoor post insulators of ceramic material or glass for systems with nominal voltages greater than 1000 V",
        publication_year=2001,
        tc="TC 36",
        tc_description="Insulators",
        url="https://webstore.iec.ch/en/publication/918",
        price=555.0,
        currency="CHF",
    ),
    "6033111": IECOfficialMetadata(
        designation="IEC 60331-11:1999+AMD1:2009 CSV",
        title="Tests for electric cables under fire conditions - Circuit integrity - Part 11: Apparatus - Fire alone at a flame temperature of at least 750 °C",
        publication_year=2009,
        tc="TC 20",
        tc_description="Electric cables",
        url="https://webstore.iec.ch/en/publication/1468",
        lifecycle_status="WITHDRAWN",
        lifecycle_detail="IEC Webstore lists this publication as withdrawn on 2024-12-31.",
    ),
    "6033211": IECOfficialMetadata(
        designation="IEC 60332-1-1:2004+AMD1:2015 CSV",
        title="Tests on electric and optical fibre cables under fire conditions - Part 1-1: Test for vertical flame propagation for a single insulated wire or cable - Apparatus",
        publication_year=2015,
        tc="TC 20",
        tc_description="Electric cables",
        url="https://webstore.iec.ch/en/publication/22995",
        price=50.0,
        currency="CHF",
    ),
    "611431": IECOfficialMetadata(
        designation="IEC 61143-1:1992+AMD1:1997 CSV",
        title="Electrical measuring instruments - X-t recorders - Part 1: Definitions and requirements",
        publication_year=1998,
        tc="TC 85",
        tc_description="Measuring equipment for electrical and electromagnetic quantities",
        url="https://webstore.iec.ch/en/publication/4567",
        price=460.0,
        currency="CHF",
    ),
    "60724": IECOfficialMetadata(
        designation="IEC 60724:2000+AMD1:2008 CSV",
        title="Short-circuit temperature limits of electric cables with rated voltages of 1 kV (Um = 1,2 kV) and 3 kV (Um = 3,6 kV)",
        publication_year=2008,
        tc="TC 20",
        tc_description="Electric cables",
        url="https://webstore.iec.ch/en/publication/3091",
        price=85.0,
        currency="CHF",
    ),
    "6079411": IECOfficialMetadata(
        designation="IEC 60794-1-1:2023",
        title="Optical fibre cables - Part 1-1: Generic specification - General",
        publication_year=2023,
        tc="TC 86/SC 86A",
        tc_description="Fibres and cables",
        url="https://webstore.iec.ch/en/publication/68873",
    ),
    # 2013 is amendment 1; IEC currently presents the combined 2019 edition.
    "610342": IECOfficialMetadata(
        designation="IEC 61034-2:2005+AMD1:2013+AMD2:2019 CSV",
        title="Measurement of smoke density of cables burning under defined conditions - Part 2: Test procedure and requirements",
        publication_year=2019,
        tc="TC 20",
        tc_description="Electric cables",
        url="https://webstore.iec.ch/en/publication/66136",
    ),
    # 2013 identifies amendment 1, not a standalone edition. IEC currently
    # publishes the combined third edition with both 2013 and 2019 amendments.
    "610341": IECOfficialMetadata(
        designation="IEC 61034-1:2005+AMD1:2013+AMD2:2019 CSV",
        title="Measurement of smoke density of cables burning under defined conditions - Part 1: Test apparatus",
        publication_year=2019,
        tc="TC 20",
        tc_description="Electric cables",
        url="https://webstore.iec.ch/en/publication/66134",
        price=170.0,
        currency="CHF",
    ),
}


class IECOfficialMetadataService:
    """Resolve a verified Webstore record from an IEC designation."""

    @staticmethod
    def identity_key(sdo_name, designation):
        if str(sdo_name or "").strip().upper() != "IEC":
            return None
        value = str(designation or "").strip().upper()
        value = re.sub(r"\s*\([^)]*\)\s*$", "", value)
        value = re.sub(r"^\s*IEC\s*", "", value)
        # Strip an explicit publication year, but retain hyphenated part
        # numbers such as 60331-11 and 60332-1-1.
        # Consolidated publications can contain several edition/amendment
        # years (e.g. :2004+AMD1:2015 CSV). Reduce the whole edition suffix to
        # its base IEC number so the verified consolidated record is matched.
        value = re.sub(r"\s*:\s*(?:19|20)\d{2}.*$", "", value)
        return re.sub(r"[^A-Z0-9]", "", value)

    @classmethod
    def lookup(cls, sdo_name, designation):
        key = cls.identity_key(sdo_name, designation)
        return _CATALOG.get(key)
