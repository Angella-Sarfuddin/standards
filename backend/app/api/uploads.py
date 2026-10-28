from fastapi import HTTPException, UploadFile


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def read_limited_upload(file: UploadFile) -> None:
    """Reject a missing name or a file larger than 10 MB, then rewind it."""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File name is required",
        )

    content = file.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File size must not exceed 10 MB",
        )
    file.file.seek(0)
