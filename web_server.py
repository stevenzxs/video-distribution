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
import sys
import time
from dataclasses import dataclass
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
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
PREVIEW_CONTROL_OPTIONAL_RESULT_TIMEOUT_SECONDS = 1.0
PREVIEW_CONTROL_PULSE_RESULT_TIMEOUT_SECONDS = 2.0
PREVIEW_CONTROL_PULSE_TEXT = "pulse"
PREVIEW_BROWSER_WS_EXTENSIONS = "permessage-deflate; client_max_window_bits"

def _configure_logging() -> None:
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )


_configure_logging()
logger = logging.getLogger(__name__)


@dataclass
class UpstreamWebSocket:
    sock: socket.socket
    headers: Dict[str, str]
    initial_data: bytes = b""
    first_line: str = ""
    handshake_elapsed: str = ""


class MatrixHTTPRequestHandler(BaseHTTPRequestHandler):
    scheduler = MatrixScheduler()

    def do_OPTIONS(self) -> None:
        self._send_empty(204)

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        logger.info(
            "收到GET: path=%s, query=%s, host=%s",
            path,
            parsed_path.query or "-",
            self.headers.get("Host", "-"),
        )
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
        control_protocol = str(stream.get("control_ws_protocol") or stream.get("ws_protocol") or "")
        stream_protocol = str(stream.get("stream_ws_protocol") or "")
        client_protocol = self.headers.get("Sec-WebSocket-Protocol", "")
        client_extensions = self.headers.get("Sec-WebSocket-Extensions", "")
        user_agent = self.headers.get("User-Agent", DEFAULT_PREVIEW_USER_AGENT)
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self._send_json({"error": "missing Sec-WebSocket-Key"}, 400)
            return

        logger.info(
            (
                "预览代理请求: output=%s, control_url=%s, stream_url=%s, "
                "candidates=%s, control_protocol=%s, stream_protocol=%s, "
                "client_protocol=%s, client_extensions=%s, user_agent=%s"
            ),
            output,
            control_url or "-",
            upstream_url or "-",
            _preview_candidates_summary(stream),
            _preview_protocol_summary(control_protocol),
            _preview_protocol_summary(stream_protocol),
            _preview_protocol_summary(client_protocol),
            "yes" if client_extensions else "no",
            user_agent[:120],
        )

        stage = "control" if control_url else "stream"
        try:
            if control_url:
                control_result = _call_preview_control_ws(
                    control_url,
                    origin=API_BASE_URL,
                    protocol=control_protocol,
                    user_agent=user_agent,
                )
                logger.info(
                    "预览视频调度确认: output=%s, url=%s, result=%s",
                    output,
                    control_url,
                    _preview_control_result_summary(control_result),
                )
                stage = "stream"
            logger.info(
                (
                    "预览代理开始取流连接: output=%s, url=%s, origin=%s, "
                    "protocol=%s, extensions=%s"
                ),
                output,
                upstream_url,
                API_BASE_URL,
                _preview_protocol_summary(stream_protocol),
                "yes" if client_extensions else "no",
            )
            upstream = _open_upstream_websocket(
                upstream_url,
                origin=API_BASE_URL,
                protocol=stream_protocol,
                extensions=client_extensions,
                user_agent=user_agent,
            )
        except OSError as exc:
            logger.error(
                (
                    "预览代理连接上游失败: output=%s, stage=%s, "
                    "control_url=%s, url=%s, "
                    "control_protocol=%s, stream_protocol=%s, "
                    "extensions=%s, timeout=%ss, error=%s: %s"
                ),
                output,
                "调度确认" if stage == "control" else "取流",
                control_url,
                upstream_url,
                "yes" if control_protocol else "no",
                "yes" if stream_protocol else "no",
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
        response_protocol = upstream.headers.get("sec-websocket-protocol", "")
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
            (
                "预览代理已连接: output=%s, upstream=%s, origin=%s, "
                "protocol=%s, first_line=%s, handshake_elapsed=%ss, "
                "upstream_protocol=%s, upstream_extensions=%s, initial_bytes=%d"
            ),
            output,
            upstream_url,
            API_BASE_URL,
            _preview_protocol_summary(stream_protocol),
            upstream.first_line,
            upstream.handshake_elapsed or "-",
            _preview_protocol_summary(upstream.headers.get("sec-websocket-protocol", "")),
            "yes" if upstream.headers.get("sec-websocket-extensions") else "no",
            len(upstream.initial_data),
        )
        if upstream.initial_data:
            self.request.sendall(upstream.initial_data)
        _relay_websocket(
            self.request,
            upstream.sock,
            context=f"output={output}, upstream={upstream_url}",
        )

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        logger.info(
            "收到POST: path=%s, content_length=%s, content_type=%s",
            path,
            self.headers.get("Content-Length", "0"),
            self.headers.get("Content-Type", "-"),
        )
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

        if path == "/api/matrix/output/close":
            try:
                payload = self._read_json()
                logger.info("关闭输出请求: payload=%s", payload)
                output = _output_from_payload(payload)
                result = self.scheduler.close_output(output)
                self._send_json(result)
            except MatrixError as exc:
                logger.warning("关闭输出窗口失败: %s", exc)
                self._send_json(
                    {"result": str(exc), "result_val": 3},
                    exc.status_code,
                )
            except Exception as exc:
                logger.exception("关闭输出窗口失败")
                self._send_json(
                    {"result": f"关闭输出窗口失败: {exc}", "result_val": 8},
                    500,
                )
            return

        if path != "/api/matrix/switch":
            self._send_json({"error": "not found"}, 404)
            return

        try:
            payload = self._read_json()
            logger.info("矩阵切换请求: payload=%s", payload)
            commands = _commands_from_payload(payload)
            logger.info("矩阵切换命令: %s", commands)
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
        logger.info(
            "收到JSON请求体: path=%s, body=%s",
            urlparse(self.path).path,
            raw.decode("utf-8", errors="replace"),
        )
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
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
        self.send_header("Cache-Control", "no-store")
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
            self.send_header("Cache-Control", "no-store")
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


