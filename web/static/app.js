const state = {
  inputs: [],
  outputs: [],
  screens: [],
  selectedInput: null,
  selectedOutputs: new Set(),
  busy: false,
  history: [],
};

const previewReceivers = new Map();
const FRAME_HEADER_LENGTH = 17;

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refreshButton").addEventListener("click", loadConfig);
  document.getElementById("inputButtons").addEventListener("click", onInputClick);
  document.getElementById("outputButtons").addEventListener("click", onOutputClick);
  document.getElementById("routeGrid").addEventListener("click", onRouteCellClick);
  loadConfig();
});

async function loadConfig() {
  setDispatchState("busy", "读取中");
  try {
    const data = await fetchJson("/api/matrix/config");
    state.inputs = data.inputs || [];
    state.outputs = data.outputs || [];
    state.screens = data.screens || [];
    state.selectedInput = state.selectedInput || state.inputs[0]?.index || null;

    const server = data.server || {};
    document.getElementById("serverStatus").textContent =
      `${server.name || "服务器"} ${server.ip || ""}`.trim();

    renderAll();
    setDispatchState("ok", "就绪");
  } catch (error) {
    setDispatchState("error", error.message);
  }
}

function renderAll() {
  renderScreens();
  renderButtons();
  renderRouteGrid();
  renderPendingCommand();
  renderHistory();
}

function renderScreens() {
  const screenRow = document.getElementById("screenRow");
  screenRow.innerHTML = state.screens.map((screen) => {
    const assignment = screen.assignment;
    const output = screen.output || {};
    const active = Boolean(assignment);
    const inputName = assignment?.input?.name || "未接入";
    const inputIp = assignment?.input?.ip || "";
    const command = assignment?.command || "";

    return `
      <article class="screen ${active ? "active" : ""}" data-screen="${screen.index}">
        <canvas id="preview-${screen.index}" width="960" height="540"></canvas>
        <div class="screen-meta">
          <div class="screen-topline">
            <div class="screen-label">输出${screen.index} ${escapeHtml(output.name || "")}</div>
            <div class="stream-state" id="stream-state-${screen.index}">
              ${active ? "已调度" : "待机"}
            </div>
          </div>
          <div class="screen-center" id="screen-center-${screen.index}">
            <strong>${escapeHtml(inputName)}</strong>
            <span>${escapeHtml(inputIp || output.ip || "")}</span>
          </div>
          <div class="screen-bottomline">
            <div class="command-chip">${escapeHtml(command || `OUT${screen.index}`)}</div>
          </div>
        </div>
      </article>
    `;
  }).join("");

  for (const screen of state.screens) {
    const canvas = document.getElementById(`preview-${screen.index}`);
    drawIdlePreview(canvas, screen);
  }
}

function renderButtons() {
  const inputButtons = document.getElementById("inputButtons");
  inputButtons.innerHTML = state.inputs.map((input) => `
    <button
      class="matrix-button ${input.index === state.selectedInput ? "selected" : ""}"
      data-input="${input.index}"
      aria-pressed="${input.index === state.selectedInput}"
      ${state.busy ? "disabled" : ""}
      type="button">
      <strong>输入${input.index} ${escapeHtml(input.name)}</strong>
      <span>${escapeHtml(input.ip)}</span>
    </button>
  `).join("");

  const outputButtons = document.getElementById("outputButtons");
  outputButtons.innerHTML = state.outputs.map((output) => `
    <button
      class="matrix-button ${state.selectedOutputs.has(output.index) ? "selected" : ""}"
      data-output="${output.index}"
      aria-pressed="${state.selectedOutputs.has(output.index)}"
      ${state.busy ? "disabled" : ""}
      type="button">
      <strong>输出${output.index} ${escapeHtml(output.name)}</strong>
      <span>${escapeHtml(output.ip)}</span>
    </button>
  `).join("");
}

function renderRouteGrid() {
  const grid = document.getElementById("routeGrid");
  const headings = [
    `<div class="route-heading">输入/输出</div>`,
    ...state.outputs.map((output) => (
      `<div class="route-heading">输出${output.index}</div>`
    )),
  ];

  const rows = state.inputs.flatMap((input) => {
    const cells = state.outputs.map((output) => {
      const command = `${input.index}v${output.index}.`;
      const selected = input.index === state.selectedInput &&
        state.selectedOutputs.has(output.index);
      return `
        <button
          class="route-cell ${selected ? "selected" : ""}"
          data-input="${input.index}"
          data-output="${output.index}"
          ${state.busy ? "disabled" : ""}
          type="button">${command}</button>
      `;
    });
    return [`<div class="route-row-label">输入${input.index}</div>`, ...cells];
  });

  grid.innerHTML = [...headings, ...rows].join("");
}

