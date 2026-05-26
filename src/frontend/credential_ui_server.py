from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from src.comsol.credentials import comsol_credentials_status
from src.comsol.credentials import set_comsol_credentials
from src.comsol.server import stop_started_servers
from src.frontend.target_ui_server import designer_html_path
from src.frontend.target_ui_server import make_handler
from src.frontend.target_ui_server import workflow_snapshot


def injected_designer_html() -> bytes:
    html_path = designer_html_path()
    body = html_path.read_text(encoding="utf-8")
    script_tag = '  <script src="/assets/comsol_credentials.js"></script>\n'
    if "/assets/comsol_credentials.js" not in body and "</body>" in body:
        body = body.replace("</body>", script_tag + "</body>")
    return body.encode("utf-8")


def make_credential_handler(config: dict):
    base_handler = make_handler(config)
    credential_script_path = designer_html_path().with_name("comsol_credentials.js")

    class CredentialUiHandler(base_handler):
        def do_GET(self) -> None:
            route = urlparse(self.path).path
            if route in {"/", "/target_designer.html"}:
                self.send_bytes(injected_designer_html(), "text/html; charset=utf-8")
                return
            if route == "/assets/comsol_credentials.js":
                self.send_file(credential_script_path, "application/javascript; charset=utf-8")
                return
            if route == "/api/comsol-credentials":
                self.send_json(comsol_credentials_status(config))
                return
            super().do_GET()

        def do_POST(self) -> None:
            route = self.path.split("?", 1)[0]
            if route != "/api/comsol-credentials":
                super().do_POST()
                return
            try:
                if workflow_snapshot().get("running"):
                    self.send_json({"error": "Cannot change COMSOL credentials while a workflow is running."}, HTTPStatus.CONFLICT)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                set_comsol_credentials(payload.get("username", ""), payload.get("password", ""))
                stop_started_servers()
                self.send_json({
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                    "credentials": comsol_credentials_status(config),
                })
            except Exception as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    return CredentialUiHandler


def run_target_ui(config: dict, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), make_credential_handler(config))
    print(f"Target designer running at http://{host}:{port} / 目标绘图器运行于 http://{host}:{port}")
    server.serve_forever()
