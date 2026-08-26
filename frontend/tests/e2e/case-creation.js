import { expect } from "@playwright/test";

const GENERAL_FIGURE_SELECTION = {
  stageId: "ug",
  typeId: "ct-figure",
  templateId: "tpl-general-v1",
};

export async function createGeneralFigureCase(request, csrfToken) {
  const response = await request.post("/api/cases", {
    headers: { "X-CSRF-Token": csrfToken },
    data: GENERAL_FIGURE_SELECTION,
  });
  expect(response.ok()).toBe(true);
  return response.json();
}

export async function saveCaseChanges(request, csrfToken, current, changes) {
  const response = await request.patch(`/api/cases/${current.id}`, {
    headers: { "X-CSRF-Token": csrfToken },
    data: { ...changes, revision: current.revision },
  });
  expect(response.ok()).toBe(true);
  return response.json();
}
