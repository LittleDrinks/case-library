// ProseMirror positions survive inline formatting; ambiguous quotes are never guessed.
function indexedText(doc) {
  let text = "";
  const positions = [];
  doc.descendants((node, pos) => {
    if (node.isTextblock && text) { text += " "; positions.push(pos); }
    if (!node.isText) return;
    text += node.text;
    for (let i = 0; i < node.text.length; i++) positions.push(pos + i);
  });
  return { text, positions };
}
export function validRange(doc, quote, range) {
  if (!range || range.from > range.to || range.from < 0 || range.to > doc.content.size) return false;
  return doc.textBetween(range.from, range.to, " ") === quote;
}
export function findTextRange(doc, quote, range) {
  if (!quote) return null;
  if (range) return validRange(doc, quote, range) ? range : null;
  const { text, positions } = indexedText(doc);
  const index = text.indexOf(quote);
  if (index < 0 || text.indexOf(quote, index + 1) >= 0) return null;
  return { from: positions[index], to: positions[index + quote.length - 1] + 1 };
}
export function mapAnchor(transaction, anchor, quote) {
  const before = findTextRange(transaction.before, quote, anchor.range);
  if (!before || anchor.anchorMissing) return;
  const from = transaction.mapping.map(before.from, 1);
  const to = transaction.mapping.map(before.to, -1);
  anchor.range = { from, to };
  anchor.anchorMissing = !validRange(transaction.doc, quote, anchor.range);
  if (anchor.anchorMissing && anchor.kind === "revision") anchor.status = "stale";
}

export function mapRevision(transaction, revision) {
  const previous = revision.range || findTextRange(transaction.before, revision.original);
  if (!previous) return;
  const inner = { from: transaction.mapping.map(previous.from, 1), to: transaction.mapping.map(previous.to, -1) };
  const outer = { from: transaction.mapping.map(previous.from, -1), to: transaction.mapping.map(previous.to, 1) };
  for (const range of [inner, outer]) {
    const original = validRange(transaction.doc, revision.original, range);
    const replaced = validRange(transaction.doc, revision.replacement, range);
    if (!original && !replaced) continue;
    revision.range = range; revision.anchorMissing = false;
    if (revision.status !== "rejected") revision.status = original ? "pending" : "accepted";
    return;
  }
  revision.range = outer; revision.anchorMissing = true; revision.status = "stale";
}