function renderPendingCommand() {
  const pending = document.getElementById("pendingCommand");
  if (!state.selectedInput) {
    pending.textContent = "等待选择输入";
    return;
  }
  const outputs = [...state.selectedOutputs].sort((a, b) => a - b);
  if (!outputs.length) {
    pending.textContent = `输入${state.selectedInput} 已选`;
    return;
  }
  pending.textContent = outputs.map((output) => `${state.selectedInput}v${output}.`).join(" ");
}

function renderHistory() {
  const history = document.getElementById("history");
  history.textContent = state.history.slice(0, 6).join("  ");
}

function onInputClick(event) {
  const button = event.target.closest("[data-input]");
  if (!button || state.busy) {
    return;
  }
  state.selectedInput = Number(button.dataset.input);
  renderAll();

  const outputs = [...state.selectedOutputs];
  if (outputs.length) {
    dispatch(outputs);
  }
}

function onOutputClick(event) {
  const button = event.target.closest("[data-output]");
  if (!button || state.busy) {
    return;
  }

  const output = Number(button.dataset.output);
  if (state.selectedOutputs.has(output)) {
    state.selectedOutputs.delete(output);
    renderAll();
    return;
  }

  state.selectedOutputs.add(output);
  renderAll();
  dispatch([output]);
}

function onRouteCellClick(event) {
  const button = event.target.closest("[data-input][data-output]");
  if (!button || state.busy) {
    return;
  }

  const input = Number(button.dataset.input);
  const output = Number(button.dataset.output);
  state.selectedInput = input;
  state.selectedOutputs.add(output);
  renderAll();
  dispatch([output]);
}

async function dispatch(outputs) {
  if (!state.selectedInput || !outputs.length) {
    renderPendingCommand();
    return;
  }

  state.busy = true;
  renderButtons();
  renderRouteGrid();
  const commands = outputs.map((output) => `${state.selectedInput}v${output}.`);
  setDispatchState("busy", commands.join(" "));

  try {
    const response = await fetchJson("/api/matrix/switch", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        input: state.selectedInput,
        outputs,
      }),
    });

    if (!isApiSuccess(response)) {
      throw new Error(response.result || "矩阵切换失败");
    }

    applyRoutes(response.routes || []);
    state.history = [...commands, ...state.history].slice(0, 12);
    setDispatchState("ok", "已发送");
  } catch (error) {
    setDispatchState("error", error.message);
  } finally {
    state.busy = false;
    renderButtons();
    renderRouteGrid();
    renderPendingCommand();
    renderHistory();
  }
}

function applyRoutes(routes) {
  for (const route of routes) {
    const outputIndex = Number(route.output?.index);
    const screen = state.screens.find((item) => item.index === outputIndex);
    if (screen) {
      screen.assignment = route;
    }
  }

  renderScreens();
  for (const route of routes) {
    startPreview(route);
  }
}

function startPreview(route) {
  const outputIndex = Number(route.output?.index);
  if (!outputIndex) {
    return;
  }

  const oldReceiver = previewReceivers.get(outputIndex);
  if (oldReceiver) {
    oldReceiver.stop();
  }

  const receiver = new PreviewReceiver(outputIndex, route.stream);
  previewReceivers.set(outputIndex, receiver);
  receiver.start();
}

class PreviewReceiver {
  constructor(outputIndex, stream) {
    this.outputIndex = outputIndex;
    this.stream = stream;
    this.candidates = normalizeStreamCandidates(stream);
    this.candidateIndex = 0;
    this.activeCandidate = null;
    this.ws = null;
    this.decoder = null;
    this.connectUrl = "";
    this.decodeDisabled = false;
    this.timestamp = 0;
    this.bytes = 0;
    this.frames = 0;
    this.decodedFrames = 0;
    this.lastFrame = null;
    this.waitTimer = null;
    this.connectTimer = null;
  }

  start() {
    if (!this.stream?.ws_url || !window.WebSocket) {
      this.drawState("已调度", "浏览器不可连接取流服务");
      return;
    }

    this.startCandidate(0);
  }

