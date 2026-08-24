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
const PREVIEW_CONNECT_TIMEOUT_MS = 25000;
const PREVIEW_FIRST_FRAME_TIMEOUT_MS = 5000;

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("refreshButton").addEventListener("click", loadConfig);
  document.getElementById("inputButtons").addEventListener("click", onInputClick);
  document.getElementById("outputButtons").addEventListener("click", onOutputClick);
  document.getElementById("routeGrid").addEventListener("click", onRouteCellClick);
  document.getElementById("screenRow").addEventListener("click", onScreenClick);
  document.addEventListener("fullscreenchange", updateFullscreenButtons);
  document.addEventListener("webkitfullscreenchange", updateFullscreenButtons);
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
            <div class="screen-tools">
              <div class="stream-state" id="stream-state-${screen.index}">
                ${active ? "已调度" : "待机"}
              </div>
              <button
                class="fullscreen-button"
                data-fullscreen-screen="${screen.index}"
                type="button"
                title="全屏"
                aria-label="全屏查看输出${screen.index}">
                ⛶
              </button>
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
  updateFullscreenButtons();
}

function onScreenClick(event) {
  const button = event.target.closest("[data-fullscreen-screen]");
  if (!button) {
    return;
  }

  const screen = button.closest(".screen");
  if (screen) {
    toggleScreenFullscreen(screen);
  }
}

async function toggleScreenFullscreen(screen) {
  try {
    if (fullscreenElement() === screen) {
      await exitFullscreen();
    } else {
      await requestFullscreen(screen);
    }
  } catch (error) {
    setDispatchState("error", "浏览器未允许全屏");
  } finally {
    updateFullscreenButtons();
  }
}

function fullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

function requestFullscreen(element) {
  if (element.requestFullscreen) {
    return element.requestFullscreen();
  }
  if (element.webkitRequestFullscreen) {
    return element.webkitRequestFullscreen();
  }
  return Promise.reject(new Error("fullscreen unsupported"));
}

function exitFullscreen() {
  if (document.exitFullscreen) {
    return document.exitFullscreen();
  }
  if (document.webkitExitFullscreen) {
    return document.webkitExitFullscreen();
  }
  return Promise.resolve();
}

