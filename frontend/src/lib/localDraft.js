const PREFIX = "case-library:crash-draft:";

function key(userId, caseId) {
  return `${PREFIX}${userId}:${caseId}`;
}

export function storeLocalDraft(userId, caseId, baseRevision, snapshot) {
  try {
    const value = { userId, caseId, baseRevision, snapshot };
    localStorage.setItem(key(userId, caseId), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function readLocalDraft(userId, caseId) {
  try {
    return JSON.parse(localStorage.getItem(key(userId, caseId))) || null;
  } catch {
    return null;
  }
}

export function clearLocalDraft(userId, caseId) {
  try {
    localStorage.removeItem(key(userId, caseId));
  } catch {
    return;
  }
}

export function sameDraft(draft, value) {
  if (!draft?.snapshot) return false;
  return draft.snapshot.title === value.title
    && JSON.stringify(draft.snapshot.document) === JSON.stringify(value.document);
}