  startCandidate(index) {
    const candidate = this.candidates[index];
    if (!candidate) {
      this.drawState("取流失败", "没有可用取流通道");
      this.setStreamState("取流失败");
      return;
    }

    this.candidateIndex = index;
    this.activeCandidate = candidate;
    this.decodeDisabled = false;
    this.timestamp = 0;
    this.bytes = 0;
    this.frames = 0;
    this.decodedFrames = 0;
    this.lastFrame = null;
    this.connectUrl = resolveWsUrl(this.stream.ws_proxy_path || this.stream.ws_url);
    this.report("candidate_start");

    try {
      const useDirectProtocol = !this.stream.ws_proxy_path;
      const protocol = useDirectProtocol ? String(this.stream.ws_protocol || "").trim() : "";
      this.ws = protocol
        ? new WebSocket(this.connectUrl, protocol)
        : new WebSocket(this.connectUrl);
      this.ws.binaryType = "arraybuffer";
      this.connectTimer = window.setTimeout(() => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
          this.tryNextCandidate("连接超时");
        }
      }, 5000);
      this.ws.onopen = () => {
        this.clearConnectTimer();
        this.report("ws_open");
        this.ws.send(JSON.stringify(candidate.open_header));
        this.setStreamState(`等待码流 ${candidate.channel}`);
        this.drawState("等待码流", candidate.channel);
        this.waitTimer = window.setTimeout(() => {
          if (!this.frames) {
            this.tryNextCandidate("未收到码流");
          }
        }, 3000);
      };
      this.ws.onmessage = (event) => this.onMessage(event.data);
      this.ws.onerror = () => {
        this.tryNextCandidate("取流异常");
      };
      this.ws.onclose = () => {
        if (!this.frames) {
          this.tryNextCandidate("取流已断开");
        }
      };
    } catch (error) {
      this.tryNextCandidate(error.message || "取流失败");
    }
  }

  stop() {
    if (this.waitTimer) {
      window.clearTimeout(this.waitTimer);
      this.waitTimer = null;
    }
    this.clearConnectTimer();

    if (this.decoder) {
      this.closeDecoder();
    }

    this.closeActiveSocket();
  }

  onMessage(data) {
    if (typeof data === "string") {
      this.setStreamState(data.slice(0, 24));
      this.drawState("取流消息", data.slice(0, 80));
      this.report("text_message", {detail: data.slice(0, 160)});
      return;
    }

    const frame = parseStreamFrame(data);
    if (!frame) {
      this.setStreamState("码流接收中");
      return;
    }

    if (this.waitTimer) {
      window.clearTimeout(this.waitTimer);
      this.waitTimer = null;
    }

    this.bytes += frame.payload.byteLength;
    this.frames += 1;
    this.lastFrame = frame;
    if (this.frames === 1) {
      this.report("first_frame", {
        codec: codecName(frame.codec),
        width: frame.width,
        height: frame.height,
        detail: streamTypeName(frame.streamType),
      });
    }
    if (frame.streamType !== 1) {
      this.setStreamState(`收到${streamTypeName(frame.streamType)}`);
      return;
    }

    const decodeResult = this.tryDecode(frame);
    if (decodeResult === "retrying") {
      return;
    }

    if (!decodeResult) {
      drawActivityPreview(this.canvas(), frame, this.bytes);
    }
    this.setStreamState(
      `接收 ${codecName(frame.codec)} ${frame.width || "-"}x${frame.height || "-"}`
    );
  }

  tryDecode(frame) {
    if (frame.codec === 3) {
      return this.tryNextCandidate("收到 H.265") ? "retrying" : true;
    }

    if (this.decodeDisabled || frame.codec !== 2 || !window.VideoDecoder || !window.EncodedVideoChunk) {
      return false;
    }

    if (!this.decoder) {
      try {
        this.decoder = new VideoDecoder({
          output: (videoFrame) => {
            const canvas = this.canvas();
            if (canvas) {
              const ctx = prepareCanvas(canvas);
              ctx.drawImage(videoFrame, 0, 0, canvas.width, canvas.height);
            }
            this.decodedFrames += 1;
            if (this.decodedFrames === 1) {
              this.report("decode_ok", {
                codec: codecName(frame.codec),
                width: videoFrame.displayWidth || frame.width,
                height: videoFrame.displayHeight || frame.height,
              });
            }
            videoFrame.close();
            this.setStreamState(`解码 ${formatBytes(this.bytes)}`);
          },
          error: () => {
            this.decodeDisabled = true;
            this.tryNextCandidate("H.264 解码失败");
          },
        });
        const config = {
          codec: "avc1.42E01E",
          codedWidth: frame.width || 1920,
          codedHeight: frame.height || 1080,
          avc: {format: "annexb"},
        };
        this.decoder.configure(config);
      } catch (error) {
        this.decodeDisabled = true;
        return this.tryNextCandidate("H.264 解码失败") ? "retrying" : true;
      }
    }

    try {
      this.timestamp += 33333;
      const chunk = new EncodedVideoChunk({
        type: frame.frameType === 1 ? "key" : "delta",
        timestamp: this.timestamp,
        data: frame.payload,
      });
      this.decoder.decode(chunk);
      return true;
    } catch (error) {
      this.decodeDisabled = true;
      return this.tryNextCandidate("H.264 解码失败") ? "retrying" : true;
    }
  }

  tryNextCandidate(reason) {
    if (this.waitTimer) {
      window.clearTimeout(this.waitTimer);
      this.waitTimer = null;
    }
    this.clearConnectTimer();

    const currentChannel = this.activeCandidate?.channel || "";
    const nextIndex = this.candidateIndex + 1;
    this.report("candidate_failed", {reason});
    if (nextIndex >= this.candidates.length) {
      this.closeDecoder();
      this.closeActiveSocket();
      this.setStreamState(reason);
      const detail = currentChannel || this.stream.channel || "";
      if (reason === "收到 H.265") {
        this.drawState("收到 H.265", "已尝试所有取流通道，浏览器预览暂不能解码");
      } else if (this.lastFrame) {
        drawActivityPreview(this.canvas(), this.lastFrame, this.bytes, reason);
      } else {
        this.drawState(reason, detail);
      }
      return false;
    }

    this.setStreamState(`${reason}，尝试下一路`);
    this.closeDecoder();
    this.closeActiveSocket();
    this.startCandidate(nextIndex);
    return true;
  }

  report(event, extra = {}) {
    reportPreviewEvent({
      output: this.outputIndex,
      event,
      ws_url: this.stream.ws_url,
      connect_url: this.connectUrl || this.stream.ws_url,
      ws_protocol: this.stream.ws_protocol || "",
      channel: this.activeCandidate?.channel || this.stream.channel || "",
      bytes: this.bytes,
      frames: this.frames,
      ...extra,
    });
  }

  clearConnectTimer() {
    if (this.connectTimer) {
      window.clearTimeout(this.connectTimer);
      this.connectTimer = null;
    }
  }

  closeDecoder() {
    if (!this.decoder) {
      return;
    }

    try {
      this.decoder.close();
    } catch (error) {
      // 关闭失败不影响重新切换。
    }
    this.decoder = null;
  }

  closeActiveSocket() {
    if (!this.ws) {
      return;
    }

    const socket = this.ws;
    this.ws = null;
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    try {
      if (socket.readyState === WebSocket.OPEN) {
        const closeHeader = this.activeCandidate?.close_header || this.stream.close_header;
        socket.send(JSON.stringify(closeHeader));
      }
      socket.close();
    } catch (error) {
      // 关闭失败不影响尝试下一路取流。
    }
  }

  canvas() {
    return document.getElementById(`preview-${this.outputIndex}`);
  }

  drawState(title, detail) {
    drawMessage(this.canvas(), title, detail);
  }

  setStreamState(text) {
    const node = document.getElementById(`stream-state-${this.outputIndex}`);
    if (node) {
      node.textContent = text;
    }
  }
}

