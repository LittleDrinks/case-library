const STORAGE_KEY = "case-library:material-return";

function storage() {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

function normalizedQuery(query) {
  return Object.fromEntries(Object.keys(query).sort().map((key) => {
    const value = query[key];
    return [key, Array.isArray(value) ? [...value].sort() : value];
  }));
}

function sameQuery(left, right) {
  return JSON.stringify(normalizedQuery(left)) === JSON.stringify(normalizedQuery(right));
}

export function rememberMaterialReturn(query, state) {
  try { storage()?.setItem(STORAGE_KEY, JSON.stringify({ query, ...state })); }
  catch { /* session storage can be unavailable in privacy modes */ }
}

export function restoreMaterialReturn(query) {
  const target = storage();
  if (!target) return null;
  try {
    const record = JSON.parse(target.getItem(STORAGE_KEY) || "null");
    target.removeItem(STORAGE_KEY);
    return record && sameQuery(record.query || {}, query) ? record : null;
  } catch {
    target.removeItem(STORAGE_KEY);
    return null;
  }
}
