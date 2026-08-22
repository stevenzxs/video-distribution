"""
分布式视频矩阵 Web 控制台。

启动：
    python web_server.py --host 127.0.0.1 --port 8080
"""
import argparse
import json
import logging
import mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import unquote, urlparse

from config import LOG_FORMAT, LOG_LEVEL
from matrix_service import MatrixError, MatrixScheduler, get_matrix_state


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


class MatrixHTTPRequestHandler(BaseHTTPRequestHandler):
    scheduler = MatrixScheduler()

    def do_OPTIONS(self) -> None:
        self._send_empty(204)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._serve_file(WEB_DIR / "index.html")
            return
        if path == "/api/matrix/config":
            self._send_json(get_matrix_state())
            return
        if path.startswith("/static/"):
            relative = unquote(path.removeprefix("/static/"))
            self._serve_file(STATIC_DIR / relative)
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/matrix/switch":
            self._send_json({"error": "not found"}, 404)
            return

        try:
            payload = self._read_json()
            commands = _commands_from_payload(payload)
            routes = [self.scheduler.switch_command(command) for command in commands]
            self._send_json({"result": "success", "result_val": 0, "routes": routes})
        except MatrixError as exc:
            logger.warning("矩阵切换失败: %s", exc)
            self._send_json(
                {"result": str(exc), "result_val": 3, "routes": []},
                exc.status_code,
            )
        except Exception as exc:
            logger.exception("矩阵切换失败")
            self._send_json(
                {"result": f"矩阵切换失败: {exc}", "result_val": 8, "routes": []},
                500,
            )

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(WEB_DIR.resolve()) or not resolved.is_file():
                self._send_json({"error": "not found"}, 404)
                return

            body = resolved.read_bytes()
            content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError as exc:
            logger.exception("读取静态文件失败")
            self._send_json({"error": f"读取文件失败: {exc}"}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)


def _commands_from_payload(payload: Dict[str, Any]) -> List[str]:
    command = str(payload.get("command", "")).strip()
    if command:
        return [command]

    try:
        input_index = int(payload.get("input"))
    except (TypeError, ValueError):
        raise MatrixError("缺少输入编号")

    outputs = payload.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise MatrixError("缺少输出编号")

    commands = []
    for output in outputs:
        try:
            output_index = int(output)
        except (TypeError, ValueError):
            raise MatrixError("输出编号必须为数字")
        commands.append(f"{input_index}v{output_index}.")
    return commands


def main() -> None:
    parser = argparse.ArgumentParser(description="分布式视频矩阵 Web 控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), MatrixHTTPRequestHandler)
    logger.info("Web 控制台已启动: http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("正在停止 Web 控制台")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