def _output_from_payload(payload: Dict[str, Any]) -> int:
    try:
        output = int(payload.get("output"))
    except (TypeError, ValueError):
        raise MatrixError("缺少输出编号")
    if output < 1:
        raise MatrixError("输出编号必须大于0")
    return output


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
        "candidate_index",
        "candidate_count",
        "next_channel",
        "elapsed_ms",
        "connect_elapsed_ms",
        "first_frame_elapsed_ms",
        "ready_state",
        "close_code",
        "close_reason",
        "was_clean",
        "packet_bytes",
        "payload_bytes",
        "frame_type",
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
    started = time.monotonic()
    upstream = _open_upstream_websocket(
        ws_url,
        origin=origin,
        protocol=protocol,
        extensions=PREVIEW_BROWSER_WS_EXTENSIONS,
        user_agent=user_agent or DEFAULT_PREVIEW_USER_AGENT,
    )
    frame_count = 0
    pulse_sent = False
    try:
        upstream.sock.settimeout(PREVIEW_CONTROL_OPTIONAL_RESULT_TIMEOUT_SECONDS)
        frame_buffer = bytearray(upstream.initial_data)
        logger.info(
            (
                "预览控制WS等待结果: url=%s, origin=%s, protocol=%s, "
                "handshake_elapsed=%ss, initial_bytes=%d, result_timeout=%ss"
            ),
            ws_url,
            origin or "-",
            _preview_protocol_summary(protocol),
            upstream.handshake_elapsed or "-",
            len(upstream.initial_data),
            PREVIEW_CONTROL_OPTIONAL_RESULT_TIMEOUT_SECONDS,
        )
        for frame_index in range(1, 6):
            try:
                opcode, payload = _recv_ws_frame(upstream.sock, frame_buffer)
            except TimeoutError:
                if not pulse_sent:
                    _send_ws_text_frame(upstream.sock, PREVIEW_CONTROL_PULSE_TEXT)
                    pulse_sent = True
                    upstream.sock.settimeout(PREVIEW_CONTROL_PULSE_RESULT_TIMEOUT_SECONDS)
                    logger.info(
                        (
                            "预览控制WS发送心跳: url=%s, payload=%s, "
                            "wait_timeout=%ss, elapsed=%ss"
                        ),
                        ws_url,
                        PREVIEW_CONTROL_PULSE_TEXT,
                        PREVIEW_CONTROL_PULSE_RESULT_TIMEOUT_SECONDS,
                        _elapsed_seconds(started),
                    )
                    continue

                result = _preview_control_handshake_only_result("idle_timeout_after_pulse")
                logger.warning(
                    (
                        "预览控制WS握手和心跳后未返回JSON结果，按握手成功继续取流: "
                        "url=%s, origin=%s, protocol=%s, elapsed=%ss, "
                        "frames=%d, optional_result_timeout=%ss, pulse_result_timeout=%ss"
                    ),
                    ws_url,
                    origin or "-",
                    _preview_protocol_summary(protocol),
                    _elapsed_seconds(started),
                    frame_count,
                    PREVIEW_CONTROL_OPTIONAL_RESULT_TIMEOUT_SECONDS,
                    PREVIEW_CONTROL_PULSE_RESULT_TIMEOUT_SECONDS,
                )
                return result

            frame_count = frame_index
            logger.info(
                (
                    "预览控制WS收到帧: url=%s, frame=%d, opcode=%s, "
                    "payload_bytes=%d, elapsed=%ss, sample=%s"
                ),
                ws_url,
                frame_index,
                _preview_ws_opcode_name(opcode),
                len(payload),
                _elapsed_seconds(started),
                _preview_payload_sample(opcode, payload),
            )
            if opcode in (0x1, 0x2):
                result = _parse_preview_control_result_or_pulse(payload)
                if result is None:
                    continue
                if not is_success_response(result):
                    raise OSError(
                        "preview control websocket returned "
                        f"{_preview_control_result_summary(result)}"
                    )
                logger.info(
                    "预览控制WS结果成功: url=%s, result=%s, elapsed=%ss",
                    ws_url,
                    _preview_control_result_summary(result),
                    _elapsed_seconds(started),
                )
                return result
            if opcode == 0x8:
                raise OSError("preview control websocket closed before result")
            if opcode == 0x9:
                _send_ws_client_frame(upstream.sock, 0xA, payload)
                continue
            if opcode == 0xA:
                continue

        result = _preview_control_handshake_only_result("non_result_frames")
        logger.warning(
            (
                "预览控制WS未返回结果帧，按握手成功继续取流: "
                "url=%s, frames=%d, elapsed=%ss"
            ),
            ws_url,
            frame_count,
            _elapsed_seconds(started),
        )
        return result
    except TimeoutError as exc:
        result = _preview_control_handshake_only_result("idle_timeout")
        logger.warning(
            (
                "预览控制WS握手后未返回结果帧，按握手成功继续取流: "
                "url=%s, origin=%s, protocol=%s, elapsed=%ss, "
                "frames=%d, optional_result_timeout=%ss"
            ),
            ws_url,
            origin or "-",
            _preview_protocol_summary(protocol),
            _elapsed_seconds(started),
            frame_count,
            PREVIEW_CONTROL_OPTIONAL_RESULT_TIMEOUT_SECONDS,
        )
        return result
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


