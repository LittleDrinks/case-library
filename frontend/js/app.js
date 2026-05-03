// 强国有我大思政课案例库 - 前端JavaScript

const API_BASE = "http://localhost:8001/api";

// 用户认证相关全局变量
let currentUser = null;
let authToken = null;

// 全局错误处理
window.addEventListener('error', function(e) {
  console.error('Global error caught:', e.error);
  alert('发生错误: ' + e.error.message);
});

window.addEventListener('unhandledrejection', function(e) {
  console.error('Unhandled promise rejection:', e.reason);
  alert('发生异步错误: ' + (e.reason?.message || e.reason));
});

// 类型名称映射
const TYPE_NAMES = {
  TYPE_A: "思政课教学案例",
  TYPE_B: "课程思政共享资源案例",
  TYPE_C: "实践育人案例",
};

const STATUS_NAMES = {
  draft: "草稿",
  pending_review: "待审核",
  approved: "已通过",
  approved_pending_deploy: "已通过",
  needs_revision: "需修改",
  deleted: "已删除",
};

const STATUS_CLASSES = {
  draft: "status-draft",
  pending_review: "status-pending",
  approved: "status-approved",
  approved_pending_deploy: "status-approved",
  needs_revision: "status-revision",
  deleted: "status-draft",
};

// ============ 工具函数 ============

async function apiRequest(url, options = {}) {
  try {
    console.log("apiRequest called:", url, options);
    
    const headers = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (authToken) {
      headers["Authorization"] = `Bearer ${authToken}`;
    }

    const fullUrl = `${API_BASE}${url}`;
    console.log("Fetching:", fullUrl);
    
    const response = await fetch(fullUrl, {
      headers: headers,
      ...options,
    });
    
    console.log("Response status:", response.status);
    
    // 检查响应状态
    if (!response.ok) {
      const errorText = await response.text();
      console.error("HTTP Error:", response.status, errorText);
      return { success: false, error: `服务器错误: ${response.status}`, status: response.status };
    }
    
    // 尝试解析JSON
    let data;
    try {
      data = await response.json();
    } catch (jsonError) {
      console.error("JSON parse error:", jsonError);
      const text = await response.text();
      return { success: false, error: "响应不是有效的JSON: " + text.substring(0, 100) };
    }
    
    console.log("API response data:", data);
    return data;
  } catch (error) {
    console.error("API请求失败:", error);
    return { success: false, error: error.message };
  }
}

async function formRequest(url, formData, method = "POST") {
  try {
    const headers = {};
    if (authToken) {
      headers["Authorization"] = `Bearer ${authToken}`;
    }

    console.log("formRequest - URL:", `${API_BASE}${url}`);
    console.log("formRequest - Method:", method);
    console.log("formRequest - Headers:", headers);

    const response = await fetch(`${API_BASE}${url}`, {
      method: method,
      headers: headers,
      body: formData,
    });

    console.log("formRequest - Response status:", response.status);
    console.log("formRequest - Response ok:", response.ok);

    // 检查响应状态
    if (!response.ok) {
      const errorText = await response.text();
      console.error("HTTP Error:", response.status, errorText);
      return { success: false, error: `服务器错误: ${response.status}` };
    }

    const data = await response.json();
    console.log("formRequest - Response data:", data);
    return data;
  } catch (error) {
    console.error("表单请求失败:", error);
    return { success: false, error: error.message };
  }
}

function formatDate(dateStr) {
  const date = new Date(dateStr);
  return date.toLocaleDateString("zh-CN");
}

// ============ 页面导航 ============

// 存储当前页面状态
let lastNavigatedPage = "home";

function navigateTo(page) {
  try {
    console.log("navigateTo called with page:", page, "last:", lastNavigatedPage);
    lastNavigatedPage = page;
    
    // 隐藏所有页面
    document
      .querySelectorAll(".page")
      .forEach((p) => p.classList.remove("active"));
    document
      .querySelectorAll(".nav-link")
      .forEach((l) => l.classList.remove("active"));

    // 显示目标页面
    const pageElement = document.getElementById(`page-${page}`);
    if (!pageElement) {
      console.error("Page element not found:", `page-${page}`);
      // 如果目标页面不存在，导航到首页
      navigateToHome();
      return;
    }
    pageElement.classList.add("active");

    // 权限检查：审核管理页面只有管理员可以访问
    if (page === "review") {
      if (!currentUser || currentUser.role !== "admin") {
        alert("您没有权限访问审核管理页面");
        navigateToHome();
        return;
      }
    }

    // 权限检查：创建案例页面需要登录
    if (page === "create") {
      // 确保用户已登录
      if (!currentUser) {
        // 尝试从localStorage恢复登录状态
        const savedToken = localStorage.getItem("authToken");
        const savedUser = localStorage.getItem("currentUser");
        
        if (savedToken && savedUser) {
          try {
            authToken = savedToken;
            currentUser = JSON.parse(savedUser);
            updateAuthUI();
            console.log("Session restored:", currentUser);
          } catch (e) {
            console.error("Session restore failed:", e);
          }
        }
      }
      
      // 最终检查
      if (!currentUser) {
        alert("请先登录后再创建案例");
        openLoginModal();
        return;
      }
      
      // 如果是创建案例页面，检查是否刚提交完案例
      const justSubmitted = localStorage.getItem("justSubmittedCase");
      const fromMyCases = localStorage.getItem("fromMyCases");
      
      // 如果用户直接进入创建页面（不是从修改进入），强制清除所有编辑状态
      let isEditing = localStorage.getItem("editingCaseId");
      if (!fromMyCases) {
        console.log("强制清除编辑状态，因为不是从我的案例进入");
        localStorage.removeItem("editingCaseId");
        localStorage.removeItem("resubmitCase");
        localStorage.removeItem("isEditingMode");
        localStorage.removeItem("editingCaseData");
        isEditing = null;
      }
      
      if (!justSubmitted && !isEditing) {
        // 只有在不是刚提交且不是编辑状态时才加载草稿
        loadDraft();
      } else {
        if (justSubmitted) {
          localStorage.removeItem("justSubmittedCase");
          // 强制清空表单，确保下一次创建案例时表单为空
          document.getElementById("case-title").value = "";
          document.getElementById("case-author").value = "";
          document.getElementById("case-department").value = "";
          document.getElementById("case-content").value = "";
          // 下拉框使用selectedIndex重置
          document.getElementById("case-type").selectedIndex = 0;
          document.getElementById("case-theme").selectedIndex = 0;
          if (document.getElementById("auto-process")) {
            document.getElementById("auto-process").checked = true;
          }
          // 重置页面标题和按钮文本
          const pageTitle = document.querySelector("#page-create .page-title");
          if (pageTitle) pageTitle.textContent = "创建新案例";
          const submitBtn = document.querySelector("#page-create .btn-primary");
          if (submitBtn) submitBtn.textContent = "提交案例";
        }
      }
    }

    // 设置导航链接激活状态
    const navLink = document.querySelector(`[data-page="${page}"]`);
    if (navLink) {
      navLink.classList.add("active");
    }

    // 加载页面数据
    if (page === "home") loadHomeData();
    if (page === "cases") loadCases();
    if (page === "review") loadReviewCases();
    if (page === "stats") loadStats();
    if (page === "my-cases") loadMyCases();
    
    console.log("Navigation to", page, "completed");
  } catch (error) {
    console.error("navigateTo error:", error);
    alert("导航发生错误: " + error.message);
    navigateToHome();
  }
}

function navigateToHome() {
  // 直接导航到首页，不经过权限检查
  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  document.querySelectorAll(".nav-link").forEach((l) => l.classList.remove("active"));
  document.getElementById("page-home").classList.add("active");
  const homeNav = document.querySelector('[data-page="home"]');
  if (homeNav) homeNav.classList.add("active");
  loadHomeData();
  lastNavigatedPage = "home";
}

// ============ 首页数据 ============

async function loadHomeData() {
  await Promise.all([loadStatistics()]);
}

