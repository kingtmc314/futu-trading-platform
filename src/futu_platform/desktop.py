"""桌面版啟動器：內嵌 Web 控制台（需 pywebview）。"""

from __future__ import annotations

import threading
import time

import uvicorn

from .config import get_settings


def run_desktop(host: str | None = None, port: int | None = None) -> None:
    try:
        import webview
    except ImportError as exc:
        raise SystemExit(
            "桌面版需要 pywebview。請執行：pip install 'futu-trading-platform[desktop]'"
        ) from exc

    settings = get_settings()
    host = host or settings.web_host
    port = port or settings.web_port
    url = f"http://{host}:{port}"

    config = uvicorn.Config(
        "futu_platform.web.app:app",
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    def _serve() -> None:
        server.run()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    webview.create_window(
        "Futu 交易平台",
        url,
        width=1280,
        height=860,
        min_size=(960, 640),
    )
    webview.start()