def _parse_preview_control_result_or_pulse(payload: bytes) -> Optional[Dict[str, Any]]:
    text = payload.decode("utf-8", errors="replace").strip()
    if text == PREVIEW_CONTROL_PULSE_TEXT:
        logger.info("预览控制WS收到心跳: payload=%s", text)
        return None
    return _parse_preview_control_payload(payload)


def _preview_control_result_summary(result: Dict[str, Any]) -> str:
    return ", ".join(
        f"{key}={result.get(key)}"
        for key in ("result", "result_val", "handle", "control_ws_mode", "reason")
        if key in result
    ) or str(result)[:160]


def _preview_control_handshake_only_result(reason: str) -> Dict[str, Any]:
    return {
        "result": "success",
        "result_val": 0,
        "control_ws_mode": "handshake_only",
        "reason": reason,
    }


def _preview_candidates_summary(stream: Dict[str, Any]) -> str:
    candidates = stream.get("candidates")
    if not isinstance(candidates, list):
        return str(stream.get("channel") or "-")
    channels = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        channel = candidate.get("channel") or (candidate.get("open_header") or {}).get("c")
        if channel:
            channels.append(str(channel))
    return ", ".join(channels) if channels else "-"


def _preview_protocol_summary(protocol: str) -> str:
    value = str(protocol or "").strip()
    if not value:
        return "no"
    digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"yes(len={len(value)},sha1={digest})"


