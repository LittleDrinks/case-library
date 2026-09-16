// 浏览器侧 AI 客户端：SSE 流式读取 /prototype-ai/chat，AbortController 停止。
// 返回 { text, reasoning, aborted }；错误抛出并带 message。

function consumeLine(line, state, onDelta, onReasoning) {
  if (!line.startsWith("data:")) return;
  const payload = line.slice(5).trim();
  if (!payload || payload === "[DONE]") return;
  try {
    const delta = JSON.parse(payload).choices?.[0]?.delta || {};
    if (delta.reasoning_content) { state.reasoning += delta.reasoning_content; onReasoning?.(state.reasoning); }
    if (delta.content) { state.text += delta.content; onDelta?.(state.text); }
  } catch { /* 忽略半行/注释帧 */ }
}

async function readStream(response, onDelta, onReasoning) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const state = { text: "", reasoning: "" };
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    lines.forEach((line) => consumeLine(line, state, onDelta, onReasoning));
  }
  if (buffer) consumeLine(buffer, state, onDelta, onReasoning);
  return state;
}

export async function streamChat({ messages, model, thinking, signal, onDelta, onReasoning }) {
  const response = await fetch("/prototype-ai/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages, model, thinking }),
    signal,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { message = (await response.json()).message || message; } catch { /* 保留状态码 */ }
    throw new Error(message);
  }
  return readStream(response, onDelta, onReasoning);
}
