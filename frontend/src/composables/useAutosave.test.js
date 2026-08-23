import { afterEach, expect, it, vi } from "vitest";
import { createAutosave } from "./useAutosave.js";

afterEach(() => vi.useRealTimers());

it("案例工作版本停止输入一秒后保存当前正文和修订号", async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockResolvedValue({ revision: 8 });
    const getSnapshot = () => ({ title: "新标题", revision: 7 });
    const autosave = createAutosave({ save, getSnapshot });

    autosave.markDirty();
    await vi.advanceTimersByTimeAsync(999);
    expect(save).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(save).toHaveBeenCalledWith({ title: "新标题", revision: 7 });
    expect(autosave.revision.value).toBe(8);
    autosave.destroy();
});

it("案例工作版本连续输入也会在十五秒内保存", async () => {
    vi.useFakeTimers();
    const save = vi.fn().mockResolvedValue({ revision: 2 });
    const autosave = createAutosave({ save, getSnapshot: () => ({ revision: 1 }) });

    autosave.markDirty();
    for (let index = 0; index < 29; index += 1) {
      await vi.advanceTimersByTimeAsync(500);
      autosave.markDirty();
    }
    await vi.advanceTimersByTimeAsync(500);

    expect(save).toHaveBeenCalledOnce();
    autosave.destroy();
});

it("案例工作版本旧修订保存失败时明确进入冲突状态", async () => {
    vi.useFakeTimers();
    const conflict = Object.assign(new Error("案例已更新"), { status: 409, currentRevision: 9 });
    const onConflict = vi.fn();
    const autosave = createAutosave({
      save: vi.fn().mockRejectedValue(conflict),
      getSnapshot: () => ({ revision: 8 }),
      onConflict,
    });

    autosave.markDirty();
    await vi.advanceTimersByTimeAsync(1000);

    expect(autosave.state.value).toBe("conflict");
    expect(onConflict).toHaveBeenCalledWith(conflict);
    autosave.destroy();
});

it("案例工作版本在服务暂时不可用时两秒后重试", async () => {
    vi.useFakeTimers();
    const unavailable = Object.assign(new Error("选主中"), { status: 503 });
    const save = vi.fn().mockRejectedValueOnce(unavailable).mockResolvedValue({ revision: 4 });
    const autosave = createAutosave({ save, getSnapshot: () => ({ revision: 3 }) });

    autosave.markDirty();
    await vi.advanceTimersByTimeAsync(1000);
    expect(autosave.state.value).toBe("error");

    await vi.advanceTimersByTimeAsync(2000);
    expect(save).toHaveBeenCalledTimes(2);
    expect(autosave.state.value).toBe("saved");
    autosave.destroy();
});

it("保存响应丢失后可用服务端修订恢复为已保存状态", async () => {
  const unavailable = Object.assign(new Error("响应中断"), { status: 503 });
  const autosave = createAutosave({
    save: vi.fn().mockRejectedValue(unavailable),
    getSnapshot: () => ({ revision: 3 }),
  });
  autosave.markDirty();
  await autosave.flush();

  autosave.reconcile(4);

  expect(autosave.state.value).toBe("saved");
  expect(autosave.revision.value).toBe(4);
  autosave.destroy();
});