async function loadStatistics() {
  const data = await apiRequest("/statistics");
  if (data.success) {
    const stats = data.data;
    const statsGrid = document.getElementById("stats-grid");
    statsGrid.innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${stats.total_cases || 0}</div>
                <div class="stat-label">案例总数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.approved_cases || 0}</div>
                <div class="stat-label">已通过案例</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.total_views || 0}</div>
                <div class="stat-label">总浏览量</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.total_likes || 0}</div>
                <div class="stat-label">总点赞数</div>
            </div>
        `;
  }
}

async function loadTrendingCases() {
  const data = await apiRequest("/trending?limit=6");
  if (data.success) {
    renderCases(data.data, "trending-cases");
  }
}

async function loadLatestCases() {
  const data = await apiRequest("/latest?limit=6");
  if (data.success) {
    renderCases(data.data, "latest-cases");
  }
}

// ============ 案例渲染 ============

function renderCases(cases, containerId) {
  const container = document.getElementById(containerId);
  if (!cases.length) {
    container.innerHTML =
      '<p style="text-align: center; color: var(--text-light); padding: 2rem;">暂无案例</p>';
    return;
  }

  const likedCases = JSON.parse(localStorage.getItem("likedCases") || "[]");

  container.innerHTML = cases
    .map(
      (c) => {
        const isLiked = likedCases.includes(String(c.id));
        return `
        <div class="case-card" data-case-id="${c.id}">
            <div class="case-card-header">
                <div class="case-type">${TYPE_NAMES[c.type] || c.type}</div>
                <div class="case-title">${c.title}</div>
            </div>
            <div class="case-card-body">
                <div class="case-meta">
                    <span>📅 ${formatDate(c.created_at)}</span>
                    ${c.author ? `<span>👤 ${c.author}</span>` : ""}
                </div>
                <div class="case-summary">
                    ${c.content?.substring(0, 150) || ""}...
                </div>
            </div>
            <div class="case-card-footer">
                <div class="case-stats">
                    <span>👁️ ${c.view_count || 0}</span>
                    <span>❤️ ${c.like_count || 0}</span>
                    <button type="button" class="btn btn-primary btn-sm btn-like" data-case-id="${c.id}" onclick="event.stopPropagation(); event.preventDefault(); likeCase(${c.id});" ${isLiked ? 'style="background-color: #e74c3c;"' : ''}>${isLiked ? '❤️ 已点赞' : '❤️ 点赞'}</button>
                </div>
                <div class="case-actions">
                    <button type="button" class="btn btn-secondary btn-sm btn-view-detail" data-case-id="${c.id}">查看详情</button>
                </div>
            </div>
            <div class="case-detail" id="case-detail-${containerId}-${c.id}">
                <div class="detail-content">
                    <div class="detail-row">
                        <strong>作者：</strong>${c.author || '未知'}
                    </div>
                    <div class="detail-row">
                        <strong>部门：</strong>${c.department || '未知'}
                    </div>
                    <div class="detail-row">
                        <strong>类型：</strong>${TYPE_NAMES[c.type] || c.type}
                    </div>
                    <div class="detail-row">
                        <strong>主题：</strong>${c.theme || '未设置'}
                    </div>
                    <div class="detail-row detail-content-full">
                        <strong>内容：</strong>
                        <div>${c.content || '暂无内容'}</div>
                    </div>
                    ${c.keywords && c.keywords.length ? `
                    <div class="detail-row">
                        <strong>关键词：</strong>
                        ${c.keywords.map(k => `<span class="keyword-tag">${k}</span>`).join('')}
                    </div>
                    ` : ''}
                    <div class="detail-actions">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCaseDetail(${c.id}, '${containerId}')">收起详情</button>
                    </div>
                </div>
            </div>
        </div>
      `;
      }
    )
    .join("");
  
  container.querySelectorAll('.btn-view-detail').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      e.preventDefault();
      const caseId = parseInt(this.dataset.caseId);
      if (caseId) {
        console.log('Cases page view detail button clicked for case:', caseId);
        toggleCaseDetail(caseId, containerId);
      }
    });
  });
  
}

// ============ 案例库 ============

async function loadCases() {
  await applyFilters();
}

async function searchCases() {
  const query = document.getElementById("search-input").value;
  if (!query.trim()) {
    loadCases();
    return;
  }

  const data = await apiRequest(`/search?q=${encodeURIComponent(query)}`);
  if (data.success) {
    renderCases(data.data, "cases-list");
  }
}

async function applyFilters() {
  const type = document.getElementById("filter-type")?.value;
  const theme = document.getElementById("filter-theme")?.value;

  let url = "/cases?status=approved";
  if (type) url += `&type=${type}`;
  if (theme) url += `&theme=${theme}`;

  const data = await apiRequest(url);
  if (data.success) {
    renderCases(data.data, "cases-list");
  }
}

// ============ 案例详情 ============

async function openCaseDetail(caseId) {
  try {
    console.log("openCaseDetail called with caseId:", caseId);
    
    const data = await apiRequest(`/cases/${caseId}`);
    console.log("API response:", data);
    
    if (!data || !data.success) {
      console.error("Failed to load case detail:", data?.message);
      alert("加载案例详情失败: " + (data?.message || "未知错误"));
      return;
    }
    
    const c = data.data;
    if (!c) {
      console.error("Case data is null");
      alert("案例数据为空");
      return;
    }
    
    const modalTitle = document.getElementById("modal-title");
    const modalBody = document.getElementById("modal-body");
    const caseModal = document.getElementById("case-modal");
    
    if (!modalTitle || !modalBody || !caseModal) {
      console.error("Modal elements not found");
      alert("模态框元素未找到");
      return;
    }
    
    modalTitle.textContent = c.title;
    modalBody.innerHTML = `
            <div style="margin-bottom: 1rem;">
                <span class="status-badge ${STATUS_CLASSES[c.status] || ''}">${STATUS_NAMES[c.status] || c.status}</span>
                <span style="margin-left: 8px; color: var(--text-light);">${TYPE_NAMES[c.type] || c.type}</span>
            </div>
            <div style="display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;">
                <span>📅 ${formatDate(c.created_at)}</span>
                ${c.author ? `<span>👤 ${c.author}</span>` : ""}
                ${c.department ? `<span>🏛️ ${c.department}</span>` : ""}
                <span>👁️ ${c.view_count || 0}</span>
                <span class="modal-like-count" data-case-id="${c.id}">❤️ ${c.like_count || 0}</span>
            </div>
            <div style="background: var(--bg-color); padding: 1.5rem; border-radius: var(--radius); margin-bottom: 1.5rem;">
                ${c.content || '暂无内容'}
            </div>
            ${
              c.keywords && c.keywords.length
                ? `
                <div style="margin-bottom: 1.5rem;">
                    <strong>关键词：</strong>
                    ${c.keywords.map((k) => `<span style="display: inline-block; background: var(--bg-color); padding: 4px 12px; border-radius: 20px; margin: 4px; font-size: 0.875rem;">${k}</span>`).join("")}
                </div>
            `
                : ""
            }
            <div style="display: flex; gap: 8px;">
                <button type="button" class="btn btn-primary" onclick="likeCase(${c.id})">❤️ 点赞</button>
                <button type="button" class="btn btn-secondary" onclick="closeModal()">关闭</button>
            </div>
        `;
    caseModal.classList.add("active");
    console.log("Modal opened successfully");
  } catch (error) {
    console.error("openCaseDetail error:", error);
    alert("打开案例详情时发生错误: " + error.message);
  }
}

// 防止重复点赞的标志
let likeProcessing = new Set();

async function likeCase(caseId) {
  try {
    // 防止重复点击
    if (likeProcessing.has(caseId)) {
      console.log("likeCase already processing for caseId:", caseId);
      return;
    }
    likeProcessing.add(caseId);
    
    console.log("likeCase called with caseId:", caseId);
    
    const storedLikedCases = localStorage.getItem("likedCases");
    console.log("Stored likedCases:", storedLikedCases);
    
    const likedCases = JSON.parse(storedLikedCases || "[]");
    const isLiked = likedCases.includes(String(caseId));
    
    console.log("isLiked:", isLiked);
    
    if (isLiked) {
      console.log("Attempting to unlike case:", caseId);
      const data = await apiRequest(`/cases/${caseId}/unlike`, { method: "POST" });
      console.log("API response for unlike:", data);
      
      if (data.success) {
        const newLikedCases = likedCases.filter(id => id !== String(caseId));
        localStorage.setItem("likedCases", JSON.stringify(newLikedCases));
        console.log("After unlike - localStorage:", localStorage.getItem("likedCases"));
        updateLikeUI(caseId, false);
      } else {
        console.error("Unlike API failed:", data);
        alert("取消点赞失败: " + (data.error || "未知错误"));
      }
    } else {
      console.log("Attempting to like case:", caseId);
      const data = await apiRequest(`/cases/${caseId}/like`, { method: "POST" });
      console.log("API response for like:", data);
      
      if (data.success) {
        likedCases.push(String(caseId));
        localStorage.setItem("likedCases", JSON.stringify(likedCases));
        console.log("After like - localStorage:", localStorage.getItem("likedCases"));
        updateLikeUI(caseId, true);
      } else {
        console.error("Like API failed:", data);
        alert("点赞失败: " + (data.error || "未知错误"));
      }
    }
  } catch (error) {
    console.error("likeCase error:", error);
    alert("点赞操作发生错误: " + error.message);
  } finally {
    // 移除处理标志
    likeProcessing.delete(caseId);
  }
}

function updateLikeUI(caseId, isLiked) {
  const caseIdStr = String(caseId);
  console.log("updateLikeUI called - caseId:", caseId, "caseIdStr:", caseIdStr, "isLiked:", isLiked);
  
  const cards = document.querySelectorAll(`[data-case-id="${caseIdStr}"]`);
  console.log("Found", cards.length, "cards with data-case-id=" + caseIdStr);
  
  cards.forEach((card, index) => {
    console.log("Processing card", index);
    
    const likeBtn = card.querySelector('button[onclick*="likeCase"]');
    console.log("Found likeBtn:", !!likeBtn);
    
    const likeCount = card.querySelector('.case-stats span:last-child');
    console.log("Found likeCount:", !!likeCount);
    
    if (likeBtn) {
      if (isLiked) {
        likeBtn.innerHTML = "❤️ 已点赞";
        likeBtn.style.backgroundColor = "#e74c3c";
      } else {
        likeBtn.innerHTML = "❤️ 点赞";
        likeBtn.style.backgroundColor = "";
      }
      console.log("Button updated to:", isLiked ? "已点赞" : "点赞");
    }
    
    if (likeCount) {
      const currentCount = parseInt(likeCount.textContent.replace('❤️', '').trim()) || 0;
      console.log("Current like count:", currentCount);
      
      if (isLiked) {
        likeCount.textContent = `❤️ ${currentCount + 1}`;
      } else {
        likeCount.textContent = `❤️ ${Math.max(0, currentCount - 1)}`;
      }
      console.log("New like count:", likeCount.textContent);
    }
  });
  
  const modalLikeCount = document.querySelector(`.modal-like-count[data-case-id="${caseIdStr}"]`);
  if (modalLikeCount) {
    const currentCount = parseInt(modalLikeCount.textContent.replace('❤️', '').trim()) || 0;
    if (isLiked) {
      modalLikeCount.textContent = `❤️ ${currentCount + 1}`;
    } else {
      modalLikeCount.textContent = `❤️ ${Math.max(0, currentCount - 1)}`;
    }
  }
}

function isCaseLiked(caseId) {
  const likedCases = JSON.parse(localStorage.getItem("likedCases") || "[]");
  return likedCases.includes(String(caseId));
}

function closeModal() {
  document.getElementById("case-modal").classList.remove("active");
}

// ============ 创建案例 ============

async function submitCase() {
  try {
    const submitBtn = document.querySelector("#page-create .btn-primary");
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "提交中...";
    }

    const title = document.getElementById("case-title").value;
    const department = document.getElementById("case-department").value;
    const content = document.getElementById("case-content").value;
    const caseType = document.getElementById("case-type").value;
    const caseTheme = document.getElementById("case-theme").value;

    if (!title.trim()) {
      alert("请填写案例标题！");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "提交案例";
      }
      return;
    }
    
    if (!content.trim()) {
      alert("请填写案例内容！");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "提交案例";
      }
      return;
    }
    
    if (!caseType || caseType === "") {
      alert("请选择案例类型！");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "提交案例";
      }
      return;
    }
    
    if (!caseTheme || caseTheme === "") {
      alert("请选择案例主题！");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "提交案例";
      }
      return;
    }

    if (!currentUser) {
      alert("请先登录后再提交案例！");
      openLoginModal();
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "提交案例";
      }
      return;
    }
    
    const formData = new FormData();
    formData.append("title", title);
    formData.append("content", content);
    formData.append("author", currentUser.username);
    formData.append("department", department);
    formData.append("type", caseType);
    formData.append("theme", caseTheme);
    formData.append("auto_process", false);
    formData.append("status", "pending_review");

    const response = await fetch(`${API_BASE}/cases`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${authToken}`
      },
      body: formData
    });
    
    const data = await response.json();
    
    if (data.success) {
      alert("案例创建成功！");
      
      const form = document.getElementById("create-case-form");
      if (form) {
        form.reset();
      }
      
      if (document.getElementById("auto-process")) {
        document.getElementById("auto-process").checked = true;
      }
    } else {
      alert(data.error || "创建失败，请重试");
    }

    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "提交案例";
    }
  } catch (error) {
    console.error("提交失败:", error);
    alert("提交案例时发生错误: " + error.message);
    
    const submitBtn = document.querySelector("#page-create .btn-primary");
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "提交案例";
    }
  }
}

