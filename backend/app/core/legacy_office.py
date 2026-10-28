"""Helpers for reading legacy Microsoft Office formats without xlrd/Word COM."""

from collections.abc import Iterator
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid


logger = logging.getLogger(__name__)

ALLOWED_TARGET_EXTENSIONS = {".docx", ".xlsx"}


class OfficeConversionUnavailable(RuntimeError):
    """Raised when LibreOffice is not installed or cannot be located."""


class OfficeConversionError(RuntimeError):
    """Raised when LibreOffice cannot convert the supplied Office file."""


def _soffice_path() -> str:
    configured = os.environ.get("LIBREOFFICE_PATH")
    candidates = [configured, shutil.which("soffice")]
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates.extend([
            str(Path(program_files) / "LibreOffice" / "program" / "soffice.exe"),
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ])
    else:
        candidates.extend(["/usr/bin/soffice", "/usr/local/bin/soffice"])

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise OfficeConversionUnavailable(
        "LibreOffice was not found. Install LibreOffice or configure "
        "LIBREOFFICE_PATH to enable legacy .doc/.xls uploads."
    )


def _read_upload(file: object) -> bytes:
    if isinstance(file, (str, os.PathLike)):
        return Path(file).read_bytes()
    if hasattr(file, "seek"):
        file.seek(0)
    if hasattr(file, "read"):
        content = file.read()
        if hasattr(file, "seek"):
            file.seek(0)
        return content
    return bytes(file)


def _create_conversion_directory() -> Path:
    """Create an Office workspace with inherited filesystem permissions.

    ``TemporaryDirectory`` creates a private directory on Windows. On some
    managed installations the app process cannot create child directories in
    that private ACL, even though it can write to its normal temp location.
    Plain child directories inherit the parent ACL and keep conversion local.
    """
    project_temp = Path(__file__).resolve().parents[3] / ".standards-tmp"
    candidates = [
        os.environ.get("STANDARDS_TEMP_DIR"),
        tempfile.gettempdir(),
        str(project_temp),
    ]
    errors = []
    for candidate in dict.fromkeys(value for value in candidates if value):
        base = Path(candidate)
        try:
            base.mkdir(parents=True, exist_ok=True)
            directory = base / f"standards-office-{uuid.uuid4().hex}"
            directory.mkdir()
            return directory
        except OSError as exc:
            errors.append(f"{base}: {exc}")

    raise OfficeConversionError(
        "Could not create a temporary folder for Office conversion. "
        + "; ".join(errors)
    )


def _target_extension(target_extension: str) -> str:
    extension = str(target_extension or "").lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    if extension not in ALLOWED_TARGET_EXTENSIONS:
        raise OfficeConversionError(
            "Legacy Office conversion only supports .docx and .xlsx output."
        )
    return extension


@contextmanager
def converted_office_file(
    file: object,
    filename: str | None,
    target_extension: str,
    timeout: int = 90,
) -> Iterator[Path]:
    """Yield a temporary converted file, using an isolated LibreOffice profile."""
    target_extension = _target_extension(target_extension)
    soffice = _soffice_path()
    logger.info(
        "Converting %s to %s with LibreOffice",
        Path(str(filename or "upload")).name,
        target_extension,
    )
    source_name = Path(str(filename or "upload")).name
    source_extension = Path(source_name).suffix or ".bin"

    try:
        root = _create_conversion_directory()
    except OfficeConversionError as exc:
        raise OfficeConversionError(
            f"Could not create a temporary folder for Office conversion: {exc}"
        ) from exc

    try:
        source = root / ("source" + source_extension)
        output_dir = root / "converted"
        profile_dir = root / "profile"
        try:
            output_dir.mkdir()
            profile_dir.mkdir()
            source.write_bytes(_read_upload(file))
        except OSError as exc:
            raise OfficeConversionError(
                f"Could not prepare a temporary folder for Office conversion: {exc}"
            ) from exc

        profile_uri = profile_dir.resolve().as_uri()
        command = [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            target_extension.lstrip("."),
            "--outdir",
            str(output_dir),
            str(source),
        ]
        options = {
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": timeout,
        }
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            completed = subprocess.run(command, **options)
        except subprocess.TimeoutExpired as exc:
            logger.error(
                "LibreOffice timed out after %s seconds converting %s",
                timeout,
                source_name,
            )
            raise OfficeConversionError(
                f"LibreOffice took longer than {timeout} seconds to read the file."
            ) from exc
        except OSError as exc:
            logger.exception("LibreOffice could not be started")
            raise OfficeConversionError(
                f"LibreOffice could not be started: {exc}"
            ) from exc

        converted = output_dir / (source.stem + target_extension)
        if completed.returncode != 0 or not converted.is_file():
            detail = (completed.stderr or completed.stdout or "").strip()
            logger.warning(
                "LibreOffice conversion failed code=%s file=%s detail=%s",
                completed.returncode,
                source_name,
                detail[:500],
            )
            raise OfficeConversionError(
                "LibreOffice could not convert this legacy Office file."
            )

        yield converted
    finally:
        shutil.rmtree(root, ignore_errors=True)
