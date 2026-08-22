"""
分布式视频矩阵 Web 控制台。

启动：
    python web_server.py --host 127.0.0.1 --port 8080
"""
import argparse
import base64
import hashlib
import json
import logging
import mimetypes
import os
import select
import socket
import time
from dataclasses import dataclass
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union
from urllib.parse import parse_qs, unquote, urlparse

from api_client import is_success_response
from config import API_BASE_URL, LOG_FORMAT, LOG_LEVEL
from matrix_service import MatrixError, MatrixScheduler, get_matrix_state


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
DEFAULT_PREVIEW_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
PREVIEW_TCP_CONNECT_TIMEOUT_SECONDS = 3.0
PREVIEW_UPSTREAM_HANDSHAKE_TIMEOUT_SECONDS = 20.0
PREVIEW_DIAGNOSTIC_HANDSHAKE_TIMEOUT_SECONDS = 8.0
PREVIEW_CONTROL_RESPONSE_TIMEOUT_SECONDS = 8.0

logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


@dataclass
class UpstreamWebSocket:
    sock: socket.socket
    headers: Dict[str, str]
    initial_data: bytes = b""


class MatrixHTTPRequestHandler(BaseHTTPRequestHandler):
    scheduler = MatrixScheduler()

    def do_OPTIONS(self) -> None:
        self._send_empty(204)

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        if path == "/api/preview/ws":
            self._proxy_preview_ws(parsed_path.query)
            return
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

    def _proxy_preview_ws(self, query: str) -> None:
        output = _preview_output_from_query(query)
        stream = _preview_stream_for_output(
            self.scheduler.runtime_state.snapshot(),
            output,
        )
        if not stream:
            self._send_json({"error": f"output {output} has no active stream"}, 404)
            return

        upstream_url = str(stream.get("ws_url", ""))
        control_url = str(stream.get("control_ws_url", ""))
        protocol = str(stream.get("ws_protocol", ""))
        client_protocol = self.headers.get("Sec-WebSocket-Protocol", "")
        client_extensions = self.headers.get("Sec-WebSocket-Extensions", "")
        user_agent = self.headers.get("User-Agent", DEFAULT_PREVIEW_USER_AGENT)
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self._send_json({"error": "missing Sec-WebSocket-Key"}, 400)
            return

        try:
            if control_url:
                control_result = _call_preview_control_ws(
                    control_url,
                    origin=API_BASE_URL,
                    protocol=protocol,
                    user_agent=user_agent,
                )
                logger.info(
                    "预览视频调度确认: output=%s, url=%s, result=%s",
                    output,
                    control_url,
                    _preview_control_result_summary(control_result),
                )
            upstream = _open_upstream_websocket(
                upstream_url,
                origin=API_BASE_URL,
                protocol=protocol,
                extensions=client_extensions,
                user_agent=user_agent,
            )
        except OSError as exc:
            logger.error(
                (
                    "预览代理连接上游失败: output=%s, control_url=%s, url=%s, protocol=%s, "
                    "extensions=%s, timeout=%ss, error=%s: %s"
                ),
                output,
                control_url,
                upstream_url,
                "yes" if protocol else "no",
                "yes" if client_extensions else "no",
                PREVIEW_UPSTREAM_HANDSHAKE_TIMEOUT_SECONDS,
                type(exc).__name__,
                exc,
            )
            self._send_json({"error": f"upstream websocket failed: {exc}"}, 502)
            return

        response_lines = [
            "HTTP/1.1 101 Switching Protocols",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Accept: {_websocket_accept_key(key)}",
        ]
        response_protocol = (
            upstream.headers.get("sec-websocket-protocol")
            or _first_requested_protocol(client_protocol)
        )
        if response_protocol and _protocol_requested_by_client(
            client_protocol,
            response_protocol,
        ):
            response_lines.append(f"Sec-WebSocket-Protocol: {response_protocol}")

        response_extensions = upstream.headers.get("sec-websocket-extensions", "")
        if response_extensions and client_extensions:
            response_lines.append(f"Sec-WebSocket-Extensions: {response_extensions}")

        response = "\r\n".join(response_lines) + "\r\n\r\n"
        self.request.sendall(response.encode("ascii"))
        self.close_connection = True

        logger.info(
            "预览代理已连接: output=%s, upstream=%s, origin=%s, protocol=%s",
            output,
            upstream_url,
            API_BASE_URL,
            "yes" if protocol else "no",
        )
        if upstream.initial_data:
            self.request.sendall(upstream.initial_data)
        _relay_websocket(self.request, upstream.sock)

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
                for handshake_result in _check_ws_handshakes(
                    str(payload.get("ws_url", "")),
                    origin=origin,
                    protocol=str(payload.get("ws_protocol", "")),
                ):
                    logger.info("预览取流握手检查: %s", handshake_result)
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
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError) as exc:
            logger.warning("响应写入失败: %s: %s", type(exc).__name__, exc)

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
        "control_ws_url",
        "ws_url",
        "connect_url",
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
        with socket.create_connection(
            (host, port),
            timeout=PREVIEW_TCP_CONNECT_TIMEOUT_SECONDS,
        ):
            return f"url={ws_url}, status=tcp_ok"
    except OSError as exc:
        return f"url={ws_url}, status=tcp_failed, error={type(exc).__name__}: {exc}"