function resetCaseForm() {
  const formFields = [
    "case-title", "case-author", "case-department",
    "case-content", "case-type", "case-theme"
  ];
  
  formFields.forEach(fieldId => {
    const el = document.getElementById(fieldId);
    if (el) {
      if (el.tagName === "SELECT") {
        el.selectedIndex = 0;
      } else {
        el.value = "";
      }
    }
  });

  const autoProcess = document.getElementById("auto-process");
  if (autoProcess) autoProcess.checked = true;

  const form = document.getElementById("create-case-form");
  if (form) form.reset();
}

function createNewCaseMode() {
  localStorage.removeItem("editingCaseId");
  localStorage.removeItem("fromMyCases");
  localStorage.removeItem("resubmitCase");
  localStorage.removeItem("isEditingMode");
  localStorage.removeItem("editingCaseData");
  localStorage.removeItem("justSubmittedCase");

  if (currentUser) {
    const draftKey = `caseDraft_${currentUser.username}`;
    localStorage.removeItem(draftKey);
    sessionStorage.removeItem(draftKey);
  }
  localStorage.removeItem("caseDraft");
  sessionStorage.removeItem("caseDraft");

  const pageTitle = document.querySelector("#page-create .page-title");
  if (pageTitle) pageTitle.textContent = "创建新案例";
  
  const submitBtn = document.querySelector("#page-create .btn-primary");
  if (submitBtn) submitBtn.textContent = "提交案例";

  console.log("已自动进入新建案例模式，表单已重置");
}

function resetForm() {
  // 1. 清空所有表单字段
  const titleField = document.getElementById("case-title");
  const authorField = document.getElementById("case-author");
  const deptField = document.getElementById("case-department");
  const contentField = document.getElementById("case-content");
  const typeField = document.getElementById("case-type");
  const themeField = document.getElementById("case-theme");
  const autoProcessField = document.getElementById("auto-process");
  
  if (titleField) titleField.value = "";
  if (authorField) authorField.value = "";
  if (deptField) deptField.value = "";
  if (contentField) contentField.value = "";
  if (typeField) typeField.selectedIndex = 0;
  if (themeField) themeField.selectedIndex = 0;
  if (autoProcessField) autoProcessField.checked = true;
  
  // 2. 清除所有编辑状态（保留justSubmittedCase和forceReset标志，它们用于阻止草稿加载）
  localStorage.removeItem("editingCaseId");
  localStorage.removeItem("fromMyCases");
  localStorage.removeItem("resubmitCase");
  localStorage.removeItem("isEditingMode");
  localStorage.removeItem("editingCaseData");
  
  // 3. 清除当前登录用户的草稿
  if (currentUser) {
    const draftKey = `caseDraft_${currentUser.username}`;
    localStorage.removeItem(draftKey);
    sessionStorage.removeItem(draftKey);
  }
  
  // 4. 清除所有可能的草稿键
  localStorage.removeItem("caseDraft");
  sessionStorage.removeItem("caseDraft");
  
  // 5. 重置页面标题和按钮文本
  const pageTitle = document.querySelector("#page-create .page-title");
  const submitBtn = document.querySelector("#page-create .btn-primary");
  if (pageTitle) pageTitle.textContent = "创建新案例";
  if (submitBtn) {
    submitBtn.textContent = "提交案例";
    submitBtn.disabled = false;
  }
  
  // 6. 重置页面状态
  // 滚动到页面顶部
  window.scrollTo({ top: 0, behavior: 'smooth' });
  
  // 7. 重置全局编辑状态变量
  if (typeof editingCaseId !== 'undefined') {
    editingCaseId = null;
  }
  
  console.log("✅ 案例提交成功！表单已完全重置，进入新建案例状态");
}

function fullResetCaseForm() {
  const hasContent = document.getElementById("case-title")?.value || document.getElementById("case-content")?.value;
  if (hasContent && !confirm("确定要放弃当前内容，创建新案例吗？")) {
    return;
  }

  const formFields = [
    "case-title", "case-author", "case-department", "case-content", "case-type", "case-theme"
  ];
  formFields.forEach(fieldId => {
    const el = document.getElementById(fieldId);
    if (el) {
      el.value = "";
    }
  });
  
  const autoProcessEl = document.getElementById("auto-process");
  if (autoProcessEl) autoProcessEl.checked = true;

  const resetKeys = [
    "editingCaseId", "fromMyCases", "resubmitCase", "isEditingMode",
    "editingCaseData", "justSubmittedCase", "caseDraft"
  ];
  resetKeys.forEach(key => {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  });

  if (currentUser) {
    const draftKey = `caseDraft_${currentUser.username}`;
    localStorage.removeItem(draftKey);
    sessionStorage.removeItem(draftKey);
  }

  localStorage.setItem("forceReset", "true");

  const pageTitle = document.querySelector("#page-create .page-title");
  if (pageTitle) pageTitle.textContent = "创建新案例";
  const submitBtn = document.querySelector("#page-create .btn-primary");
  if (submitBtn) submitBtn.textContent = "提交案例";

  const form = document.getElementById("create-case-form");
  if (form) form.reset();

  console.log("表单已全量重置，草稿/编辑状态已清除");
}

// 创建新案例（放弃当前编辑，开始全新案例）
function createNewCase() {
  // 确认用户操作
  if (document.getElementById("case-title").value || document.getElementById("case-content").value) {
    if (!confirm("确定要放弃当前内容，创建新案例吗？")) {
      return;
    }
  }
  
  // 1. 设置刚提交标志，阻止草稿加载
  localStorage.setItem("justSubmittedCase", "true");
  
  // 2. 清除所有编辑状态
  localStorage.removeItem("editingCaseId");
  localStorage.removeItem("fromMyCases");
  localStorage.removeItem("resubmitCase");
  localStorage.removeItem("isEditingMode");
  localStorage.removeItem("editingCaseData");
  
  // 3. 清除草稿数据
  if (currentUser) {
    const draftKey = `caseDraft_${currentUser.username}`;
    localStorage.removeItem(draftKey);
    sessionStorage.removeItem(draftKey);
  }
  localStorage.removeItem("caseDraft");
  sessionStorage.removeItem("caseDraft");
  
  // 4. 清空表单字段
  const titleEl = document.getElementById("case-title");
  const authorEl = document.getElementById("case-author");
  const deptEl = document.getElementById("case-department");
  const contentEl = document.getElementById("case-content");
  const typeEl = document.getElementById("case-type");
  const themeEl = document.getElementById("case-theme");
  const autoProcessEl = document.getElementById("auto-process");
  
  if (titleEl) titleEl.value = "";
  if (authorEl) authorEl.value = "";
  if (deptEl) deptEl.value = "";
  if (contentEl) contentEl.value = "";
  if (typeEl) typeEl.value = "";
  if (themeEl) themeEl.value = "";
  if (autoProcessEl) autoProcessEl.checked = true;
  
  // 5. 重置页面标题和按钮文本
  const pageTitle = document.querySelector("#page-create .page-title");
  if (pageTitle) pageTitle.textContent = "创建新案例";
  
  const submitBtn = document.querySelector("#page-create .btn-primary");
  if (submitBtn) submitBtn.textContent = "提交案例";
  
  // 6. 重置表单
  document.getElementById("create-case-form")?.reset();
  
  console.log("已重置为新案例模式，可以开始创建新案例");
}

async function saveDraft() {
  const title = document.getElementById("case-title").value;
  const author = document.getElementById("case-author").value;
  const department = document.getElementById("case-department").value;
  const content = document.getElementById("case-content").value;
  const caseType = document.getElementById("case-type").value;
  const caseTheme = document.getElementById("case-theme").value;
  const autoProcessCheckbox = document.getElementById("auto-process");
    const autoProcess = autoProcessCheckbox ? autoProcessCheckbox.checked : false;

  if (!title.trim() && !content.trim()) {
    alert("请至少填写标题或内容！");
    return;
  }

  if (!currentUser) {
    alert("请先登录后再保存草稿！");
    return;
  }

  const draft = {
    title,
    author,
    department,
    content,
    caseType,
    caseTheme,
    autoProcess,
    savedAt: new Date().toISOString()
  };

  // 保存到localStorage，使用用户名作为键名的一部分，跨页面刷新仍然有效
  const draftKey = `caseDraft_${currentUser.username}`;
  try {
    localStorage.setItem(draftKey, JSON.stringify(draft));
    alert("草稿保存成功！");
  } catch (error) {
    console.error("保存草稿失败:", error);
    alert("草稿保存失败，请检查存储空间");
  }
}

