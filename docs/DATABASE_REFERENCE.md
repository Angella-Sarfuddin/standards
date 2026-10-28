# Database reference

This document describes SQLAlchemy models and connection setup visible in the repository. It does not claim that a deployed database's DDL, constraints, indexes, or data exactly match these model declarations. No database connection or query was made for this documentation task.

## Configuration and session lifecycle

[`backend/app/database/database.py`](../backend/app/database/database.py) searches for a root `.env` first and `backend/.env` second, selecting the first existing file and loading it with `python-dotenv`. It reads `DATABASE_URL` and raises `ValueError` if that value is unavailable. It creates a SQLAlchemy engine with `pool_pre_ping=True` and `pool_recycle=1800`, then a `SessionLocal` factory. `get_db()` yields a session and closes it in `finally`.

The runtime uses the dialect specified by `DATABASE_URL`; the checked-in example shape is a MySQL/PyMySQL URL. The actual deployed engine and server version are unverified. The application path uses one configured session for search and enrichment, as shown by `DocumentSearchService.__init__()`. `database.py` reads `DATABASE_URL` only.

## ORM model inventory

Models are defined under `backend/app/models/` and inherit from the shared `Base` in `app.database.database`.

| Model | Table | Declared fields |
|---|---|---|
| `Standard` | `standards_search` | `id`, `Standard_id`, `sdo_id`, `status_id`, `standardno`, `title`, `url`, `stdkeyword`, `created_at`, `updated_at`, `display_stdNo`, `search_query`, `created_by`, `updated_by`, `status`, `esales`, `stdNo_normalized` |
| `StandardMaster` | `standards` | `id`, `Standard_id`, `sdo_id`, `standardno`, `standardyear`, `title`, `url`, `display_stdNo`, `status_id`, `status`, `recent`, `mostpopular`, `featured`, `archive`, `BSBESales`, `BSBInternal`, `BSBSubscription`, `DocumentAvailability`, `created_at`, `updated_at` |
| `StandardStatus` | `std_status` | `id`, `status`, `std_show`, `cart_show` |
| `StandardPrice` | `std_prices` | `id`, `std_id`, `formate_id`, `language_id`, `member_price_rate`, `non_member_price_rate`, `sdo_id`, `status`, `ProductSKU` |
| `SDO` | `sdos` | `id`, `sdo_title`, `sdo_fullname`, `access_list`, `url`, `currency_id`, `sdo_shortdesc`, `sdo_detaildesc`, `sdo_banner`, `sdo_uploadfile`, `watermark`, `status`, `promote`, `meta_title`, `meta_keyword`, `meta_description`, `created_by`, `updated_by`, `created_at`, `updated_at`, `structure_data`, `free_structure_data`, `free_meta_title`, `free_meta_description`, `BSBESales`, `BSBInternal`, `BSBSubscription`, `DailyDownloadLimit`, `sdo_shortdesc_detail`, `address0`, `address1`, `address2`, `address3`, `contact_name`, `designation`, `phone`, `pincode`, `email`, `del_format_data`, `other_sdos` |
| `StandardClassification` | `bsbe_std_classifications` | `id`, `classfication_id`, `standard_id`, `sdo_id`, `sdo`, `status` |
| `SDOClassification` | `sdo_classifications` | `id`, `sdo_id`, `agency`, `classification_code`, `description`, `parent_id`, `status` |
| `Currency` | `currencies` | `id`, `currency_title`, `currency_code`, `currency_symbol` |

Source definitions: [`standard.py`](../backend/app/models/standard.py), [`standard_master.py`](../backend/app/models/standard_master.py), [`standard_status.py`](../backend/app/models/standard_status.py), [`standard_price.py`](../backend/app/models/standard_price.py), [`sdo.py`](../backend/app/models/sdo.py), [`standard_classification.py`](../backend/app/models/standard_classification.py), [`sdo_classification.py`](../backend/app/models/sdo_classification.py), and [`currency.py`](../backend/app/models/currency.py).

## Declared constraints and relationships

The model code declares primary keys on each table's `id`. `StandardMaster.Standard_id` is declared `unique=True` and non-null; `sdo_id`, `standardno`, and `status_id` are also declared non-null on that model. Most other fields do not specify additional constraints in these class definitions.

The inspected model classes do not declare SQLAlchemy `ForeignKey` constraints or `relationship()` properties. Fields such as `StandardPrice.std_id`, `StandardClassification.standard_id`, `StandardClassification.classfication_id`, `SDO.currency_id`, and `SDOClassification.parent_id` are identifier columns, but their database-level referential constraints cannot be inferred from these declarations.

No migration or DDL deployment mechanism is described by these model files. The production schema, unique indexes beyond those declared, column types/collations, referential integrity, and catalogue completeness require database-owner confirmation.

## Repository usage

- [`StandardsRepository`](../backend/app/repositories/standards_repository.py) queries `Standard` (`standards_search`) and `SDO` (`sdos`) for local matching and SDO resolution.
- [`EnrichmentRepository`](../backend/app/repositories/enrichment_repository.py) queries `StandardMaster`, `StandardStatus`, `StandardPrice`, `Currency`, `StandardClassification`, `SDOClassification`, and `SDO` for fallback matching and result enrichment.
- `DocumentSearchService.__init__()` constructs both repositories using the same supplied session.

The repository queries establish expected table/model usage, not the live data contents or deployed database state.