function updateFullscreenButtons() {
  const activeScreen = fullscreenElement();
  document.querySelectorAll("[data-fullscreen-screen]").forEach((button) => {
    const screen = button.closest(".screen");
    const active = screen && screen === activeScreen;
    button.textContent = active ? "×" : "⛶";
    button.title = active ? "退出全屏" : "全屏";
    button.setAttribute("aria-label", active ? "退出全屏" : `全屏查看输出${button.dataset.fullscreenScreen}`);
  });
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
    this.candidateStartedAt = 0;
    this.connectStartedAt = 0;
    this.unparsedPackets = 0;
    this.currentStreamState = "";
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
    this.unparsedPackets = 0;
    this.currentStreamState = "";
    this.candidateStartedAt = performance.now();
    this.connectStartedAt = this.candidateStartedAt;
    this.connectUrl = resolveWsUrl(this.stream.ws_proxy_path || this.stream.ws_url);
    this.setPreviewPlaying(false);
    this.report("candidate_start");

    try {
      const protocol = String(this.stream.ws_protocol || "").trim();
      this.ws = protocol
        ? new WebSocket(this.connectUrl, protocol)
        : new WebSocket(this.connectUrl);
      this.ws.binaryType = "arraybuffer";
      this.connectTimer = window.setTimeout(() => {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
          this.tryNextCandidate("连接超时");
        }
      }, PREVIEW_CONNECT_TIMEOUT_MS);
      this.ws.onopen = () => {
        this.clearConnectTimer();
        this.report("ws_open", {
          connect_elapsed_ms: this.elapsedSince(this.connectStartedAt),
        });
        const openHeaderText = JSON.stringify(candidate.open_header);
        this.ws.send(openHeaderText);
        this.report("open_header_sent", {
          detail: openHeaderText,
          connect_elapsed_ms: this.elapsedSince(this.connectStartedAt),
        });
        this.setStreamState(`等待码流 ${candidate.channel}`);
        this.drawState("等待码流", candidate.channel);
        this.waitTimer = window.setTimeout(() => {
          if (!this.frames) {
            this.tryNextCandidate("未收到码流");
          }
        }, PREVIEW_FIRST_FRAME_TIMEOUT_MS);
      };
      this.ws.onmessage = (event) => this.onMessage(event.data);
      this.ws.onerror = (event) => {
        this.report("ws_error", {
          detail: event?.message || "",
        });
        this.tryNextCandidate("取流异常");
      };
      this.ws.onclose = (event) => {
        this.report("ws_close", {
          close_code: event.code,
          close_reason: event.reason,
          was_clean: event.wasClean,
        });
        if (!this.frames) {
          this.tryNextCandidate("取流已断开");
        }
      };
    } catch (error) {
      this.report("ws_construct_failed", {
        detail: error.message || String(error),
      });
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

    this.setPreviewPlaying(false);
    this.closeActiveSocket();
  }

  onMessage(data) {
    if (typeof data === "string") {
      this.setStreamState(data.slice(0, 24));
      this.drawState("取流消息", data.slice(0, 80));
      this.report("text_message", {
        detail: data.slice(0, 160),
        packet_bytes: data.length,
      });
      return;
    }

    const packetBytes = data instanceof ArrayBuffer ? data.byteLength : 0;
    const frame = parseStreamFrame(
      data,
      this.activeCandidate?.channel || this.stream.channel || ""
    );
    if (!frame) {
      this.setStreamState("码流接收中");
      this.unparsedPackets += 1;
      if (this.unparsedPackets === 1) {
        this.report("unparsed_binary", {
          packet_bytes: packetBytes,
          detail: binaryPrefixSummary(data),
        });
      }
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
      this.setPreviewPlaying(true);
      this.report("first_frame", {
        codec: codecName(frame.codec),
        width: frame.width,
        height: frame.height,
        detail: streamTypeName(frame.streamType),
        packet_bytes: packetBytes,
        payload_bytes: frame.payload.byteLength,
        frame_type: frame.frameType,
        header_offset: frame.headerOffset,
        version: frame.version,
        first_frame_elapsed_ms: this.elapsedSince(this.candidateStartedAt),
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
      this.setStreamState(
        `接收 ${codecName(frame.codec)} ${frame.width || "-"}x${frame.height || "-"}`
      );
    } else if (!this.decodedFrames) {
      this.setStreamState(`解码中 ${codecName(frame.codec)}`);
    }
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
              this.setStreamState(`播放中 ${codecName(frame.codec)}`);
            }
            videoFrame.close();
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
    const nextCandidate = this.candidates[nextIndex];
    this.report("candidate_failed", {
      reason,
      next_channel: nextCandidate?.channel || "",
      payload_bytes: this.lastFrame?.payload?.byteLength || "",
      frame_type: this.lastFrame?.frameType || "",
      codec: this.lastFrame ? codecName(this.lastFrame.codec) : "",
      width: this.lastFrame?.width || "",
      height: this.lastFrame?.height || "",
    });
    if (nextIndex >= this.candidates.length) {
      this.closeDecoder();
      this.closeActiveSocket();
      this.setPreviewPlaying(Boolean(this.lastFrame));
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
    this.setPreviewPlaying(false);
    this.startCandidate(nextIndex);
    return true;
  }

  report(event, extra = {}) {
    reportPreviewEvent({
      output: this.outputIndex,
      event,
      control_ws_url: this.stream.control_ws_url || "",
      ws_url: this.stream.ws_url,
      connect_url: this.connectUrl || this.stream.ws_url,
      ws_protocol: this.stream.ws_protocol || "",
      channel: this.activeCandidate?.channel || this.stream.channel || "",
      candidate_index: this.candidateIndex + 1,
      candidate_count: this.candidates.length,
      elapsed_ms: this.elapsedSince(this.candidateStartedAt),
      ready_state: this.ws ? this.ws.readyState : "",
      bytes: this.bytes,
      frames: this.frames,
      ...extra,
    });
  }

  elapsedSince(startedAt) {
    return startedAt ? Math.max(0, Math.round(performance.now() - startedAt)) : 0;
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
    if (node && text !== this.currentStreamState) {
      this.currentStreamState = text;
      node.textContent = text;
    }
  }

  setPreviewPlaying(playing) {
    const screen = document.querySelector(`.screen[data-screen="${this.outputIndex}"]`);
    if (screen) {
      screen.classList.toggle("preview-playing", Boolean(playing));
    }
  }
}

function parseStreamFrame(buffer, channel = "") {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength <= 4) {
    return null;
  }

  return parseStructuredStreamFrame(buffer, channel) || parseAnnexBStreamFrame(buffer, channel);
}