// 加载草稿
function loadDraft() {
  // 检测强制重置标志，直接返回不加载草稿
  const forceReset = localStorage.getItem("forceReset");
  if (forceReset) {
    localStorage.removeItem("forceReset");
    return;
  }

  // 检查是否正在编辑案例，如果是则不加载草稿
  const editingCaseId = localStorage.getItem("editingCaseId");
  if (editingCaseId) {
    // 如果正在编辑案例，保持表单数据不变，不加载草稿
    return;
  }
  
  // 检查是否刚提交完案例（使用localStorage持久化标志，跨页面刷新仍然有效）
  const justSubmitted = localStorage.getItem("justSubmittedCase");
  if (justSubmitted) {
    localStorage.removeItem("justSubmittedCase");
    // 强制清空所有表单字段
    document.getElementById("case-title").value = "";
    document.getElementById("case-author").value = "";
    document.getElementById("case-department").value = "";
    document.getElementById("case-content").value = "";
    // 下拉框使用selectedIndex重置
    document.getElementById("case-type").selectedIndex = 0;
    document.getElementById("case-theme").selectedIndex = 0;
    if (document.getElementById("auto-process")) {
      document.getElementById("auto-process").checked = true;
    }
    // 删除所有可能的草稿数据
    if (currentUser) {
      const draftKey = `caseDraft_${currentUser.username}`;
      localStorage.removeItem(draftKey);
      sessionStorage.removeItem(draftKey);
    }
    localStorage.removeItem("caseDraft");
    sessionStorage.removeItem("caseDraft");
    return;
  }
  
  if (!currentUser) {
    return;
  }
  
  // 使用用户名作为键名的一部分，从localStorage加载（持久化存储）
  const draftKey = `caseDraft_${currentUser.username}`;
  const draftStr = localStorage.getItem(draftKey);
  
  if (!draftStr) {
    return;
  }

  try {
    const draft = JSON.parse(draftStr);
    
    // 填充表单
    document.getElementById("case-title").value = draft.title || "";
    document.getElementById("case-author").value = draft.author || "";
    document.getElementById("case-department").value = draft.department || "";
    document.getElementById("case-content").value = draft.content || "";
    document.getElementById("case-type").value = draft.caseType || "";
    document.getElementById("case-theme").value = draft.caseTheme || "";
    if (draft.autoProcess !== undefined && document.getElementById("auto-process")) {
      document.getElementById("auto-process").checked = draft.autoProcess;
    }
    
    // 提示用户
    const savedDate = new Date(draft.savedAt).toLocaleString("zh-CN");
    console.log(`已加载 ${savedDate} 保存的草稿`);
  } catch (error) {
    console.error("加载草稿失败:", error);
    // 如果解析失败，清除无效的草稿数据
    localStorage.removeItem(draftKey);
    sessionStorage.removeItem(draftKey);
  }
}

// ============ 审核管理 ============

let currentReviewTab = "pending";

async function loadReviewCases() {
  let url = "/cases";
  if (currentReviewTab === "pending") {
    url += "?status=pending_review";
  } else if (currentReviewTab === "approved") {
    url += "?status=approved_all";
  } else if (currentReviewTab === "rejected") {
    url += "?status=rejected";
  } else if (currentReviewTab === "all") {
    url += "?status=all";
  }
  const data = await apiRequest(url);
  if (data.success) {
    renderReviewCases(data.data);
  }
}

function renderReviewCases(cases, containerId = "review-list") {
  const container = document.getElementById("review-list");
  console.log('renderReviewCases called with', cases.length, 'cases');
  
  if (!cases.length) {
    container.innerHTML =
      '<p style="text-align: center; color: var(--text-light); padding: 2rem;">暂无案例</p>';
    return;
  }

  const likedCases = JSON.parse(localStorage.getItem("likedCases") || "[]");

  const html = cases
    .map(
      (c) => {
        const isLiked = likedCases.includes(String(c.id));
        return `
        <div class="case-card" data-case-id="${c.id}">
            <div class="case-card-header">
                <div>
                    <div class="case-type">${TYPE_NAMES[c.type] || c.type}</div>
                    <div class="case-title">${c.title}</div>
                </div>
                <span class="status-badge ${STATUS_CLASSES[c.status] || ''}">${STATUS_NAMES[c.status] || c.status}</span>
            </div>
            <div class="case-card-body">
                <div class="case-meta">
                    <span>📅 ${formatDate(c.created_at)}</span>
                    ${c.author ? `<span>👤 ${c.author}</span>` : ""}
                </div>
                <div class="case-summary">
                    ${c.content?.substring(0, 150) || ""}...
                </div>
            </div>
            <div class="case-card-footer">
                <div class="case-stats">
                    <span>👁️ ${c.view_count || 0}</span>
                    <span>❤️ ${c.like_count || 0}</span>
                </div>
                <div class="case-actions">
                    <button type="button" class="btn btn-secondary btn-sm btn-view-detail" data-case-id="${c.id}">查看详情</button>
                ${
                  c.status === "pending_review"
                    ? `
                    <button type="button" class="btn btn-primary btn-sm" onclick="openReviewModal(${c.id})">审核</button>
                `
                    : ""
                }
                </div>
            </div>
            <div class="case-detail" id="case-detail-${containerId}-${c.id}">
                <div class="detail-content">
                    <div class="detail-row">
                        <strong>作者：</strong>${c.author || '未知'}
                    </div>
                    <div class="detail-row">
                        <strong>部门：</strong>${c.department || '未知'}
                    </div>
                    <div class="detail-row">
                        <strong>类型：</strong>${TYPE_NAMES[c.type] || c.type}
                    </div>
                    <div class="detail-row">
                        <strong>主题：</strong>${c.theme || '未设置'}
                    </div>
                    <div class="detail-row detail-content-full">
                        <strong>内容：</strong>
                        <div>${c.content || '暂无内容'}</div>
                    </div>
                    ${c.keywords && c.keywords.length ? `
                    <div class="detail-row">
                        <strong>关键词：</strong>
                        ${c.keywords.map(k => `<span class="keyword-tag">${k}</span>`).join('')}
                    </div>
                    ` : ''}
                    <div class="detail-actions">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCaseDetail(${c.id}, '${containerId}')">收起详情</button>
                    </div>
                </div>
            </div>
        </div>
    `;
      }
    )
    .join("");
  
  container.innerHTML = html;
  console.log('Review cases rendered with detail expand/collapse functionality');
  
  container.querySelectorAll('.btn-view-detail').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      e.preventDefault();
      const caseId = parseInt(this.dataset.caseId);
      if (caseId) {
        console.log('Review page view detail button clicked for case:', caseId);
        toggleCaseDetail(caseId, containerId);
      }
    });
  });
}

// 切换案例详情显示/隐藏
function toggleCaseDetail(caseId, containerId) {
  console.log(`toggleCaseDetail called for caseId: ${caseId}, containerId: ${containerId}`);
  
  // 使用容器ID来创建唯一的详情元素ID
  const detailId = containerId ? `case-detail-${containerId}-${caseId}` : `case-detail-${caseId}`;
  const detailElement = document.getElementById(detailId);
  
  if (!detailElement) {
    console.error(`Detail element not found: ${detailId}`);
    return;
  }
  
  // 查找对应的卡片和按钮
  const caseCard = detailElement.closest('.case-card');
  const cardButton = caseCard ? caseCard.querySelector('.btn-view-detail') : null;
  
  console.log('Elements found:', {
    detailElement: !!detailElement,
    caseCard: !!caseCard,
    cardButton: !!cardButton
  });
  
  // 获取当前展开状态
  const isExpanded = detailElement.classList.contains('expanded');
  console.log(`Current expanded state: ${isExpanded}`);
  
  if (isExpanded) {
    // 收起详情
    detailElement.classList.remove('expanded');
    if (cardButton) {
      cardButton.textContent = "查看详情";
    }
    console.log('Detail collapsed');
  } else {
    // 展开详情
    detailElement.classList.add('expanded');
    if (cardButton) {
      cardButton.textContent = "收起详情";
    }
    console.log('Detail expanded');
  }
}

function switchReviewTab(tab) {
  currentReviewTab = tab;
  document
    .querySelectorAll(".tabs .tab")
    .forEach((t) => t.classList.remove("active"));
  document.querySelector(`[data-tab="${tab}"]`).classList.add("active");
  loadReviewCases();
}

function openReviewModal(caseId) {
  // 清空表单，确保每个案例的审核都是独立的
  document.getElementById("reviewer-name").value = "";
  document.getElementById("review-comment").value = "";
  
  // 默认选中"通过"选项
  const approveRadio = document.querySelector('input[name="review-status"][value="approve"]');
  if (approveRadio) {
    approveRadio.checked = true;
  }
  
  document.getElementById("review-case-id").value = caseId;
  
  // 加载当前案例的草稿（如果有的话）
  loadReviewDraft(caseId);
  
  document.getElementById("review-modal").classList.add("active");
}

function closeReviewModal() {
  document.getElementById("review-modal").classList.remove("active");
  document.getElementById("reviewer-name").value = "";
  document.getElementById("review-comment").value = "";
}

