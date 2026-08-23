import { ref } from "vue";

const CONFLICT = 409;

function clearTimer(context, name) {
  clearTimeout(context.timers[name]);
  context.timers[name] = null;
}

function fireTimer(context, name) {
  context.timers[name] = null;
  void context.flush();
}

function scheduleIdle(context) {
  clearTimer(context, "idle");
  context.timers.idle = setTimeout(
    () => fireTimer(context, "idle"),
    context.options.idleMs ?? 1000,
  );
}

function scheduleMax(context) {
  if (context.timers.max) return;
  context.timers.max = setTimeout(
    () => fireTimer(context, "max"),
    context.options.maxMs ?? 15000,
  );
}

function markDirty(context) {
  context.dirty = true;
  context.state.value = "dirty";
  clearTimer(context, "retry");
  scheduleIdle(context);
  scheduleMax(context);
}

function beginSave(context) {
  context.dirty = false;
  context.saving = true;
  context.state.value = "saving";
  clearTimer(context, "idle");
  clearTimer(context, "max");
  clearTimer(context, "retry");
}

function finishSave(context, result) {
  context.revision.value = result.revision;
  context.saving = false;
  context.state.value = context.dirty ? "dirty" : "saved";
  if (context.dirty) {
    scheduleIdle(context);
    scheduleMax(context);
  }
}

function failSave(context, error) {
  context.dirty = true;
  context.saving = false;
  context.state.value = error.status === CONFLICT ? "conflict" : "error";
  if (error.status === CONFLICT) context.options.onConflict?.(error);
  else {
    context.options.onError?.(error);
    if (retryable(error)) scheduleRetry(context);
  }
}

function retryable(error) {
  return !error.status || error.status >= 500 || [408, 429].includes(error.status);
}

function scheduleRetry(context) {
  clearTimer(context, "retry");
  context.timers.retry = setTimeout(
    () => fireTimer(context, "retry"),
    context.options.retryMs ?? 2000,
  );
}

async function runSave(context) {
  try {
    finishSave(context, await context.options.save(context.options.getSnapshot()));
  } catch (error) {
    failSave(context, error);
  } finally {
    context.inflight = null;
  }
}

async function flush(context) {
  if (context.saving) return context.inflight;
  if (!context.dirty) return;
  beginSave(context);
  context.inflight = runSave(context);
  return context.inflight;
}

function destroy(context) {
  clearTimer(context, "idle");
  clearTimer(context, "max");
  clearTimer(context, "retry");
}

function reconcile(context, revision) {
  clearTimer(context, "idle");
  clearTimer(context, "max");
  clearTimer(context, "retry");
  context.dirty = false;
  context.revision.value = revision;
  context.state.value = "saved";
}

function createAutosaveContext(options) {
  return {
    options,
    state: ref("saved"),
    revision: ref(null),
    timers: { idle: null, max: null, retry: null },
    dirty: false,
    saving: false,
    inflight: null,
  };
}

function autosaveControls(context) {
  context.flush = () => flush(context);
  return {
    state: context.state,
    revision: context.revision,
    markDirty: () => markDirty(context),
    flush: context.flush,
    reconcile: (revision) => reconcile(context, revision),
    destroy: () => destroy(context),
  };
}

export function createAutosave(options) {
  return autosaveControls(createAutosaveContext(options));
}
