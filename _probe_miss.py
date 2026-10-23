from database import SessionLocal
from app.services.document_search_service import DocumentSearchService

samples = [
    ("ASME", "Sec. IX"),
    ("ASME", "BPVC Sec.II Materials Part C"),
    ("ASME", "BPVC Sec. VIII Div-1"),
    ("ASME", "BPVC Sec. II Materials Part-A"),
    ("ANSI", "B 18.2.3.5M"),
    ("DIN", "EN 10213:2007+A1"),
    ("EN", "ISO 3651-2"),
    ("ANSI", "/MSS SP-25"),
    ("ANSI", "/MSS SP-55"),
    ("ANSI", "/MSS SP-144"),
    ("ANSI", "NACE MR 0175 ISO 15156 - Part-1,2,3"),
    ("SAE", "AMS 5699 Rev.H"),
    ("SAE", "AMS 2750 Rev.H"),
    ("SAE", "AMS5837"),
    ("AWS", "QCI"),
    ("ANSI", "/ASNT-CP-189"),
    ("ANSI", "/MSS SP-135"),
    ("SAE", "2017-28-1972"),
    ("PD", "CEN-TR 1591-2"),
    ("ASNT", "ACCP-CP1"),
    ("ASTM", "A991-A991M"),
    ("ISO", "3056 - 2"),
    ("SAE", "AMS 5894 Rev.E"),
    ("ASME", "BPVC SEC II PART B"),
    ("ASME", "BPVC SEC II PART D Customary"),
    ("JIS", "G1253 Amendment-1"),
    ("SAE", "AMS 2644 Rev.H"),
    ("ASME", "BPVC Sec. VIII Div-2"),
]
db = SessionLocal()
results = DocumentSearchService(db).search([
    {"sdo_name": sdo, "displaystdno": num} for sdo, num in samples
])
for row in results:
    std = row.get("standard") or {}
    print(row.get("status"), "|", row.get("requested_sdo"), row.get("requested_standard"), "|", std.get("display_stdNo"))
db.close()