function saveReviewDraft() {
  const caseId = document.getElementById("review-case-id").value;
  const reviewer = document.getElementById("reviewer-name").value;
  const comment = document.getElementById("review-comment").value;
  const status = document.querySelector('input[name="review-status"]:checked')?.value || 'approve';
  
  if (!reviewer.trim() && !comment.trim()) {
    alert("没有需要保存的内容");
    return;
  }
  
  const draft = {
    caseId: caseId,
    reviewer: reviewer,
    comment: comment,
    status: status,
    savedAt: new Date().toISOString()
  };
  
  localStorage.setItem(`reviewDraft_${caseId}`, JSON.stringify(draft));
  alert("草稿已保存");
}

function loadReviewDraft(caseId) {
  const draftStr = localStorage.getItem(`reviewDraft_${caseId}`);
  if (!draftStr) return;
  
  try {
    const draft = JSON.parse(draftStr);
    
    if (draft.reviewer) {
      document.getElementById("reviewer-name").value = draft.reviewer;
    }
    if (draft.comment) {
      document.getElementById("review-comment").value = draft.comment;
    }
    if (draft.status) {
      const radio = document.querySelector(`input[name="review-status"][value="${draft.status}"]`);
      if (radio) {
        radio.checked = true;
      }
    }
    
    console.log("Loaded review draft for case", caseId);
  } catch (e) {
    console.error("Failed to load review draft:", e);
  }
}

async function submitReview() {
  try {
    const caseId = document.getElementById("review-case-id").value;
    const reviewer = document.getElementById("reviewer-name").value;
    const comment = document.getElementById("review-comment").value;
    const status = document.querySelector(
      'input[name="review-status"]:checked',
    ).value;

    if (!reviewer.trim() || !comment.trim()) {
      alert("请填写完整信息！");
      return;
    }

    const formData = new FormData();
    formData.append("reviewer", reviewer);
    formData.append("comment", comment);
    formData.append("status", status);

    const data = await formRequest(`/reviews/${caseId}`, formData);
    if (data.success) {
      alert("审核完成！");
      
      // 清除已提交的草稿
      localStorage.removeItem(`reviewDraft_${caseId}`);
      
      closeReviewModal();
      loadReviewCases();
    }
  } catch (error) {
    console.error("submitReview error:", error);
    alert("提交审核时发生错误: " + error.message);
  }
}

// ============ 数据统计 ============

async function loadStats() {
  const data = await apiRequest("/statistics");
  if (data.success) {
    const stats = data.data;
    const dashboard = document.getElementById("stats-dashboard");
    
    const types = ['TYPE_A', 'TYPE_B', 'TYPE_C'];
    const themes = ['强国建设', '上海实践', '创新发展', '校园文明'];
    
    dashboard.innerHTML = `
            <div class="stats-section-grid">
                <div class="chart-container">
                    <h4 style="margin-bottom: 1rem;">案例总数</h4>
                    <div class="stat-value">${stats.total_cases || 0}</div>
                    <div class="stat-label">已进入案例库</div>
                </div>
                <div class="chart-container">
                    <h4 style="margin-bottom: 1rem;">互动数据</h4>
                    <div style="font-size: 0.95rem;">
                        <div style="margin: 8px 0;">👁️ 总浏览：${stats.total_views || 0}</div>
                        <div style="margin: 8px 0;">❤️ 总点赞：${stats.total_likes || 0}</div>
                    </div>
                </div>
                <div class="chart-container">
                    <h4 style="margin-bottom: 1rem;">按类型分类</h4>
                    <div style="font-size: 0.95rem;">
                        ${types.map(type => `
                            <div style="margin: 8px 0;">${TYPE_NAMES[type] || type}：${(stats.by_type || {})[type] || 0}</div>
                        `).join("")}
                    </div>
                </div>
                <div class="chart-container">
                    <h4 style="margin-bottom: 1rem;">按主题分类</h4>
                    <div style="font-size: 0.95rem;">
                        ${themes.map(theme => `
                            <div style="margin: 8px 0;">${theme}：${(stats.by_theme || {})[theme] || 0}</div>
                        `).join("")}
                    </div>
                </div>
            </div>
        `;
  }
}

// ============ 我的案例 ============

let currentMyCasesTab = "pending_review";

async function loadMyCases() {
  if (!currentUser) {
    document.getElementById("my-cases-list").innerHTML = 
      '<p style="text-align: center; color: var(--text-light); padding: 2rem;">请先登录查看您的案例</p>';
    return;
  }
  
  console.log("加载我的案例，当前用户:", currentUser.username);
  console.log("当前用户ID:", currentUser.id);
  
  const url = `/cases?author=${encodeURIComponent(currentUser.username)}&status=all`;
  
  const data = await apiRequest(url);
  console.log("我的案例数据:", data);
  if (data.success) {
    renderMyCases(data.data, "my-cases-list");
  } else {
    document.getElementById("my-cases-list").innerHTML = 
      '<p style="text-align: center; color: var(--text-light); padding: 2rem;">加载失败，请稍后再试</p>';
  }
}

function switchMyCasesTab(tab) {
  currentMyCasesTab = tab;
  document.querySelectorAll("#page-my-cases .tabs .tab").forEach(t => t.classList.remove("active"));
  document.querySelector(`#page-my-cases [data-tab="${tab}"]`).classList.add("active");
  loadMyCases();
}

// 渲染我的案例列表
function renderMyCases(cases, containerId) {
  const container = document.getElementById(containerId);
  
  const tabNames = {
    "all": "提交记录",
    "pending_review": "待审核",
    "approved": "已通过",
    "needs_revision": "已驳回"
  };
  
  // 前端过滤：确保只显示当前tab对应的案例
  let filteredCases = cases;
  if (currentMyCasesTab !== "all") {
    filteredCases = cases.filter(c => c.status === currentMyCasesTab);
  }
  
  if (!filteredCases.length) {
    container.innerHTML = `
      <div style="text-align: center; padding: 3rem 1rem;">
        <div style="font-size: 3rem; margin-bottom: 1rem;">📝</div>
        <h3 style="margin-bottom: 0.5rem; color: var(--text-secondary);">暂无${tabNames[currentMyCasesTab] || '案例'}</h3>
        <p style="color: var(--text-light); margin-bottom: 1.5rem;">当前分类下没有案例</p>
        <button class="btn btn-primary" onclick="navigateTo('create')">创建新案例</button>
      </div>
    `;
    return;
  }

  const likedCases = JSON.parse(localStorage.getItem("likedCases") || "[]");

  container.innerHTML = filteredCases
    .map(
      (c) => {
        const isLiked = likedCases.includes(String(c.id));
        return `
        <div class="case-card" data-case-id="${c.id}">
            <div class="case-card-header">
                <div class="case-type">${TYPE_NAMES[c.type] || c.type}</div>
                <div class="case-title">${c.title}</div>
            </div>
            <div class="case-card-body">
                <div class="case-meta">
                    <span>📅 ${formatDate(c.created_at)}</span>
                </div>
                <div class="case-summary">
                    ${c.content?.substring(0, 150) || ""}...
                </div>
            </div>
            <div class="case-card-footer">
                <div class="case-stats">
                    <span>👁️ ${c.view_count || 0}</span>
                    <span>❤️ ${c.like_count || 0}</span>
                </div>
                <span class="status-badge ${STATUS_CLASSES[c.status] || ''}">${STATUS_NAMES[c.status] || c.status}</span>
            </div>
            <div class="case-actions">
                <button type="button" class="btn btn-secondary btn-view-detail" data-case-id="${c.id}">查看详情</button>
                ${
                  c.status !== "approved"
                    ? `
                    <button type="button" class="btn btn-primary btn-edit-case" onclick="event.preventDefault(); event.stopPropagation(); editMyCase(${c.id})">修改</button>
                `
                    : ""
                }
                <button type="button" class="btn btn-danger btn-delete-case" onclick="event.preventDefault(); event.stopPropagation(); deleteMyCase(${c.id})">删除</button>
            </div>
            <div class="case-detail" id="case-detail-${containerId}-${c.id}">
                <div class="detail-content">
                    <div class="detail-row">
                        <strong>作者：</strong>${c.author || '未知'}
                    </div>
                    <div class="detail-row">
                        <strong>部门：</strong>${c.department || '未知'}
                    </div>
                    <div class="detail-row">
                        <strong>类型：</strong>${TYPE_NAMES[c.type] || c.type}
                    </div>
                    <div class="detail-row">
                        <strong>主题：</strong>${c.theme || '未设置'}
                    </div>
                    <div class="detail-row detail-content-full">
                        <strong>内容：</strong>
                        <div>${c.content || '暂无内容'}</div>
                    </div>
                    ${c.keywords && c.keywords.length ? `
                    <div class="detail-row">
                        <strong>关键词：</strong>
                        ${c.keywords.map(k => `<span class="keyword-tag">${k}</span>`).join('')}
                    </div>
                    ` : ''}
                    <div class="detail-actions">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="toggleCaseDetail(${c.id}, '${containerId}')">收起详情</button>
                    </div>
                </div>
            </div>
        </div>
    `;
      }
    )
    .join("");
  
  container.querySelectorAll('.btn-view-detail').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      e.preventDefault();
      const caseId = parseInt(this.dataset.caseId);
      if (caseId) {
        console.log('My cases view detail button clicked for case:', caseId);
        toggleCaseDetail(caseId, containerId);
      }
    });
  });
}

