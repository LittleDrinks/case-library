import { diffChars } from "diff";

function jsonPayload(response) {
  const trimmed = response.trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return JSON.parse(fenced ? fenced[1] : trimmed);
}

export function parseCandidateResponse(response) {
  let payload;
  try { payload = jsonPayload(response); }
  catch { throw new Error("候选格式无效，请重新生成"); }
  const text = typeof payload?.text === "string" ? payload.text.trim() : "";
  const reason = typeof payload?.reason === "string" ? payload.reason.trim() : "";
  if (!text || !reason) throw new Error("候选格式无效，请重新生成");
  return { text, reason };
}

function diffKind(part) {
  if (part.added) return "added";
  return part.removed ? "removed" : "equal";
}

export function candidateDiff(source, candidate) {
  return diffChars(source || "", candidate || "")
    .map((part) => ({ value: part.value, kind: diffKind(part) }));
}

export function candidateSource(candidate, mode) {
  if (mode === "replace-selection") return candidate.context.quote;
  if (mode === "replace-section") return candidate.context.sectionText;
  return "";
}

export function candidatePrompt(instruction, target, context) {
  const source = target === "selection" ? context.quote : context.sectionText;
  return [
    "writing_candidate",
    "你是高校思政教学案例的写作助手。只提出一个候选，不直接修改正文。",
    "仅输出 JSON 对象，不要 Markdown：{\"text\":\"候选正文\",\"reason\":\"修改理由\"}",
    `目标：${target === "selection" ? "所选文字" : `小节「${context.section}」`}`,
    `教师要求：${instruction}`,
    `原文：${source}`,
  ].join("\n\n");
}
