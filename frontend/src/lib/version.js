export function versionLabel(version) {
  const prefix = version.kind === "ai" ? `AI版本 v${version.number}` : `v${version.number}`;
  return `${prefix} · ${version.title}`;
}

export function versionPaperLabel(version) {
  return version.kind === "ai" ? "AI生成版本" : "提交版本";
}