def _preview_ws_opcode_name(opcode: int) -> str:
    names = {
        0x0: "continuation",
        0x1: "text",
        0x2: "binary",
        0x8: "close",
        0x9: "ping",
        0xA: "pong",
    }
    return f"{names.get(opcode, 'unknown')}({opcode})"


def _preview_payload_sample(opcode: int, payload: bytes) -> str:
    if not payload:
        return "-"
    if opcode == 0x1:
        return payload.decode("utf-8", errors="replace").strip()[:160]
    return payload[:32].hex()


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
    logger.info(
        (
            "预览上游WS握手开始: url=%s, origin=%s, protocol=%s, "
            "extensions=%s, tcp_timeout=%ss, handshake_timeout=%ss"
        ),
        ws_url,
        origin or "-",
        _preview_protocol_summary(protocol),
        "yes" if extensions else "no",
        PREVIEW_TCP_CONNECT_TIMEOUT_SECONDS,
        PREVIEW_UPSTREAM_HANDSHAKE_TIMEOUT_SECONDS,
    )
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
        logger.info(
            "预览上游WS TCP已连接: url=%s, elapsed=%ss",
            ws_url,
            _elapsed_seconds(started),
        )
        sock.settimeout(PREVIEW_UPSTREAM_HANDSHAKE_TIMEOUT_SECONDS)
        sock.sendall(request.encode("ascii"))
        response, initial_data = _recv_http_headers(sock)
        first_line = response.splitlines()[0] if response else ""
        elapsed = _elapsed_seconds(started)
        parsed_headers = _parse_http_headers(response)
        if " 101 " not in f" {first_line} ":
            logger.warning(
                (
                    "预览上游WS握手拒绝: url=%s, first_line=%s, "
                    "elapsed=%ss, headers=%s, initial_bytes=%d"
                ),
                ws_url,
                first_line[:160] or "-",
                elapsed,
                _preview_headers_summary(parsed_headers),
                len(initial_data),
            )
            raise OSError(f"upstream handshake rejected: {first_line[:160]}")
        logger.info(
            (
                "预览上游WS握手成功: url=%s, first_line=%s, "
                "elapsed=%ss, headers=%s, initial_bytes=%d"
            ),
            ws_url,
            first_line[:160],
            elapsed,
            _preview_headers_summary(parsed_headers),
            len(initial_data),
        )
        sock.settimeout(None)
        return UpstreamWebSocket(
            sock=sock,
            headers=parsed_headers,
            initial_data=initial_data,
            first_line=first_line[:160],
            handshake_elapsed=elapsed,
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


def _preview_headers_summary(headers: Dict[str, str]) -> str:
    parts = [
        f"protocol={_preview_protocol_summary(headers.get('sec-websocket-protocol', ''))}",
        "extensions=yes" if headers.get("sec-websocket-extensions") else "extensions=no",
    ]
    for key in ("server", "keep-alive"):
        value = headers.get(key)
        if value:
            parts.append(f"{key}={value[:80]}")
    return ", ".join(parts)


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


def _send_ws_text_frame(sock: socket.socket, text: str) -> None:
    _send_ws_client_frame(sock, 0x1, text.encode("utf-8"))


def _send_ws_client_frame(sock: socket.socket, opcode: int, payload: bytes) -> None:
    first_byte = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        header = bytes([first_byte, 0x80 | length])
    elif length < 65536:
        header = bytes([first_byte, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first_byte, 0x80 | 127]) + length.to_bytes(8, "big")

    mask = os.urandom(4)
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    sock.sendall(header + mask + masked)


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


def _relay_websocket(
    client: socket.socket,
    upstream: socket.socket,
    context: str = "",
) -> None:
    sockets = [client, upstream]
    started = time.monotonic()
    client_to_upstream_bytes = 0
    upstream_to_client_bytes = 0
    client_to_upstream_chunks = 0
    upstream_to_client_chunks = 0
    first_client_chunk_logged = False
    first_upstream_chunk_logged = False
    reason = "unknown"
    try:
        while True:
            readable, _, errored = select.select(sockets, [], sockets, 1.0)
            if errored:
                reason = "select_error"
                return
            for source in readable:
                try:
                    data = source.recv(65536)
                except OSError:
                    reason = "recv_error"
                    return
                if not data:
                    reason = "closed_by_client" if source is client else "closed_by_upstream"
                    return
                target = upstream if source is client else client
                if source is client:
                    client_to_upstream_bytes += len(data)
                    client_to_upstream_chunks += 1
                    if not first_client_chunk_logged:
                        first_client_chunk_logged = True
                        logger.info(
                            (
                                "预览代理首个数据块: %s, direction=client_to_upstream, "
                                "bytes=%d, sample=%s"
                            ),
                            context or "-",
                            len(data),
                            _preview_ws_frame_sample_from_bytes(data),
                        )
                else:
                    upstream_to_client_bytes += len(data)
                    upstream_to_client_chunks += 1
                    if not first_upstream_chunk_logged:
                        first_upstream_chunk_logged = True
                        logger.info(
                            (
                                "预览代理首个数据块: %s, direction=upstream_to_client, "
                                "bytes=%d, sample=%s"
                            ),
                            context or "-",
                            len(data),
                            _preview_ws_frame_sample_from_bytes(data),
                        )
                try:
                    target.sendall(data)
                except OSError:
                    reason = "send_error"
                    return
    finally:
        logger.info(
            (
                "预览代理转发结束: %s, reason=%s, elapsed=%ss, "
                "client_to_upstream_bytes=%d, upstream_to_client_bytes=%d, "
                "client_to_upstream_chunks=%d, upstream_to_client_chunks=%d"
            ),
            context or "-",
            reason,
            _elapsed_seconds(started),
            client_to_upstream_bytes,
            upstream_to_client_bytes,
            client_to_upstream_chunks,
            upstream_to_client_chunks,
        )
        try:
            upstream.close()
        except OSError:
            pass


def _preview_ws_frame_sample_from_bytes(data: bytes) -> str:
    try:
        if len(data) < 2:
            return f"raw={data.hex() or '-'}"

        first_byte, second_byte = data[0], data[1]
        opcode = first_byte & 0x0F
        length = second_byte & 0x7F
        masked = bool(second_byte & 0x80)
        offset = 2
        if length == 126:
            if len(data) < offset + 2:
                return f"opcode={_preview_ws_opcode_name(opcode)}, incomplete_header"
            length = int.from_bytes(data[offset:offset + 2], "big")
            offset += 2
        elif length == 127:
            if len(data) < offset + 8:
                return f"opcode={_preview_ws_opcode_name(opcode)}, incomplete_header"
            length = int.from_bytes(data[offset:offset + 8], "big")
            offset += 8

        mask = b""
        if masked:
            if len(data) < offset + 4:
                return f"opcode={_preview_ws_opcode_name(opcode)}, incomplete_mask"
            mask = data[offset:offset + 4]
            offset += 4

        payload = bytearray(data[offset:offset + length])
        if len(payload) < length:
            return (
                f"opcode={_preview_ws_opcode_name(opcode)}, masked={masked}, "
                f"incomplete_payload={len(payload)}/{length}"
            )
        if masked:
            for index, value in enumerate(payload):
                payload[index] = value ^ mask[index % 4]

        return (
            f"opcode={_preview_ws_opcode_name(opcode)}, masked={masked}, "
            f"payload_bytes={length}, sample={_preview_payload_sample(opcode, bytes(payload))}"
        )
    except Exception as exc:
        return f"raw={data[:32].hex()}, parse_error={type(exc).__name__}: {exc}"


def main() -> None:
    _configure_logging()
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
