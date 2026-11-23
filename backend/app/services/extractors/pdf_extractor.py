import logging
import os
import re
import subprocess
import tempfile

import pymupdf

from app.services.extractors.base_extractor import BaseExtractor

logger = logging.getLogger(__name__)

# OCR often glues the letter series onto ASTM: ASTMD93, ASTMA 240, ASTME4S.
_GLUED_ASTM_RE = re.compile(
    r"\bASTM(?P<letter>[A-GE])\s*(?P<num>\d+[A-Za-z0-9.-]*)",
    re.IGNORECASE,
)

# Capture a designation and optional dual metric form (A 240/A240M).
_STANDARD_RE = re.compile(
    r"\b(?P<sdo>ISO(?:/IEC|/TS|/TR)?|ASTM|ASME|API|IEC|NACE|IEEE|ANSI|BS|EN|"
    r"DIN|JIS|UL|SAE|AWS|AWWA|ASHRAE|ACI|NFPA|BSI|IS)"
    r"\s+"
    r"(?P<body>"
    r"(?:[A-Z]{1,4}\s*)?\d+[A-Za-z0-9.-]*"
    r"(?:\s*/\s*(?:[A-Z]{1,4}\s*)?\d+[A-Za-z0-9.-]*)?"
    r")",
    re.IGNORECASE,
)


class PDFExtractor(BaseExtractor):
    """Extract plain text from PDFs, with OCR fallback for scanned pages."""

    OCR_DPI = 220
    OCR_PSM = "6"

    def extract(self, file):
        document = pymupdf.open(
            stream=file.read(),
            filetype="pdf",
        )

        text_parts = []
        used_ocr = False

        try:
            for page_index, page in enumerate(document):
                text = (page.get_text("text", sort=True) or "").strip()

                if not text:
                    ocr_text = self._ocr_page(page, page_index)
                    if ocr_text:
                        text = self._normalize_ocr_text(ocr_text)
                        used_ocr = True

                if text:
                    text_parts.append(text)
        finally:
            document.close()

        return {
            "text": "\n".join(text_parts),
            "source_type": "pdf",
            "ocr_used": used_ocr,
        }

    def _ocr_page(self, page, page_index: int) -> str:
        """Rasterize the page and OCR with Tesseract (table-friendly PSM)."""
        try:
            pix = page.get_pixmap(dpi=self.OCR_DPI, alpha=False)
            with tempfile.TemporaryDirectory(prefix="pdf-ocr-") as tmp:
                png_path = os.path.join(tmp, f"page-{page_index + 1}.png")
                pix.save(png_path)
                completed = subprocess.run(
                    [
                        "tesseract",
                        png_path,
                        "stdout",
                        "--psm",
                        self.OCR_PSM,
                        "-l",
                        "eng",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    logger.warning(
                        "Tesseract OCR failed on PDF page %s: %s",
                        page_index + 1,
                        (completed.stderr or "").strip() or completed.returncode,
                    )
                    return ""
                return (completed.stdout or "").strip()
        except Exception as exc:
            logger.warning(
                "OCR failed on PDF page %s: %s",
                page_index + 1,
                exc,
            )
            return ""

    @classmethod
    def _normalize_ocr_text(cls, text: str) -> str:
        """Turn noisy OCR table text into clean SDO + designation lines."""
        if not text:
            return ""

        repaired = _GLUED_ASTM_RE.sub(
            lambda match: f"ASTM {match.group('letter').upper()} {match.group('num')}",
            text,
        )

        seen = set()
        lines = []
        for match in _STANDARD_RE.finditer(repaired):
            sdo = match.group("sdo").upper()
            if sdo == "IS" and not re.match(r"(?i)^IS\b", match.group(0)):
                continue
            body = re.sub(r"\s+", " ", match.group("body")).strip(" .-_|")
            if not body or not re.search(r"\d", body):
                continue
            designation = f"{sdo} {body}"
            key = re.sub(r"\s+", "", designation).upper()
            if key in seen:
                continue
            seen.add(key)
            lines.append(designation)

        return "\n".join(lines) if lines else repaired