// 从我的案例进入编辑模式
function editMyCase(caseId) {
  try {
    console.log("editMyCase called with caseId:", caseId);
    
    // 立即保存编辑状态（必须在任何操作之前保存）
    localStorage.setItem("editingCaseId", String(caseId));
    localStorage.setItem("fromMyCases", "true");
    localStorage.setItem("resubmitCase", "true");
    localStorage.setItem("isEditingMode", "true");
    
    // 先切换到创建页面（立即执行，不等待API响应）
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    
    const createPage = document.getElementById("page-create");
    if (createPage) {
      createPage.classList.add("active");
      console.log("Create page activated");
    } else {
      console.error("Create page element not found!");
      return;
    }
    
    const createNav = document.querySelector('[data-page="create"]');
    if (createNav) {
      createNav.classList.add("active");
    }
    
    lastNavigatedPage = "create";
    
    // 然后异步获取案例数据并填充表单（不增加浏览量）
    const fullUrl = `${API_BASE}/cases/${caseId}?increment_view=false`;
    console.log("Loading case from:", fullUrl);
    
    fetch(fullUrl)
      .then(response => {
        console.log("Response status:", response.status);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        console.log("API response:", data);
        if (data.success) {
          const c = data.data;
          console.log("Filling form with case data:", c);
          
          // 填充表单（直接操作，不再延迟）
          const titleEl = document.getElementById("case-title");
          const authorEl = document.getElementById("case-author");
          const deptEl = document.getElementById("case-department");
          const contentEl = document.getElementById("case-content");
          const typeEl = document.getElementById("case-type");
          const themeEl = document.getElementById("case-theme");
          
          if (titleEl) titleEl.value = c.title || "";
          if (authorEl) authorEl.value = c.author || "";
          if (deptEl) deptEl.value = c.department || "";
          if (contentEl) contentEl.value = c.content || "";
          if (typeEl) typeEl.value = c.type || "";
          if (themeEl) themeEl.value = c.theme || "";
          
          // 更新页面标题和按钮
          const pageTitle = document.querySelector("#page-create .page-title");
          if (pageTitle) pageTitle.textContent = "修改案例";
          
          const submitBtn = document.querySelector("#page-create .btn-primary");
          if (submitBtn) submitBtn.textContent = "重新提交";
          
          console.log("Form filled successfully");
        } else {
          console.error("API returned error:", data.message);
          alert("加载案例失败: " + (data.message || "未知错误"));
          localStorage.removeItem("editingCaseId");
          localStorage.removeItem("fromMyCases");
          localStorage.removeItem("resubmitCase");
        }
      })
      .catch(error => {
        console.error("Failed to load case:", error);
        alert("加载案例失败: " + error.message);
        localStorage.removeItem("editingCaseId");
        localStorage.removeItem("fromMyCases");
        localStorage.removeItem("resubmitCase");
      });
    
  } catch (error) {
    console.error("editMyCase error:", error);
    alert("编辑案例时发生错误: " + error.message);
    localStorage.removeItem("editingCaseId");
    localStorage.removeItem("fromMyCases");
    localStorage.removeItem("resubmitCase");
  }
}

// 删除我的案例
async function deleteMyCase(caseId) {
  try {
    console.log("deleteMyCase called with caseId:", caseId);
    
    const confirmDelete = confirm("确定要删除这个案例吗？此操作不可撤销！");
    if (!confirmDelete) {
      console.log("用户取消删除");
      return;
    }
    
    const response = await fetch(`${API_BASE}/cases/${caseId}`, {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${authToken}`
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      alert("案例删除成功！");
      await loadMyCases();
      
      if (data.deleted_stats && data.deleted_stats.was_in_library) {
        if (typeof loadStatistics === 'function') {
          await loadStatistics();
        }
        if (typeof loadStats === 'function') {
          await loadStats();
        }
        if (typeof loadCases === 'function') {
          await loadCases();
        }
      }
    } else {
      alert("删除失败: " + (data.error || "未知错误"));
    }
  } catch (error) {
    console.error("deleteMyCase error:", error);
    alert("删除案例时发生错误: " + error.message);
  }
}

// 从审核管理页面删除案例
async function deleteCaseFromReview(caseId) {
  try {
    console.log("deleteCaseFromReview called with caseId:", caseId);
    
    const confirmDelete = confirm("确定要删除这个已通过的案例吗？此操作不可撤销！");
    if (!confirmDelete) {
      console.log("用户取消删除");
      return;
    }
    
    const response = await fetch(`${API_BASE}/cases/${caseId}`, {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${authToken}`
      }
    });
    
    const data = await response.json();
    
    if (data.success) {
      alert("案例删除成功！");
      loadReviewCases();
      
      if (data.deleted_stats && data.deleted_stats.was_in_library) {
        if (typeof loadStatistics === 'function') {
          await loadStatistics();
        }
        if (typeof loadStats === 'function') {
          await loadStats();
        }
        if (typeof loadCases === 'function') {
          await loadCases();
        }
      }
    } else {
      alert("删除失败: " + (data.error || "未知错误"));
    }
  } catch (error) {
    console.error("deleteCaseFromReview error:", error);
    alert("删除案例时发生错误: " + error.message);
  }
}

// 直接跳转到创建页面，立即执行
function goToCreatePageDirect(caseId) {
  console.log("goToCreatePageDirect called with caseId:", caseId);
  
  // 设置编辑模式标志，防止其他代码干扰
  localStorage.setItem("isEditingMode", "true");
  
  // 更新最后导航状态
  lastNavigatedPage = "create";
  
  // 隐藏所有页面
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
  
  // 显示创建页面
  const createPage = document.getElementById("page-create");
  if (createPage) {
    createPage.classList.add("active");
    console.log("Create page activated");
  }
  
  // 设置导航激活
  const createNav = document.querySelector('[data-page="create"]');
  if (createNav) createNav.classList.add("active");
  
  // 延迟加载案例数据并填充表单
  setTimeout(() => {
    loadAndFillCaseData(caseId);
  }, 50);
}

// 加载案例数据并填充表单
async function loadAndFillCaseData(caseId) {
  try {
    console.log("loadAndFillCaseData called with caseId:", caseId);
    
    const data = await apiRequest(`/cases/${caseId}`);
    
    if (data.success) {
      const c = data.data;
      console.log("Case data loaded:", c);
      
      // 填充表单
      const titleEl = document.getElementById("case-title");
      const authorEl = document.getElementById("case-author");
      const deptEl = document.getElementById("case-department");
      const contentEl = document.getElementById("case-content");
      const typeEl = document.getElementById("case-type");
      const themeEl = document.getElementById("case-theme");
      
      if (titleEl) titleEl.value = c.title || "";
      if (authorEl) authorEl.value = c.author || "";
      if (deptEl) deptEl.value = c.department || "";
      if (contentEl) contentEl.value = c.content || "";
      if (typeEl) typeEl.value = c.type || "";
      if (themeEl) themeEl.value = c.theme || "";
      
      // 更新页面标题和按钮
      const pageTitle = document.querySelector("#page-create .page-title");
      if (pageTitle) pageTitle.textContent = "修改案例";
      
      const submitBtn = document.querySelector("#page-create .btn-primary");
      if (submitBtn) submitBtn.textContent = "重新提交";
      
      console.log("Form filled successfully");
    } else {
      alert("加载案例数据失败，请刷新页面重试");
    }
  } catch (error) {
    console.error("loadAndFillCaseData error:", error);
    alert("加载案例数据失败: " + error.message);
  }
}

// 直接跳转到创建案例页面，不经过权限检查
function goToCreatePage() {
  try {
    console.log("goToCreatePage called");
    
    // 更新最后导航页面状态
    lastNavigatedPage = "create";
    
    // 隐藏所有页面
    const allPages = document.querySelectorAll(".page");
    console.log("Found pages:", allPages.length);
    allPages.forEach((p) => p.classList.remove("active"));
    
    // 移除所有导航链接激活状态
    const allNavs = document.querySelectorAll(".nav-link");
    console.log("Found nav links:", allNavs.length);
    allNavs.forEach((l) => l.classList.remove("active"));
    
    // 显示创建案例页面
    const createPage = document.getElementById("page-create");
    console.log("Create page element:", createPage);
    if (createPage) {
      createPage.classList.add("active");
      console.log("Create page activated");
    } else {
      console.error("Create page element not found!");
    }
    
    // 设置导航链接激活状态
    const createNav = document.querySelector('[data-page="create"]');
    console.log("Create nav element:", createNav);
    if (createNav) {
      createNav.classList.add("active");
    }
    
    // 等待页面切换后填充表单
    console.log("Scheduling fillEditForm");
    setTimeout(() => {
      fillEditForm();
    }, 100);
    
    console.log("goToCreatePage completed");
  } catch (error) {
    console.error("goToCreatePage error:", error);
    alert("导航发生错误: " + error.message);
  }
}

// 填充编辑表单
function fillEditForm() {
  try {
    console.log("fillEditForm called");
    
    const caseDataStr = localStorage.getItem("editingCaseData");
    console.log("editingCaseData:", caseDataStr ? "found" : "not found");
    
    if (!caseDataStr) {
      console.error("No editing case data found");
      return;
    }
    
    const c = JSON.parse(caseDataStr);
    console.log("Filling form with case data:", c);
    
    // 填充表单
    const titleEl = document.getElementById("case-title");
    const authorEl = document.getElementById("case-author");
    const deptEl = document.getElementById("case-department");
    const contentEl = document.getElementById("case-content");
    const typeEl = document.getElementById("case-type");
    const themeEl = document.getElementById("case-theme");
    
    console.log("Form elements:", {
      titleEl: !!titleEl,
      authorEl: !!authorEl,
      deptEl: !!deptEl,
      contentEl: !!contentEl,
      typeEl: !!typeEl,
      themeEl: !!themeEl
    });
    
    if (titleEl) titleEl.value = c.title || "";
    else console.error("titleEl not found");
    
    if (authorEl) authorEl.value = c.author || "";
    else console.error("authorEl not found");
    
    if (deptEl) deptEl.value = c.department || "";
    else console.error("deptEl not found");
    
    if (contentEl) contentEl.value = c.content || "";
    else console.error("contentEl not found");
    
    if (typeEl) typeEl.value = c.type || "";
    else console.error("typeEl not found");
    
    if (themeEl) themeEl.value = c.theme || "";
    else console.error("themeEl not found");
    
    // 更新页面标题
    const pageTitle = document.querySelector("#page-create .page-title");
    console.log("pageTitle:", pageTitle);
    if (pageTitle) pageTitle.textContent = "修改案例";
    
    // 更新提交按钮文本为"重新提交"
    const submitBtn = document.querySelector("#page-create .btn-primary");
    console.log("submitBtn:", submitBtn);
    if (submitBtn) submitBtn.textContent = "重新提交";
    
    // 清除临时存储的案例数据
    localStorage.removeItem("editingCaseData");
    
    console.log("Form filled successfully");
  } catch (error) {
    console.error("fillEditForm error:", error);
  }
}

