"""python serve.py; synthetic loopback only, no production service entry."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from class_os.infrastructure.windows_platform import configure_windows_platform
configure_windows_platform(os.environ)

import uvicorn
from class_os.interfaces.http.app import create_app
from class_os.interfaces.http.settings import Settings


if __name__ == "__main__":
    settings = Settings.from_env(os.environ)
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.port,
                reload=False, proxy_headers=False, access_log=False)
