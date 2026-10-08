from pathlib import Path
from typing import Generator, Optional, Tuple

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

CHUNK_SIZE = 128 * 1024  # 128 KB

MIME_BY_SUFFIX = {
    ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav",
}


class RangeNotSatisfiable(Exception):
    pass


def parse_range(header: str, size: int) -> Optional[Tuple[int, int]]:
    """Parse the first byte range of a Range header into inclusive (start, end).
    Returns None for headers that should be ignored (malformed / other units);
    raises RangeNotSatisfiable when the range lies outside the file."""
    try:
        unit, _, spec = header.partition("=")
        if unit.strip().lower() != "bytes":
            return None
        first = spec.split(",")[0].strip()
        start_s, _, end_s = first.partition("-")
        if start_s == "":  # suffix form "bytes=-500" means the last 500 bytes
            count = int(end_s)
            if count <= 0:
                raise RangeNotSatisfiable()
            return max(size - count, 0), size - 1
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start >= size or end < start:
        raise RangeNotSatisfiable()
    return start, min(end, size - 1)  # an end past EOF is clamped, per the HTTP spec


def send_file_range_response(file_path: Path, range_header: Optional[str]) -> StreamingResponse:
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    file_size = file_path.stat().st_size
    mime_type = MIME_BY_SUFFIX.get(file_path.suffix.lower(), "application/octet-stream")

    start, end = 0, max(file_size - 1, 0)
    partial = False
    if range_header and file_size > 0:
        try:
            parsed = parse_range(range_header, file_size)
        except RangeNotSatisfiable:
            raise HTTPException(
                status_code=416,
                detail="Requested range not satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )
        if parsed:
            start, end = parsed
            partial = True

    content_length = (end - start) + 1 if file_size > 0 else 0

    def file_stream() -> Generator[bytes, None, None]:
        with open(file_path, "rb") as f:
            f.seek(start)
            left = content_length
            while left > 0:
                data = f.read(min(CHUNK_SIZE, left))
                if not data:
                    break
                left -= len(data)
                yield data

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": mime_type,
    }
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(
        file_stream(),
        status_code=status.HTTP_206_PARTIAL_CONTENT if partial else status.HTTP_200_OK,
        headers=headers,
    )