function parseStructuredStreamFrame(buffer, channel = "") {
  if (buffer.byteLength <= FRAME_HEADER_LENGTH) {
    return null;
  }

  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  const headerOffset = streamFrameHeaderOffset(bytes, view, channel);
  if (headerOffset < 0 || buffer.byteLength <= headerOffset + FRAME_HEADER_LENGTH) {
    return null;
  }

  const version = String.fromCharCode(
    view.getUint8(headerOffset),
    view.getUint8(headerOffset + 1)
  );
  const streamType = view.getUint8(headerOffset + 2);
  const width = readUint16(view, headerOffset + 7);
  const height = readUint16(view, headerOffset + 9);
  const codec = view.getUint8(headerOffset + 11);
  const frameType = view.getUint8(headerOffset + 12);

  return {
    version,
    streamType,
    sequence: readUint32(view, headerOffset + 3),
    width,
    height,
    codec,
    frameType,
    timestamp: readUint32(view, headerOffset + 13),
    headerOffset,
    payload: new Uint8Array(buffer, headerOffset + FRAME_HEADER_LENGTH),
  };
}

function parseAnnexBStreamFrame(buffer, channel = "") {
  const bytes = new Uint8Array(buffer);
  const prefix = asciiBytes(channel);
  const scanStart = prefix.length && startsWithBytes(bytes, prefix) ? prefix.length : 0;
  const startCode = findAnnexBStartCode(bytes, scanStart, Math.min(bytes.length - 4, scanStart + 128));
  if (!startCode) {
    return null;
  }

  const nalOffset = startCode.offset + startCode.length;
  if (nalOffset >= bytes.length) {
    return null;
  }

  const codec = annexBCodec(bytes[nalOffset]);
  if (!codec) {
    return null;
  }

  return {
    version: versionFromChannel(channel) || "raw",
    streamType: 1,
    sequence: 0,
    width: 1920,
    height: 1080,
    codec,
    frameType: annexBFrameType(bytes, startCode.offset, codec),
    timestamp: 0,
    headerOffset: startCode.offset,
    payload: new Uint8Array(buffer, startCode.offset),
  };
}

function streamFrameHeaderOffset(bytes, view, channel) {
  if (isStructuredStreamFrameHeader(bytes, view, 0)) {
    return 0;
  }

  const prefix = asciiBytes(channel);
  if (prefix.length && startsWithBytes(bytes, prefix)) {
    const offset = prefix.length;
    if (isStructuredStreamFrameHeader(bytes, view, offset)) {
      return offset;
    }

    const scanEnd = Math.min(bytes.length - FRAME_HEADER_LENGTH, offset + 128);
    for (let scanOffset = offset + 1; scanOffset <= scanEnd; scanOffset += 1) {
      if (isStructuredStreamFrameHeader(bytes, view, scanOffset)) {
        return scanOffset;
      }
    }
  }

  return -1;
}

function isStructuredStreamFrameHeader(bytes, view, offset) {
  if (
    offset < 0
    || offset + FRAME_HEADER_LENGTH >= bytes.length
    || !hasStreamFrameVersion(bytes, offset)
  ) {
    return false;
  }

  const version = String.fromCharCode(bytes[offset], bytes[offset + 1]);
  return isValidStreamFrameHeader(
    version,
    view.getUint8(offset + 2),
    readUint16(view, offset + 7),
    readUint16(view, offset + 9),
    view.getUint8(offset + 11),
    view.getUint8(offset + 12),
  );
}