function parseStreamFrame(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength <= FRAME_HEADER_LENGTH) {
    return null;
  }

  const view = new DataView(buffer);
  return {
    version: String.fromCharCode(view.getUint8(0), view.getUint8(1)),
    streamType: view.getUint8(2),
    sequence: readUint32(view, 3),
    width: readUint16(view, 7),
    height: readUint16(view, 9),
    codec: view.getUint8(11),
    frameType: view.getUint8(12),
    timestamp: readUint32(view, 13),
    payload: new Uint8Array(buffer, FRAME_HEADER_LENGTH),
  };
}

function readUint16(view, offset) {
  const be = view.getUint16(offset, false);
  const le = view.getUint16(offset, true);
  return be > 0 && be < 10000 ? be : le;
}

function readUint32(view, offset) {
  const be = view.getUint32(offset, false);
  const le = view.getUint32(offset, true);
  return be > 0 && be < 2147483647 ? be : le;
}

function drawIdlePreview(canvas, screen) {
  const assignment = screen.assignment;
  const title = assignment?.input?.name || `输出${screen.index}`;
  const detail = assignment ? assignment.command : "无信号";
  drawMessage(canvas, title, detail);
}

function drawMessage(canvas, title, detail) {
  if (!canvas) {
    return;
  }

  const ctx = prepareCanvas(canvas);
  ctx.fillStyle = "#101419";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#2c3541";
  ctx.lineWidth = 2;
  ctx.strokeRect(18, 18, canvas.width - 36, canvas.height - 36);
  ctx.fillStyle = "#e8edf2";
  ctx.font = "600 30px Microsoft YaHei, Segoe UI, Arial";
  ctx.textAlign = "center";
  ctx.fillText(title || "", canvas.width / 2, canvas.height / 2 - 10);
  ctx.fillStyle = "#97a3b0";
  ctx.font = "22px Microsoft YaHei, Segoe UI, Arial";
  ctx.fillText(detail || "", canvas.width / 2, canvas.height / 2 + 30);
}