// 重新提交案例（修改后再次提交审核）
async function resubmitCase(caseId) {
  try {
    console.log("resubmitCase called with caseId:", caseId);
    
    // 先保存编辑状态（必须在导航前保存）
    localStorage.setItem("editingCaseId", caseId);
    localStorage.setItem("fromMyCases", "true");
    localStorage.setItem("resubmitCase", "true");
    
    // 获取案例数据
    const data = await apiRequest(`/cases/${caseId}`);
    console.log("API response:", data);
    
    if (data.success) {
      const c = data.data;
      console.log("Case data:", c);
      
      // 保存案例数据到localStorage，供创建页面使用
      localStorage.setItem("editingCaseData", JSON.stringify(c));
      
      // 直接导航到创建页面（不经过权限检查）
      goToCreatePage();
      
    } else {
      alert("加载案例失败，请稍后再试");
      // 清除编辑状态
      localStorage.removeItem("editingCaseId");
      localStorage.removeItem("fromMyCases");
      localStorage.removeItem("resubmitCase");
    }
  } catch (error) {
    console.error("resubmitCase error:", error);
    alert("重新提交案例时发生错误: " + error.message);
    // 清除编辑状态
    localStorage.removeItem("editingCaseId");
    localStorage.removeItem("fromMyCases");
    localStorage.removeItem("resubmitCase");
  }
}

// ============ 案例提交 ============

// 保存案例提交草稿到本地存储
function saveSubmitDraft() {
  const title = document.getElementById("submit-case-title").value;
  const author = document.getElementById("submit-case-author").value;
  const department = document.getElementById("submit-case-department").value;
  const content = document.getElementById("submit-case-content").value;
  const caseType = document.getElementById("submit-case-type").value;
  const caseTheme = document.getElementById("submit-case-theme").value;
  const autoProcess = document.getElementById("submit-auto-process") ? document.getElementById("submit-auto-process").checked : true;

  if (!title.trim() && !content.trim()) {
    alert("请至少填写标题或内容！");
    return;
  }

  if (!currentUser) {
    alert("请先登录后再保存草稿！");
    return;
  }

  const draft = {
    title,
    author,
    department,
    content,
    caseType,
    caseTheme,
    autoProcess,
    savedAt: new Date().toISOString()
  };

  // 保存到localStorage，使用用户名作为键名的一部分，跨页面刷新仍然有效
  const draftKey = `caseDraft_${currentUser.username}`;
  try {
    localStorage.setItem(draftKey, JSON.stringify(draft));
    alert("草稿保存成功！");
  } catch (error) {
    console.error("保存草稿失败:", error);
    alert("草稿保存失败，请检查存储空间");
  }
}

// 加载案例提交草稿
function loadSubmitDraft() {
  // 检查是否在编辑案例
  const editingCaseId = localStorage.getItem("editingCaseId");
  const btnSubmitNew = document.getElementById("btn-submit-new");
  const btnUpdateCase = document.getElementById("btn-update-case");
  const pageTitle = document.getElementById("submit-page-title");
  
  if (editingCaseId) {
    // 正在编辑案例，显示"保存修改"按钮
    if (btnSubmitNew) btnSubmitNew.style.display = "none";
    if (btnUpdateCase) btnUpdateCase.style.display = "inline-block";
    if (pageTitle) pageTitle.textContent = "编辑案例";
    
    // 加载要编辑的案例数据
    editCase(editingCaseId);
    return;
  } else {
    // 不是在编辑案例，显示"提交案例"按钮
    if (btnSubmitNew) btnSubmitNew.style.display = "inline-block";
    if (btnUpdateCase) btnUpdateCase.style.display = "none";
    if (pageTitle) pageTitle.textContent = "案例提交";
  }
  
  // 使用用户名作为键名的一部分，从sessionStorage加载
  let draftStr;
  if (currentUser) {
    const draftKey = `caseDraft_${currentUser.username}`;
    draftStr = sessionStorage.getItem(draftKey);
  }
  
  if (!draftStr) {
    return;
  }

  try {
    const draft = JSON.parse(draftStr);
    
    // 填充表单
    document.getElementById("submit-case-title").value = draft.title || "";
    document.getElementById("submit-case-author").value = draft.author || "";
    document.getElementById("submit-case-department").value = draft.department || "";
    document.getElementById("submit-case-content").value = draft.content || "";
    document.getElementById("submit-case-type").value = draft.caseType || "";
    document.getElementById("submit-case-theme").value = draft.caseTheme || "";
    if (draft.autoProcess !== undefined && document.getElementById("submit-auto-process")) {
      document.getElementById("submit-auto-process").checked = draft.autoProcess;
    }
    
    // 提示用户
    const savedDate = new Date(draft.savedAt).toLocaleString("zh-CN");
    console.log(`已加载 ${savedDate} 保存的草稿`);
  } catch (error) {
    console.error("加载草稿失败:", error);
    // 如果解析失败，清除无效的草稿数据
    if (currentUser) {
      const draftKey = `caseDraft_${currentUser.username}`;
      sessionStorage.removeItem(draftKey);
    }
  }
}

// 重置案例提交表单
function resetSubmitForm() {
  document.getElementById("submit-case-title").value = "";
  document.getElementById("submit-case-author").value = "";
  document.getElementById("submit-case-department").value = "";
  document.getElementById("submit-case-content").value = "";
  document.getElementById("submit-case-type").value = "";
  document.getElementById("submit-case-theme").value = "";
  if (document.getElementById("submit-auto-process")) {
    document.getElementById("submit-auto-process").checked = true;
  }
  
  // 清除保存的草稿（使用sessionStorage）和编辑状态
  if (currentUser) {
    const draftKey = `caseDraft_${currentUser.username}`;
    sessionStorage.removeItem(draftKey);
  }
  localStorage.removeItem("editingCaseId");
  
  // 重置按钮显示
  const btnSubmitNew = document.getElementById("btn-submit-new");
  const btnUpdateCase = document.getElementById("btn-update-case");
  if (btnSubmitNew) btnSubmitNew.style.display = "inline-block";
  if (btnUpdateCase) btnUpdateCase.style.display = "none";
}

// 提交新案例
async function submitNewCase() {
  const title = document.getElementById("submit-case-title").value;
  const author = document.getElementById("submit-case-author").value;
  const department = document.getElementById("submit-case-department").value;
  const content = document.getElementById("submit-case-content").value;
  const caseType = document.getElementById("submit-case-type").value;
  const caseTheme = document.getElementById("submit-case-theme").value;
  const autoProcess = document.getElementById("submit-auto-process") ? document.getElementById("submit-auto-process").checked : true;

  if (!title.trim() || !content.trim()) {
    alert("请填写标题和内容！");
    return;
  }

  if (!autoProcess && (!caseType || !caseTheme)) {
    alert("请选择案例类型和案例主题！");
    return;
  }

  // 确保用户已登录
  if (!currentUser) {
    alert("请先登录后再提交案例！");
    openLoginModal();
    return;
  }

  const formData = new FormData();
  formData.append("title", title);
  formData.append("content", content);
  // 始终使用当前登录用户的用户名作为作者，确保"我的案例"能正确查询
  formData.append("author", currentUser.username);
  formData.append("department", department);
  formData.append("type", caseType);
  formData.append("theme", caseTheme);
  formData.append("auto_process", autoProcess);
  formData.append("status", "pending_review");  // 设置状态为待审核

  console.log("提交新案例数据:", {
    title,
    author: currentUser.username,
    department,
    type: caseType,
    theme: caseTheme,
    status: "pending_review",
    autoProcess
  });

  const data = await formRequest("/cases", formData);
  
  console.log("提交新案例响应:", data);
  
  if (data.success) {
    alert(data.message || "案例提交成功！");
    
    // 清除当前用户的草稿（使用sessionStorage）
    if (currentUser) {
      const draftKey = `caseDraft_${currentUser.username}`;
      sessionStorage.removeItem(draftKey);
    }
    
    // 清除所有可能的草稿键（兼容旧版本）
    sessionStorage.removeItem("caseDraft");
    
    // 设置标志，表示刚提交完案例，避免重新加载草稿
    sessionStorage.setItem("justSubmittedCase", "true");
    
    resetSubmitForm();
    
    // 强制刷新我的案例页面数据
    if (typeof loadMyCases === 'function') {
      loadMyCases();
    }
    
    navigateTo("my-cases");
  } else {
    alert(data.error || "案例提交失败，请稍后再试");
  }
}

// 导航到编辑案例页面
function navigateToEdit(caseId) {
  // 保存要编辑的案例ID
  localStorage.setItem("editingCaseId", caseId);
  // 导航到案例提交页面
  navigateTo("submit");
}

// 编辑未审核案例
async function editCase(caseId) {
  const data = await apiRequest(`/cases/${caseId}`);
  if (data.success) {
    const c = data.data;
    
    // 填充表单
    document.getElementById("case-title").value = c.title || "";
    document.getElementById("case-author").value = c.author || "";
    document.getElementById("case-department").value = c.department || "";
    document.getElementById("case-content").value = c.content || "";
    document.getElementById("case-type").value = c.type || "";
    document.getElementById("case-theme").value = c.theme || "";
    
    // 保存正在编辑的案例ID
    localStorage.setItem("editingCaseId", caseId);
    // 标记是从我的案例进入编辑
    localStorage.setItem("fromMyCases", "true");
    
    // 更新页面标题
    const pageTitle = document.querySelector("#page-create .page-title");
    if (pageTitle) pageTitle.textContent = "编辑案例";
    
    // 更新提交按钮文本
    const submitBtn = document.querySelector("#page-create .btn-primary");
    if (submitBtn) submitBtn.textContent = "保存修改";
    
    // 导航到创建案例页面
    navigateTo("create");
  } else {
    alert("加载案例失败，请稍后再试");
  }
}

