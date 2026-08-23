import {
  clearLocalDraft, readLocalDraft, sameDraft, storeLocalDraft,
} from "../lib/localDraft.js";

function identity(context) {
  return [context.options.userId, context.options.caseId];
}

function clear(context) {
  clearTimeout(context.timer);
  context.dirty = false;
  clearLocalDraft(...identity(context));
}

function flush(context) {
  if (!context.dirty) return;
  storeLocalDraft(
    ...identity(context),
    context.options.getRevision(),
    context.options.getSnapshot(),
  );
}

function queue(context) {
  context.dirty = true;
  clearTimeout(context.timer);
  context.timer = setTimeout(() => flush(context), context.options.delayMs ?? 300);
}

function load(context, serverCase) {
  const draft = readLocalDraft(...identity(context));
  if (!draft) return false;
  if (draft.baseRevision !== serverCase.revision || sameDraft(draft, serverCase)) {
    clear(context);
    return false;
  }
  context.options.onRecover(draft.snapshot);
  return true;
}

function saved(context, snapshot) {
  if (sameDraft({ snapshot }, context.options.getSnapshot())) {
    clear(context);
    return;
  }
  context.dirty = true;
  flush(context);
}

export function createCrashDraft(options) {
  const context = { options, timer: null, dirty: false };
  return {
    queue: () => queue(context),
    load: (serverCase) => load(context, serverCase),
    saved: (snapshot) => saved(context, snapshot),
    flush: () => flush(context),
    destroy: () => clearTimeout(context.timer),
  };
}
