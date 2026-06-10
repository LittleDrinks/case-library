import { get, postJSON } from "./client.js";

export async function listPrompts(category = "workflow") {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  const data = await get(`/api/prompts?${params.toString()}`);
  return data?.data || [];
}

export async function runPrompt(promptId, variables, model = null) {
  const payload = {
    prompt_id: promptId,
    variables,
  };
  if (model) payload.model = model;
  return postJSON("/api/ai/chat", payload);
}

export async function runParagraphReview(caseId, model = null) {
  const payload = {};
  if (model) payload.model = model;
  return postJSON(`/api/cases/${caseId}/ai-review`, payload);
}
