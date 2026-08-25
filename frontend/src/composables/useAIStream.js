import { onBeforeUnmount, ref } from "vue";
import { api } from "../api.js";
import { session } from "../session.js";

class AIStreamController {
  state = ref("idle");
  text = ref("");
  error = ref("");
  controller = undefined;
  generation = 0;

  stop() {
    this.controller?.abort();
    this.controller = undefined;
  }

  clear(next = "idle") {
    this.stop();
    this.generation += 1;
    this.state.value = next;
    this.text.value = "";
    this.error.value = "";
  }

  handlers(current) {
    return {
      onToken: (token) => { if (current === this.generation) this.text.value += token; },
      onDone: () => { if (current === this.generation) this.state.value = "complete"; },
      onError: (message) => { if (current === this.generation) this.fail(message); },
    };
  }

  fail(message) {
    this.state.value = "error";
    this.error.value = message || "AI 服务暂不可用";
  }

  async configured(current) {
    try {
      const settings = await api.aiSettings();
      if (current !== this.generation) return false;
      if (!settings.configured) this.clear("unconfigured");
      return settings.configured;
    } catch (reason) {
      if (current === this.generation) this.fail(reason.message);
      return false;
    }
  }

  async run(messages) {
    this.clear(session.user ? "checking" : "login");
    const current = this.generation;
    if (!session.user || !await this.configured(current)) return;
    if (current !== this.generation) return;
    this.controller = new AbortController();
    this.state.value = "streaming";
    await this.stream(messages, this.controller.signal, current);
  }

  async stream(messages, signal, current) {
    try {
      await api.streamAI(messages, session.csrfToken, this.handlers(current), signal);
    } catch (reason) {
      if (reason.name !== "AbortError" && current === this.generation) this.fail(reason.message);
    }
  }
}

export function useAIStream() {
  const stream = new AIStreamController();
  onBeforeUnmount(() => stream.clear());
  return {
    state: stream.state, text: stream.text, error: stream.error,
    run: stream.run.bind(stream), clear: stream.clear.bind(stream),
    stop: stream.stop.bind(stream),
  };
}