function hasStreamFrameVersion(bytes, offset) {
  return (
    offset + 1 < bytes.length
    && bytes[offset] === 118
    && (bytes[offset + 1] === 49 || bytes[offset + 1] === 50 || bytes[offset + 1] === 51)
  );
}

function isValidStreamFrameHeader(version, streamType, width, height, codec, frameType) {
  return (
    ["v1", "v2", "v3"].includes(version)
    && [1, 2].includes(streamType)
    && width > 0
    && width <= 10000
    && height > 0
    && height <= 10000
    && [2, 3].includes(codec)
    && frameType >= 1
    && frameType <= 4
  );
}

function findAnnexBStartCode(bytes, start, end) {
  for (let offset = Math.max(0, start); offset <= end; offset += 1) {
    if (
      offset + 2 < bytes.length
      && bytes[offset] === 0
      && bytes[offset + 1] === 0
      && bytes[offset + 2] === 1
    ) {
      return {offset, length: 3};
    }
    if (
      offset + 3 < bytes.length
      && bytes[offset] === 0
      && bytes[offset + 1] === 0
      && bytes[offset + 2] === 0
      && bytes[offset + 3] === 1
    ) {
      return {offset, length: 4};
    }
  }
  return null;
}

function annexBCodec(nalHeader) {
  const h264NalType = nalHeader & 0x1f;
  if ([1, 5, 6, 7, 8, 9].includes(h264NalType)) {
    return 2;
  }

  const h265NalType = (nalHeader >> 1) & 0x3f;
  if (h265NalType <= 40) {
    return 3;
  }
  return 0;
}

function annexBFrameType(bytes, startOffset, codec) {
  const nalTypes = annexBNalTypes(bytes, startOffset, 4096, codec);
  if (codec === 2 && nalTypes.some((type) => [5, 7, 8].includes(type))) {
    return 1;
  }
  if (codec === 3 && nalTypes.some((type) => [19, 20, 32, 33, 34].includes(type))) {
    return 1;
  }
  return 2;
}

function annexBNalTypes(bytes, startOffset, maxScanBytes, codec) {
  const types = [];
  const end = Math.min(bytes.length - 4, startOffset + maxScanBytes);
  let offset = startOffset;
  while (offset <= end) {
    const startCode = findAnnexBStartCode(bytes, offset, end);
    if (!startCode) {
      break;
    }
    const nalOffset = startCode.offset + startCode.length;
    if (nalOffset >= bytes.length) {
      break;
    }
    types.push(codec === 2 ? bytes[nalOffset] & 0x1f : (bytes[nalOffset] >> 1) & 0x3f);
    offset = nalOffset + 1;
  }
  return types;
}

function versionFromChannel(channel) {
  const match = String(channel || "").match(/\/(v[1-3])$/);
  return match ? match[1] : "";
}

function asciiBytes(value) {
  const text = String(value || "");
  const bytes = new Uint8Array(text.length);
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    if (code > 127) {
      return new Uint8Array();
    }
    bytes[index] = code;
  }
  return bytes;
}

function startsWithBytes(bytes, prefix) {
  if (bytes.length < prefix.length) {
    return false;
  }
  for (let index = 0; index < prefix.length; index += 1) {
    if (bytes[index] !== prefix[index]) {
      return false;
    }
  }
  return true;
}

function binaryPrefixSummary(buffer) {
  if (!(buffer instanceof ArrayBuffer)) {
    return "二进制消息不符合当前帧头格式";
  }
  const bytes = new Uint8Array(buffer, 0, Math.min(48, buffer.byteLength));
  const allBytes = new Uint8Array(buffer);
  const startCode = findAnnexBStartCode(allBytes, 0, Math.min(allBytes.length - 4, 160));
  const hex = Array.from(bytes)
    .map((value) => value.toString(16).padStart(2, "0"))
    .join(" ");
  const ascii = Array.from(bytes)
    .map((value) => (value >= 32 && value <= 126 ? String.fromCharCode(value) : "."))
    .join("");
  const annexb = startCode
    ? ` annexb_offset=${startCode.offset} nal=0x${allBytes[startCode.offset + startCode.length].toString(16)}`
    : "";
  return `二进制消息不符合当前帧头格式${annexb} prefix_ascii=${ascii} prefix_hex=${hex}`;
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
