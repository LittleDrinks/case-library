import MarkdownIt from "markdown-it";

export const CITATION_PATTERN = /〔([^〔〕]+)〕|\[([^\[\]]+)\]/g;

// 安全基线：html:false 把原文中的内联 HTML 全部转义为纯文本，不进入 DOM；
// markdown-it 内置 validateLink 会拦截 javascript:、vbscript:、file: 等危险协议链接。
const parser = new MarkdownIt({ html: false, breaks: true });
wrapTables(parser);
openExternalLinks(parser);
enableCitations(parser);

const SENTINEL = /%%CIT(\d+)%%/y;

// 文本规则只按 ASCII 断句，全角〔〕标记会被整段吞掉；先把已解析的引用标记
// 预替换为 ASCII 哨兵，再由内联规则还原成引用按钮，保证在标题、列表、表格
// 单元格与粗体内都能正确保留引用交互。
function tokenizeCitation(state, silent) {
  if (!state.env?.cite) return false;
  SENTINEL.lastIndex = state.pos;
  const match = SENTINEL.exec(state.src);
  if (!match) return false;
  if (!silent) {
    const token = state.push("citation", "", 0);
    token.meta = { order: Number(match[1]) };
  }
  state.pos += match[0].length;
  return true;
}

function enableCitations(parser) {
  parser.inline.ruler.before("link", "citation", tokenizeCitation);
  parser.renderer.rules.citation = (tokens, index) => {
    const order = tokens[index].meta.order;
    return `<button type="button" class="ai-marker" data-citation-order="${order}">〔${order}〕</button>`;
  };
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
  return parser.render(String(value ?? ""), { cite: false });
}

export function renderAnswerMarkdown(value, resolve) {
  const replaced = String(value ?? "").replace(CITATION_PATTERN, (marker, fullwidth, bracket) => {
    const resolved = resolve?.((fullwidth ?? bracket).trim());
    return resolved ? `%%CIT${resolved.order}%%` : marker;
  });
  return parser.render(replaced, { cite: true });
}