def _check_ws_handshakes(
    ws_url: str,
    origin: str = "",
    protocol: str = "",
) -> List[str]:
    results = []
    origins = []
    if origin:
        origins.append(origin)
    if API_BASE_URL and API_BASE_URL not in origins:
        origins.append(API_BASE_URL)
    origins.append("")
    for candidate_origin in origins:
        results.append(
            _check_ws_handshake(
                ws_url,
                origin=candidate_origin,
                protocol=protocol,
            )
        )
    return results


def _check_ws_handshake(
    ws_url: str,
    origin: str = "",
    protocol: str = "",
) -> str:
    parsed = urlparse(ws_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if not host:
        return f"url={ws_url or '-'}, status=invalid_url"

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    headers = _preview_upstream_handshake_headers(
        path,
        host,
        port,
        key,
        origin=origin,
        protocol=protocol,
        extensions="permessage-deflate; client_max_window_bits",
        user_agent=DEFAULT_PREVIEW_USER_AGENT,
    )
    request = "\r\n".join(headers) + "\r\n\r\n"

    started = time.monotonic()
    try:
        with socket.create_connection(
            (host, port),
            timeout=PREVIEW_TCP_CONNECT_TIMEOUT_SECONDS,
        ) as sock:
            sock.settimeout(PREVIEW_DIAGNOSTIC_HANDSHAKE_TIMEOUT_SECONDS)
            sock.sendall(request.encode("ascii"))
            response = sock.recv(512).decode("iso-8859-1", errors="replace")
    except socket.timeout:
        return (
            f"url={ws_url}, origin={origin or '-'}, protocol={'yes' if protocol else 'no'}, "
            f"status=handshake_timeout, elapsed={_elapsed_seconds(started)}s"
        )
    except OSError as exc:
        return (
            f"url={ws_url}, origin={origin or '-'}, protocol={'yes' if protocol else 'no'}, "
            "status=handshake_failed, "
            f"elapsed={_elapsed_seconds(started)}s, error={type(exc).__name__}: {exc}"
        )

    first_line = response.splitlines()[0] if response else ""
    if " 101 " in f" {first_line} ":
        status = "handshake_ok"
    elif response:
        status = "handshake_rejected"
    else:
        status = "handshake_empty"
    return (
        f"url={ws_url}, origin={origin or '-'}, protocol={'yes' if protocol else 'no'}, "
        f"status={status}, elapsed={_elapsed_seconds(started)}s, response={first_line[:160]}"
    )


def _preview_output_from_query(query: str) -> int:
    raw_output = parse_qs(query).get("output", ["0"])[0]
    try:
        return int(raw_output)
    except (TypeError, ValueError):
        return 0


def _preview_stream_for_output(state: Dict[str, Any], output: int) -> Dict[str, Any]:
    for screen in state.get("screens", []):
        if screen.get("index") != output:
            continue
        assignment = screen.get("assignment") or {}
        stream = assignment.get("stream") or {}
        return stream if isinstance(stream, dict) else {}
    return {}


def _call_preview_control_ws(
    ws_url: str,
    origin: str,
    protocol: str,
    user_agent: str = "",
) -> Dict[str, Any]:
    upstream = _open_upstream_websocket(
        ws_url,
        origin=origin,
        protocol=protocol,
        extensions="",
        user_agent=user_agent or DEFAULT_PREVIEW_USER_AGENT,
    )
    try:
        upstream.sock.settimeout(PREVIEW_CONTROL_RESPONSE_TIMEOUT_SECONDS)
        frame_buffer = bytearray(upstream.initial_data)
        for _ in range(5):
            opcode, payload = _recv_ws_frame(upstream.sock, frame_buffer)
            if opcode in (0x1, 0x2):
                result = _parse_preview_control_payload(payload)
                if not is_success_response(result):
                    raise OSError(
                        "preview control websocket returned "
                        f"{_preview_control_result_summary(result)}"
                    )
                return result
            if opcode == 0x8:
                raise OSError("preview control websocket closed before result")

        raise OSError("preview control websocket did not return a result frame")
    except TimeoutError as exc:
        raise TimeoutError("preview control websocket result timed out") from exc
    finally:
        try:
            upstream.sock.close()
        except OSError:
            pass


def _parse_preview_control_payload(payload: bytes) -> Dict[str, Any]:
    text = payload.decode("utf-8", errors="replace").strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OSError(f"preview control websocket returned non-json: {text[:160]}") from exc
    if not isinstance(result, dict):
        raise OSError(f"preview control websocket returned non-object json: {text[:160]}")
    return result


def _preview_control_result_summary(result: Dict[str, Any]) -> str:
    return ", ".join(
        f"{key}={result.get(key)}"
        for key in ("result", "result_val", "handle")
        if key in result
    ) or str(result)[:160]


def _websocket_accept_key(key: str) -> str:
    digest = hashlib.sha1(f"{key}{WEBSOCKET_GUID}".encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _open_upstream_websocket(
    ws_url: str,
    origin: str,
    protocol: str,
    extensions: str = "",
    user_agent: str = "",
) -> UpstreamWebSocket:
    parsed = urlparse(ws_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if not host:
        raise OSError(f"invalid websocket url: {ws_url}")
    if parsed.scheme == "wss":
        raise OSError("wss upstream is not supported by the local preview proxy")

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    headers = _preview_upstream_handshake_headers(
        path,
        host,
        port,
        key,
        origin=origin,
        protocol=protocol,
        extensions=extensions,
        user_agent=user_agent or DEFAULT_PREVIEW_USER_AGENT,
    )
    request = "\r\n".join(headers) + "\r\n\r\n"

    started = time.monotonic()
    try:
        sock = socket.create_connection(
            (host, port),
            timeout=PREVIEW_TCP_CONNECT_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        raise OSError(
            f"upstream tcp connect failed after {_elapsed_seconds(started)}s: {exc}"
        ) from exc

    try:
        sock.settimeout(PREVIEW_UPSTREAM_HANDSHAKE_TIMEOUT_SECONDS)
        sock.sendall(request.encode("ascii"))
        response, initial_data = _recv_http_headers(sock)
        first_line = response.splitlines()[0] if response else ""
        if " 101 " not in f" {first_line} ":
            raise OSError(f"upstream handshake rejected: {first_line[:160]}")
        sock.settimeout(None)
        return UpstreamWebSocket(
            sock=sock,
            headers=_parse_http_headers(response),
            initial_data=initial_data,
        )
    except TimeoutError as exc:
        sock.close()
        raise TimeoutError(
            f"upstream handshake timed out after {_elapsed_seconds(started)}s"
        ) from exc
    except Exception:
        sock.close()
        raise


def _preview_upstream_handshake_headers(
    path: str,
    host: str,
    port: int,
    key: str,
    origin: str,
    protocol: str,
    extensions: str = "",
    user_agent: str = "",
) -> List[str]:
    headers = [
        f"GET {path} HTTP/1.1",
        "Accept-Encoding: gzip, deflate",
        "Accept-Language: zh-CN,zh;q=0.9",
        "Cache-Control: no-cache",
        "Connection: Upgrade",
        f"Host: {host}:{port}",
        "Pragma: no-cache",
    ]
    if origin:
        headers.insert(6, f"Origin: {origin}")
    if extensions:
        headers.append(f"Sec-WebSocket-Extensions: {extensions}")
    headers.extend([
        f"Sec-WebSocket-Key: {key}",
    ])
    if protocol:
        headers.append(f"Sec-WebSocket-Protocol: {protocol}")
    headers.extend([
        "Sec-WebSocket-Version: 13",
        "Upgrade: websocket",
        f"User-Agent: {user_agent or DEFAULT_PREVIEW_USER_AGENT}",
    ])
    return headers


def _parse_http_headers(response: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for line in response.splitlines()[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return headers


def _recv_http_headers(sock: socket.socket) -> Tuple[str, bytes]:
    chunks = []
    total = 0
    while total < 8192:
        chunk = sock.recv(1024)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\r\n\r\n" in b"".join(chunks):
            break
    data = b"".join(chunks)
    header_bytes, separator, initial_data = data.partition(b"\r\n\r\n")
    if separator:
        header_bytes += separator
    return header_bytes.decode("iso-8859-1", errors="replace"), initial_data


def _recv_ws_frame(
    sock: socket.socket,
    initial_data: Union[bytes, bytearray] = b"",
) -> Tuple[int, bytes]:
    buffer = initial_data if isinstance(initial_data, bytearray) else bytearray(initial_data)
    header = _recv_buffered(sock, buffer, 2)
    first_byte, second_byte = header[0], header[1]
    opcode = first_byte & 0x0F
    length = second_byte & 0x7F
    masked = bool(second_byte & 0x80)
    if length == 126:
        length = int.from_bytes(_recv_buffered(sock, buffer, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_buffered(sock, buffer, 8), "big")

    mask = _recv_buffered(sock, buffer, 4) if masked else b""
    payload = bytearray(_recv_buffered(sock, buffer, length))
    if masked:
        for index, value in enumerate(payload):
            payload[index] = value ^ mask[index % 4]
    return opcode, bytes(payload)


def _recv_buffered(sock: socket.socket, buffer: bytearray, length: int) -> bytes:
    while len(buffer) < length:
        chunk = sock.recv(max(1024, length - len(buffer)))
        if not chunk:
            raise OSError("websocket connection closed")
        buffer.extend(chunk)

    data = bytes(buffer[:length])
    del buffer[:length]
    return data


def _first_requested_protocol(value: str) -> str:
    return next(
        (item.strip() for item in value.split(",") if item.strip()),
        "",
    )


def _protocol_requested_by_client(requested: str, selected: str) -> bool:
    selected = selected.strip()
    return bool(
        selected
        and selected in {item.strip() for item in requested.split(",") if item.strip()}
    )


def _elapsed_seconds(started: float) -> str:
    return f"{time.monotonic() - started:.2f}"


def _relay_websocket(client: socket.socket, upstream: socket.socket) -> None:
    sockets = [client, upstream]
    try:
        while True:
            readable, _, errored = select.select(sockets, [], sockets, 1.0)
            if errored:
                return
            for source in readable:
                try:
                    data = source.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                target = upstream if source is client else client
                try:
                    target.sendall(data)
                except OSError:
                    return
    finally:
        try:
            upstream.close()
        except OSError:
            pass


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
