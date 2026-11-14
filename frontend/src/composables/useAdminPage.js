import { ref, watch } from "vue";

export function useAdminPage(fetchPage) {
  const items = ref([]), total = ref(0), page = ref(1), pageSize = ref(20);
  const query = ref(""), status = ref("all"), loading = ref(false), error = ref("");
  let requestId = 0;
  async function reload() {
    const id = ++requestId;
    loading.value = true;
    error.value = "";
    try {
      const result = await fetchPage({ page: page.value, pageSize: pageSize.value, q: query.value, status: status.value });
      if (id !== requestId) return;
      const last = Math.max(1, Math.ceil(result.total / pageSize.value));
      if (page.value > last) { page.value = last; return; }
      items.value = result.items;
      total.value = result.total;
    } catch (reason) {
      if (id === requestId) error.value = reason.message || "列表加载失败";
    } finally {
      if (id === requestId) loading.value = false;
    }
  }
  function search(value) { page.value = 1; query.value = value; }
  function resize(value) { page.value = 1; pageSize.value = value; }
  function filter(value) { page.value = 1; status.value = value; }
  watch([page, pageSize, query, status], reload, { immediate: true });
  return { items, total, page, pageSize, query, status, loading, error, reload, search, resize, filter };
}
