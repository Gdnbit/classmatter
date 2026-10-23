"""Same-origin built Web. Never fall back to mock state on API failure."""
from pathlib import Path
import re
from urllib.parse import parse_qsl

from fastapi import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def navigation_query_allowed(path: str, method: str, query: bytes) -> bool:
    """Closed presentation hints only; never business/API query parameters."""
    if method != "GET" or len(query) > 512:
        return False
    if path == "/students":
        allowed = {"view": {"list", "table", "seat", "dorm", "group"}}
    elif re.fullmatch(r"/students/[^/]+", path):
        allowed = {"view": {"list", "table"}, "tab": {"overview", "timeline", "tasks", "records", "unavailable", "grades", "files", "relations"}}
    elif path == "/work":
        allowed = {"filter": {"all", "open", "waiting", "closed"}, "student": None, "task": None}
    else:
        return False
    try:
        pairs = parse_qsl(query.decode("ascii"), strict_parsing=True, keep_blank_values=True, max_num_fields=3)
    except (ValueError, UnicodeError):
        return False
    if not pairs or len(dict(pairs)) != len(pairs):
        return False
    return all(key in allowed and (bool(_UUID.fullmatch(value)) if allowed[key] is None else value in allowed[key]) for key, value in pairs)


def mount_web(app, directory: Path):
    directory = directory.resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("Build apps/web before serving the integrated application")
    app.mount("/assets", StaticFiles(directory=directory / "assets"), name="web-assets")

    def index():
        return FileResponse(directory / "index.html", media_type="text/html")

    # Exact shell routes only. No catch-all that could turn API/asset errors
    # into HTML success, and no path is joined to a filesystem location.
    for path in ("/", "/dashboard", "/students", "/students/{student_id}", "/work",
                 "/settings", "/settings/user", "/unavailable", "/data",
                 "/data/spreadsheets/{file_id}", "/data/documents/{file_id}",
                 "/spaces/{space_id}", "/automation", "/knowledge", "/reports"):
        app.add_api_route(path, index, methods=["GET"], include_in_schema=False)
    app.state.web_mounted = True
