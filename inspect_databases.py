import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
ENRICHMENT_DATABASE_URL = os.getenv("ENRICHMENT_DATABASE_URL")


# ============================================================
# HELPERS
# ============================================================

def get_database_name(url):
    if not url:
        return "NOT CONFIGURED"

    parsed = urlparse(url)
    database = parsed.path.lstrip("/")

    return database or "UNKNOWN"


def create_read_only_engine(url):
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 10
        }
    )


def print_header(title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_columns(connection, table_name):
    print()
    print(f"TABLE: {table_name}")
    print("-" * 80)

    result = connection.execute(
        text(f"SHOW COLUMNS FROM `{table_name}`")
    )

    for row in result:
        print(
            f"{row[0]:30} "
            f"{str(row[1]):25} "
            f"NULL={str(row[2]):5} "
            f"KEY={str(row[3]):8} "
            f"DEFAULT={str(row[4])}"
        )


def print_indexes(connection, table_name):
    print()
    print(f"INDEXES: {table_name}")
    print("-" * 80)

    result = connection.execute(
        text(f"SHOW INDEX FROM `{table_name}`")
    )

    seen = set()

    for row in result:
        key_name = row[2]

        if key_name in seen:
            continue

        seen.add(key_name)

        print(
            f"{key_name:30} "
            f"Column={row[4]}"
        )


def print_row_count(connection, table_name):
    try:
        result = connection.execute(
            text(f"SELECT COUNT(*) FROM `{table_name}`")
        )

        count = result.scalar()

        print(
            f"{table_name:35} "
            f"{count:,} rows"
        )

    except Exception as error:
        print(
            f"{table_name:35} "
            f"COUNT ERROR: {error}"
        )


def inspect_database(label, url, tables_to_check):
    print_header(label)

    if not url:
        print("DATABASE URL IS NOT CONFIGURED.")
        return

    print(
        "Database:",
        get_database_name(url)
    )

    print(
        "Host:",
        urlparse(url).hostname
    )

    try:
        engine = create_read_only_engine(url)

        with engine.connect() as connection:

            print()
            print("CONNECTION: OK")

            # ------------------------------------------------
            # DATABASE NAME
            # ------------------------------------------------

            result = connection.execute(
                text("SELECT DATABASE()")
            )

            print(
                "Active database:",
                result.scalar()
            )

            # ------------------------------------------------
            # TABLE LIST
            # ------------------------------------------------

            print_header(
                f"{label} - TABLE LIST"
            )

            result = connection.execute(
                text("SHOW TABLES")
            )

            tables = [
                row[0]
                for row in result
            ]

            for table in tables:
                print(table)

            # ------------------------------------------------
            # ROW COUNTS
            # ------------------------------------------------

            print_header(
                f"{label} - ROW COUNTS"
            )

            for table in tables_to_check:

                if table in tables:
                    print_row_count(
                        connection,
                        table
                    )
                else:
                    print(
                        f"{table:35} "
                        f"TABLE NOT FOUND"
                    )

            # ------------------------------------------------
            # COLUMN INFORMATION
            # ------------------------------------------------

            print_header(
                f"{label} - COLUMN INFORMATION"
            )

            for table in tables_to_check:

                if table in tables:
                    print_columns(
                        connection,
                        table
                    )
                else:
                    print()
                    print(
                        f"TABLE NOT FOUND: {table}"
                    )

            # ------------------------------------------------
            # INDEX INFORMATION
            # ------------------------------------------------

            print_header(
                f"{label} - INDEX INFORMATION"
            )

            for table in tables_to_check:

                if table in tables:
                    print_indexes(
                        connection,
                        table
                    )

        engine.dispose()

    except Exception as error:

        print()
        print("DATABASE CONNECTION FAILED")
        print()
        print(error)


# ============================================================
# DATABASE 1
# LOCAL / TEMPORARY DATABASE
# ============================================================

LOCAL_TABLES = [
    "standards_search",
    "standards",
    "sdos",
    "standarddetails",
    "std_status",
]


# ============================================================
# DATABASE 2
# COMPANY / ENRICHMENT DATABASE
# ============================================================

COMPANY_TABLES = [
    "standard",
    "standards",
    "standards_search",
    "sdos",
    "std_prices",
    "bsbe_std_classifications",
    "sdo_classifications",
]


# ============================================================
# RUN INSPECTION
# ============================================================

print()
print("=" * 80)
print("STANDARDS INTELLIGENCE DATABASE INSPECTION")
print("READ-ONLY INSPECTION - NO DATA WILL BE CHANGED")
print("=" * 80)

inspect_database(
    "LOCAL DATABASE",
    DATABASE_URL,
    LOCAL_TABLES
)

inspect_database(
    "COMPANY DATABASE",
    ENRICHMENT_DATABASE_URL,
    COMPANY_TABLES
)

print()
print("=" * 80)
print("INSPECTION COMPLETE")
print("NO INSERT / UPDATE / DELETE / ALTER / DROP OPERATIONS WERE USED")
print("=" * 80)
print()