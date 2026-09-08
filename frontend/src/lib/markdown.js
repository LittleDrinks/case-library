import MarkdownIt from "markdown-it";

export const CITATION_PATTERN = /〔([^〔〕]+)〕|\[([^\[\]]+)\]/g;

// 安全基线：html:false 把原文中的内联 HTML 全部转义为纯文本，不进入 DOM；
// markdown-it 内置 validateLink 会拦截 javascript:、vbscript:、file: 等危险协议链接。
const parser = new MarkdownIt({ html: false, breaks: true });
wrapTables(parser);
openExternalLinks(parser);
// 引用标记按官方架构在 token 层处理：block/inline 解析完成后，只转换正文
// text token，代码、链接等语境天然跳过。env.resolve 提供来源解析，
// env.citations 收集与实际渲染按钮同源的引用列表。
parser.core.ruler.after("inline", "citations", resolveCitations);
// 引用指向站内路由目标：href 由组件按检索结果白名单生成后挂在 token 属性上，
// renderAttrs 负责转义；渲染为真链接以支持键盘与浏览器新标签页。
parser.renderer.rules.citation = (tokens, index) => {
  const token = tokens[index];
  const order = Number(token.content);
  return `<a${parser.renderer.renderAttrs(token)} class="ai-marker" data-citation-order="${order}">〔${order}〕</a>`;
};

function resolveCitations(state) {
  const resolve = state.env?.resolve;
  if (!resolve) return;
  for (const block of state.tokens) {
    if (block.type === "inline" && block.children) {
      block.children = childrenWithCitations(block.children, state, resolve);
    }
  }
}

function childrenWithCitations(children, state, resolve) {
  const next = [];
  let linkDepth = 0;
  for (const token of children) {
    linkDepth += token.type === "link_open" ? 1 : token.type === "link_close" ? -1 : 0;
    if (token.type === "text" && linkDepth === 0) {
      appendTextWithCitations(next, token, state, resolve);
    } else next.push(token);
  }
  return next;
}

function appendTextWithCitations(next, token, state, resolve) {
  const value = token.content;
  let last = 0;
  for (const match of value.matchAll(CITATION_PATTERN)) {
    const resolved = resolve((match[1] ?? match[2]).trim());
    if (!resolved) continue;
    if (match.index > last) next.push(plainToken(state, value.slice(last, match.index)));
    next.push(citationToken(state, resolved));
    state.env.citations?.push(resolved);
    last = match.index + match[0].length;
  }
  if (last) {
    if (last < value.length) next.push(plainToken(state, value.slice(last)));
  } else next.push(token);
}

function plainToken(state, value) {
  const token = new state.Token("text", "", 0);
  token.content = value;
  return token;
}

function citationToken(state, resolved) {
  const token = new state.Token("citation", "", 0);
  token.content = String(resolved.order);
  if (resolved.href) {
    token.attrSet("href", resolved.href);
    token.attrSet("target", "_blank");
    token.attrSet("rel", "noopener noreferrer");
  }
  return token;
}

function wrapTables(parser) {
  parser.renderer.rules.table_open = () => '<div class="md-table-scroll"><table>';
  parser.renderer.rules.table_close = () => "</table></div>";
}

function openExternalLinks(parser) {
  const fallback = (tokens, index, options, env, self) => self.renderToken(tokens, index, options);
  const previous = parser.renderer.rules.link_open || fallback;
  parser.renderer.rules.link_open = (tokens, index, options, env, self) => {
    tokens[index].attrSet("target", "_blank");
    tokens[index].attrSet("rel", "noopener noreferrer");
    return previous(tokens, index, options, env, self);
  };
}

export function renderMarkdown(value) {
  return parser.render(String(value ?? ""));
}

export function renderAnswer(value, resolve) {
  const env = { resolve, citations: [] };
  const tokens = parser.parse(String(value ?? ""), env);
  return { html: parser.renderer.render(tokens, parser.options, env), citations: env.citations };
}
