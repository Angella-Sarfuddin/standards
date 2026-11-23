"""Column projections for catalogue search queries.

Search selection and enrichment only need a subset of each table. Loading
fewer columns cuts payload size without changing filters or match rules.
"""

from sqlalchemy.orm import load_only

from app.models.standard import Standard
from app.models.standard_master import StandardMaster

STANDARD_SEARCH_COLUMNS = (
    Standard.id,
    Standard.Standard_id,
    Standard.sdo_id,
    Standard.status_id,
    Standard.standardno,
    Standard.title,
    Standard.url,
    Standard.display_stdNo,
    Standard.status,
    Standard.esales,
    Standard.stdNo_normalized,
)

STANDARD_MASTER_SEARCH_COLUMNS = (
    StandardMaster.id,
    StandardMaster.Standard_id,
    StandardMaster.sdo_id,
    StandardMaster.standardno,
    StandardMaster.standardyear,
    StandardMaster.title,
    StandardMaster.url,
    StandardMaster.display_stdNo,
    StandardMaster.status_id,
    StandardMaster.status,
    StandardMaster.recent,
    StandardMaster.BSBESales,
    StandardMaster.BSBInternal,
    StandardMaster.BSBSubscription,
    StandardMaster.DocumentAvailability,
)


def standard_search_options():
    return load_only(*STANDARD_SEARCH_COLUMNS)


def standard_master_search_options():
    return load_only(*STANDARD_MASTER_SEARCH_COLUMNS)
