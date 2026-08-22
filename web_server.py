"""
分布式视频矩阵 Web 控制台。

启动：
    python web_server.py --host 127.0.0.1 --port 8080
"""
import argparse
import base64
import json
import logging
import mimetypes
import os
import socket
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
        if path == "/api/preview/event":
            payload = self._read_json()
            logger.info("预览事件: %s", _preview_event_summary(payload))
            if _preview_event_needs_port_check(payload):
                logger.info(
                    "预览取流端口检查: %s",
                    _check_ws_port(str(payload.get("ws_url", ""))),
                )
                origin = f"http://{self.headers.get('Host')}" if self.headers.get("Host") else ""
                logger.info(
                    "预览取流握手检查: %s",
                    _check_ws_handshake(str(payload.get("ws_url", "")), origin=origin),
                )
            self._send_json({"result": "success", "result_val": 0})
            return

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


def _preview_event_summary(payload: Dict[str, Any]) -> str:
    parts = []
    for key in (
        "output",
        "event",
        "ws_url",
        "channel",
        "reason",
        "codec",
        "width",
        "height",
        "bytes",
        "frames",
        "detail",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={str(value)[:120]}")
    return ", ".join(parts) if parts else "empty"


def _preview_event_needs_port_check(payload: Dict[str, Any]) -> bool:
    if payload.get("event") != "candidate_failed":
        return False
    if payload.get("frames"):
        return False
    return payload.get("reason") in {"连接超时", "取流异常", "取流已断开"}


def _check_ws_port(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    if not host:
        return f"url={ws_url or '-'}, status=invalid_url"

    try:
        with socket.create_connection((host, port), timeout=1.5):
            return f"url={ws_url}, status=tcp_ok"
    except OSError as exc:
        return f"url={ws_url}, status=tcp_failed, error={type(exc).__name__}: {exc}"


def _check_ws_handshake(ws_url: str, origin: str = "") -> str:
    parsed = urlparse(ws_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if not host:
        return f"url={ws_url or '-'}, status=invalid_url"

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    headers = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}:{port}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
    ]
    if origin:
        headers.append(f"Origin: {origin}")
    request = "\r\n".join(headers) + "\r\n\r\n"

    try:
        with socket.create_connection((host, port), timeout=1.5) as sock:
            sock.settimeout(2.0)
            sock.sendall(request.encode("ascii"))
            response = sock.recv(512).decode("iso-8859-1", errors="replace")
    except socket.timeout:
        return f"url={ws_url}, origin={origin or '-'}, status=handshake_timeout"
    except OSError as exc:
        return (
            f"url={ws_url}, origin={origin or '-'}, status=handshake_failed, "
            f"error={type(exc).__name__}: {exc}"
        )

    first_line = response.splitlines()[0] if response else ""
    if " 101 " in f" {first_line} ":
        status = "handshake_ok"
    elif response:
        status = "handshake_rejected"
    else:
        status = "handshake_empty"
    return f"url={ws_url}, origin={origin or '-'}, status={status}, response={first_line[:160]}"


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