// 修改并重新提交案例
async function updateCase() {
  const caseId = localStorage.getItem("editingCaseId");
  if (!caseId) {
    alert("未找到要修改的案例");
    return;
  }
  
  const title = document.getElementById("submit-case-title").value;
  const author = document.getElementById("submit-case-author").value;
  const department = document.getElementById("submit-case-department").value;
  const content = document.getElementById("submit-case-content").value;
  const caseType = document.getElementById("submit-case-type").value;
  const caseTheme = document.getElementById("submit-case-theme").value;
  const autoProcess = document.getElementById("submit-auto-process") ? document.getElementById("submit-auto-process").checked : true;

  if (!title.trim() || !content.trim()) {
    alert("请填写标题和内容！");
    return;
  }

  if (!autoProcess && (!caseType || !caseTheme)) {
    alert("请选择案例类型和案例主题！");
    return;
  }

  // 确保用户已登录
  if (!currentUser) {
    alert("请先登录后再修改案例！");
    openLoginModal();
    return;
  }

  const formData = new FormData();
  formData.append("title", title);
  formData.append("content", content);
  // 始终使用当前登录用户的用户名作为作者，确保"我的案例"能正确查询
  formData.append("author", currentUser.username);
  formData.append("department", department);
  formData.append("type", caseType);
  formData.append("theme", caseTheme);
  formData.append("auto_process", autoProcess);
  formData.append("status", "pending_review");  // 编辑后重新设置为待审核状态

  console.log("修改案例数据:", {
    caseId,
    title,
    author: currentUser.username,
    department,
    type: caseType,
    theme: caseTheme,
    status: "pending_review",
    autoProcess
  });

  const data = await formRequest(`/cases/${caseId}`, formData);
  
  console.log("修改案例响应:", data);
  
  if (data.success) {
    alert(data.message || "案例修改成功！");
    
    // 清除当前用户的草稿（使用sessionStorage）
    if (currentUser) {
      const draftKey = `caseDraft_${currentUser.username}`;
      sessionStorage.removeItem(draftKey);
    }
    
    // 清除所有可能的草稿键（兼容旧版本）
    sessionStorage.removeItem("caseDraft");
    
    // 设置标志，表示刚提交完案例，避免重新加载草稿
    sessionStorage.setItem("justSubmittedCase", "true");
    
    localStorage.removeItem("editingCaseId");
    resetSubmitForm();
    
    // 强制刷新我的案例页面数据
    if (typeof loadMyCases === 'function') {
      loadMyCases();
    }
    
    navigateTo("my-cases");
  } else {
    alert(data.error || "案例修改失败，请稍后再试");
  }
}

// ============ 用户认证 ============

// 打开登录弹窗
function openLoginModal() {
  document.getElementById("login-modal").classList.add("active");
}

// 关闭登录弹窗
function closeLoginModal() {
  document.getElementById("login-modal").classList.remove("active");
  document.getElementById("login-username").value = "";
  document.getElementById("login-password").value = "";
}

// 打开注册弹窗
function openRegisterModal() {
  closeLoginModal();
  document.getElementById("register-modal").classList.add("active");
}

// 关闭注册弹窗
function closeRegisterModal() {
  document.getElementById("register-modal").classList.remove("active");
  document.getElementById("register-username").value = "";
  document.getElementById("register-password").value = "";
  document.getElementById("register-password-confirm").value = "";
}

// 用户注册
async function register() {
  const username = document.getElementById("register-username").value;
  const password = document.getElementById("register-password").value;
  const passwordConfirm = document.getElementById("register-password-confirm").value;

  if (!username.trim()) {
    alert("请输入用户名");
    return;
  }

  if (!password || !passwordConfirm) {
    alert("请输入密码");
    return;
  }

  if (password !== passwordConfirm) {
    alert("两次输入的密码不一致");
    return;
  }

  if (password.length < 6) {
    alert("密码至少需要6个字符");
    return;
  }

  const formData = new FormData();
  formData.append("username", username);
  formData.append("password", password);

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      body: formData,
    });

    if (response.ok) {
      const data = await response.json();
      if (data.success) {
        alert("注册成功！您的账户已创建，默认权限为普通用户。");
        closeRegisterModal();
        openLoginModal();
      } else {
        alert(data.error || data.detail || "注册失败");
      }
    } else {
      try {
        const errorData = await response.json();
        alert("注册失败: " + (errorData.detail || errorData.error || "未知错误"));
      } catch {
        const errorText = await response.text();
        console.error("注册失败:", response.status, errorText);
        alert(`注册失败 (状态码: ${response.status})`);
      }
    }
  } catch (error) {
    console.error("注册失败:", error);
    alert("注册失败，请检查网络连接或后端服务是否启动");
  }
}

// 用户登录
async function login() {
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;

  console.log("开始登录流程");
  console.log("用户名:", username);
  console.log("密码:", password ? "***" : "(空)");

  if (!username.trim() || !password.trim()) {
    alert("请输入用户名和密码");
    return;
  }

  const formData = new FormData();
  formData.append("username", username);
  formData.append("password", password);

  console.log("发送登录请求到:", `${API_BASE}/auth/login`);

  const data = await formRequest("/auth/login", formData);

  console.log("登录响应:", data);

  if (data.success && data.data) {
    // 保存token和用户信息
    authToken = data.data.token;
    currentUser = {
      id: data.data.id,
      username: data.data.username,
      role: data.data.role,
    };

    // 存储到localStorage
    localStorage.setItem("authToken", authToken);
    localStorage.setItem("currentUser", JSON.stringify(currentUser));

    // 更新UI
    updateAuthUI();
    closeLoginModal();
    alert("登录成功！");
  } else {
    console.error("登录失败:", data);
    alert(data.error || data.detail || "登录失败，请检查用户名和密码");
  }
}

// 用户登出
function logout() {
  // 清除当前用户的草稿（使用sessionStorage）
  if (currentUser) {
    const draftKey = `caseDraft_${currentUser.username}`;
    sessionStorage.removeItem(draftKey);
  }
  
  // 清除所有可能的草稿键（兼容旧版本）
  sessionStorage.removeItem("caseDraft");
  
  // 清除本地存储
  localStorage.removeItem("authToken");
  localStorage.removeItem("currentUser");

  // 清除全局变量
  authToken = null;
  currentUser = null;

  // 更新UI
  updateAuthUI();

  // 跳转到首页
  navigateTo("home");
  alert("已退出登录");
}

// 更新认证相关的UI
function updateAuthUI() {
  const navLogin = document.getElementById("nav-login");
  const navLogout = document.getElementById("nav-logout");
  const navMyCases = document.getElementById("nav-my-cases");
  const navReview = document.getElementById("nav-review");
  const navCreate = document.getElementById("nav-create");

  if (currentUser) {
    // 已登录状态
    navLogin.style.display = "none";
    navLogout.style.display = "inline-block";
    navMyCases.style.display = "inline-block";
    navCreate.style.display = "inline-block";

    // 只有管理员才显示审核管理
    if (currentUser.role === "admin") {
      navReview.style.display = "inline-block";
    } else {
      navReview.style.display = "none";
    }
  } else {
    // 未登录状态
    navLogin.style.display = "inline-block";
    navLogout.style.display = "none";
    navMyCases.style.display = "none";
    navReview.style.display = "none";
    navCreate.style.display = "inline-block";
  }
}

// 检查登录状态
function checkAuthStatus() {
  const savedToken = localStorage.getItem("authToken");
  const savedUser = localStorage.getItem("currentUser");

  if (savedToken && savedUser) {
    authToken = savedToken;
    currentUser = JSON.parse(savedUser);
    updateAuthUI();
  }
}

// ============ 初始化 ============

document.addEventListener("DOMContentLoaded", () => {
  // 检查登录状态
  checkAuthStatus();
  
  // 如果用户刚提交完案例，自动跳转到"我的案例"页面
  const justSubmitted = localStorage.getItem("justSubmittedCase");
  if (justSubmitted === "true" && currentUser) {
    localStorage.removeItem("justSubmittedCase");
    localStorage.removeItem("forceReset");
    
    // 延迟一下确保页面完全加载
    setTimeout(() => {
      navigateTo('my-cases');
    }, 500);
    return;
  }
  
  // 加载首页数据
  loadHomeData();
});

// 阻止所有表单提交导致的页面刷新
document.addEventListener("submit", (e) => {
  e.preventDefault();
  e.stopPropagation();
});

// 阻止所有链接点击导致的页面刷新
document.addEventListener("click", (e) => {
  const target = e.target.closest('a');
  if (target && target.getAttribute('href') === '#') {
    e.preventDefault();
    e.stopPropagation();
  }
});

// 阻止按钮点击导致的页面刷新（特别是表单内的按钮）
document.addEventListener("click", (e) => {
  const target = e.target.closest('button');
  if (target) {
    // 如果按钮在表单内且没有明确的 type 属性，默认为 submit
    if (!target.hasAttribute('type') || target.getAttribute('type') === 'submit') {
      const form = target.closest('form');
      if (form) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
  }
}, true);

// 点击模态框外部关闭
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal")) {
    closeModal();
    closeReviewModal();
  }
});

// 全局事件委托：处理所有查看详情按钮的点击
document.addEventListener("click", (e) => {
  const target = e.target;
  
  // 检查是否点击了查看详情按钮
  if (target.classList.contains("btn-view-detail")) {
    e.stopPropagation();
    e.preventDefault();
    
    const caseId = parseInt(target.dataset.caseId);
    if (caseId) {
      console.log('Global click handler - view detail button clicked for case:', caseId);
      toggleCaseDetail(caseId);
    }
  }
});
