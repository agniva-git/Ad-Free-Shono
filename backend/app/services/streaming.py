import os
import mimetypes
from pathlib import Path
from typing import Generator
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

CHUNK_SIZE = 128 * 1024  # 128 KB chunks

def send_file_range_response(file_path: Path, range_header: str | None) -> StreamingResponse:
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found")

    file_size = file_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "audio/mpeg"

    start = 0
    end = file_size - 1

    if range_header:
        # Expected format: "bytes=0-1024" or "bytes=1024-"
        try:
            bytes_unit, ranges = range_header.strip().split("=")
            if bytes_unit.strip() == "bytes":
                start_str, end_str = ranges.split("-", 1)
                if start_str.strip():
                    start = int(start_str.strip())
                if end_str.strip():
                    end = int(end_str.strip())
        except Exception:
            start = 0
            end = file_size - 1

    if start >= file_size or end >= file_size or start > end:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Requested range not satisfiable",
            headers={"Content-Range": f"bytes */{file_size}"}
        )

    content_length = (end - start) + 1

    def file_stream() -> Generator[bytes, None, None]:
        with open(file_path, "rb") as f:
            f.seek(start)
            bytes_left = content_length
            while bytes_left > 0:
                read_amount = min(CHUNK_SIZE, bytes_left)
                data = f.read(read_amount)
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length),
        "Content-Type": mime_type,
    }

    return StreamingResponse(
        file_stream(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        headers=headers
    )
