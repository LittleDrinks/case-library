import { ApiError } from "../api.js";

export async function searchWithSyncRetry(request, isLive = () => true) {
  const deadline = Date.now() + 30_000;
  while (isLive()) {
    try {
      return await request();
    } catch (caught) {
      if (!(caught instanceof ApiError) || caught.status !== 503 || Date.now() >= deadline) throw caught;
      await new Promise((resolve) => setTimeout(resolve, 1000));
      if (!isLive() || Date.now() >= deadline) throw caught;
    }
  }
}
