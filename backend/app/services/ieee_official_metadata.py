"""Verified IEEE lifecycle links for legacy catalogue designations."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class IEEEOfficialReplacement:
    replacement_standardno: str
    replacement_year: int
    replacement_designation: str
    source_url: str
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
    ),
    "8021AG": IEEEOfficialReplacement(
        replacement_standardno="IEEE 802.1Q",
        replacement_year=2022,
        replacement_designation="IEEE 802.1Q:2022",
        source_url="https://standards.ieee.org/ieee/802.1ag/3597/",
    ),
    "8021W": IEEEOfficialReplacement(
        replacement_standardno="IEEE 802.1Q",
        replacement_year=2022,
        replacement_designation="IEEE 802.1Q:2022",
        source_url="https://standards.ieee.org/ieee/802.1w/1046/",
    ),
    "13132": IEEEOfficialReplacement(
        replacement_standardno="IEEE C62.82.2",
        replacement_year=2022,
        replacement_designation="IEEE C62.82.2:2022",
        source_url="https://standards.ieee.org/ieee/1313.2/1995/",
    ),
}


class IEEEOfficialMetadataService:
    """Find an official successor for a legacy IEEE standard identity."""

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
        return _REPLACEMENTS.get(cls.identity_key(sdo_name, designation))