function drawActivityPreview(canvas, frame, bytes, title = "收到码流") {
  if (!canvas) {
    return;
  }

  const ctx = prepareCanvas(canvas);
  ctx.fillStyle = "#101419";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const bars = 18;
  const gap = 6;
  const barWidth = (canvas.width - gap * (bars + 1)) / bars;
  const payload = frame.payload;
  for (let index = 0; index < bars; index += 1) {
    const sample = payload.length ? payload[(index * 97) % payload.length] : 80;
    const height = Math.max(28, (sample / 255) * (canvas.height * 0.72));
    const x = gap + index * (barWidth + gap);
    const y = canvas.height - height - 42;
    ctx.fillStyle = index % 3 === 0 ? "#0f766e" : index % 3 === 1 ? "#3b5368" : "#b45309";
    ctx.fillRect(x, y, barWidth, height);
  }

  ctx.fillStyle = "#e8edf2";
  ctx.font = "600 28px Microsoft YaHei, Segoe UI, Arial";
  ctx.textAlign = "left";
  ctx.fillText(`${title}  ${frame.width || "-"}x${frame.height || "-"}  ${codecName(frame.codec)}`, 28, 42);
  ctx.fillStyle = "#97a3b0";
  ctx.font = "20px Microsoft YaHei, Segoe UI, Arial";
  ctx.fillText(`码流 ${formatBytes(bytes)}`, 28, canvas.height - 20);
}

function prepareCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * ratio));
  const height = Math.max(1, Math.floor(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return canvas.getContext("2d");
}

function setDispatchState(type, text) {
  const node = document.getElementById("dispatchState");
  node.className = `dispatch-state ${type || ""}`;
  node.textContent = text;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.result || data.error || response.statusText);
  }
  return data;
}

function isApiSuccess(payload) {
  return payload?.result === "success" || payload?.result_val === 0;
}

function normalizeStreamCandidates(stream) {
  const rawCandidates = Array.isArray(stream?.candidates) && stream.candidates.length
    ? stream.candidates
    : [{
        channel: stream?.channel || stream?.open_header?.c || "",
        open_header: stream?.open_header,
        close_header: stream?.close_header,
      }];

  return rawCandidates
    .filter((candidate) => candidate?.open_header?.c)
    .map((candidate) => ({
      channel: candidate.channel || candidate.open_header.c,
      open_header: candidate.open_header,
      close_header: candidate.close_header || {
        ...candidate.open_header,
        t: "close",
      },
    }));
}

function resolveWsUrl(url) {
  if (!url || !url.startsWith("/")) {
    return url;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${url}`;
}

function reportPreviewEvent(payload) {
  try {
    fetch("/api/preview/event", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    }).catch(() => {});
  } catch (error) {
    // 诊断日志失败不影响预览。
  }
}

function codecName(codec) {
  if (codec === 2) {
    return "H.264";
  }
  if (codec === 3) {
    return "H.265";
  }
  return `Codec ${codec}`;
}

function streamTypeName(type) {
  if (type === 1) {
    return "视频帧";
  }
  if (type === 2) {
    return "音频帧";
  }
  return `类型${type}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
