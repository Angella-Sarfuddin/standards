"""Verified IEEE lifecycle links for legacy catalogue designations."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class IEEEOfficialReplacement:
    replacement_standardno: str
    replacement_year: int
    replacement_designation: str
    source_url: str
    source_year: int
    relationship_type: str
    status: str = "SUPERSEDED"


# IEEE SA lists the legacy records as superseded/inactive and identifies the
# current replacement standard. Resolve through active records in our own
# catalogue so price and committee data come from the actual replacement row.
_REPLACEMENTS = {
    "8021AD": IEEEOfficialReplacement(
        replacement_standardno="IEEE 802.1Q",
        replacement_year=2022,
        replacement_designation="IEEE 802.1Q:2022",
        source_url="https://standards.ieee.org/ieee/802.1ad/3374/",
        source_year=2005,
        relationship_type="INCORPORATED_INTO",
    ),
    "8021AG": IEEEOfficialReplacement(
        replacement_standardno="IEEE 802.1Q",
        replacement_year=2022,
        replacement_designation="IEEE 802.1Q:2022",
        source_url="https://standards.ieee.org/ieee/802.1ag/3597/",
        source_year=2007,
        relationship_type="INCORPORATED_INTO",
    ),
    "8021W": IEEEOfficialReplacement(
        replacement_standardno="IEEE 802.1D",
        replacement_year=2004,
        replacement_designation="IEEE 802.1D:2004",
        source_url="https://standards.ieee.org/ieee/802.1w/1046/",
        source_year=2001,
        relationship_type="SUPERSEDED_BY",
    ),
    "13132": IEEEOfficialReplacement(
        replacement_standardno="IEEE C62.82.2",
        replacement_year=2022,
        replacement_designation="IEEE C62.82.2:2022",
        source_url="https://standards.ieee.org/ieee/1313.2/1995/",
        source_year=1999,
        relationship_type="SUPERSEDED_BY",
    ),
}


class IEEEOfficialMetadataService:
    """Resolve verified edition-scoped IEEE lifecycle relationships."""

    @staticmethod
    def identity_key(sdo_name, designation):
        if str(sdo_name or "").strip().upper() != "IEEE":
            return None
        value = str(designation or "").strip().upper()
        value = re.sub(r"\s*\([^)]*\)\s*$", "", value)
        value = re.sub(r"^\s*IEEE(?:\s+STD)?\s*", "", value)
        value = re.sub(r"\s*[:-]\s*(?:19|20)\d{2}\s*$", "", value)
        return re.sub(r"[^A-Z0-9]", "", value)

    @classmethod
    def lookup(cls, sdo_name, designation):
        replacement = _REPLACEMENTS.get(
            cls.identity_key(sdo_name, designation)
        )
        if replacement is None:
            return None

        designation_value = re.sub(
            r"\s*\([^)]*\)\s*$",
            "",
            str(designation or "").strip(),
        )
        source_year = re.search(
            r"\s*[:-]\s*((?:19|20)\d{2})\s*$",
            designation_value,
        )
        if (
            source_year
            and int(source_year.group(1)) != replacement.source_year
        ):
            return None

        return replacement
