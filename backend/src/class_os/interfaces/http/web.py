"""Same-origin built Web. Never fall back to mock state on API failure."""
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles


def mount_web(app, directory: Path):
    directory = directory.resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("Build apps/web before serving the integrated application")
    app.mount("/assets", StaticFiles(directory=directory / "assets"), name="web-assets")

    @app.get("/")
    def index():
        return FileResponse(directory / "index.html", media_type="text/html")
