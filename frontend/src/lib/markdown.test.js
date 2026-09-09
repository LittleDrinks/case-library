import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";
import { CITATION_PATTERN, renderAnswer, renderMarkdown } from "./markdown.js";

const resolveOnly1 = (raw) => (raw === "1" ? { item: { kind: "case", id: "c-1" }, order: 1 } : null);

test("渲染标题、列表、粗体、引用、链接、分隔线与段落间距结构", () => {
  const html = renderMarkdown("## 结论\n\n- **要点**一\n- 要点二\n\n> 引用原话\n\n正文段落\n\n---\n\n[站内](https://example.com)");
  expect(html).toContain("<h2>结论</h2>");
  expect(html).toContain("<ul>");
  expect(html).toContain("<strong>要点</strong>");
  expect(html).toContain("<blockquote>");
  expect(html).toContain('<a href="https://example.com"');
  expect(html).toContain("<hr>");
  expect(html).toContain("<p>正文段落</p>");
});

test("表格被可横向滚动的容器包裹且列保有不塌缩的最小宽度", () => {
  const html = renderMarkdown("| 指标 | 数值 |\n| --- | --- |\n| 甲 | 12 |");
  expect(html).toContain('<div class="md-table-scroll"><table>');
  expect(html).toContain("<th>指标</th>");
  expect(html).toContain("</table></div>");
  const css = readFileSync(join(process.cwd(), "src/styles/markdown.css"), "utf8");
  expect(css).toMatch(/\.markdown-body th, \.markdown-body td \{[^}]*min-width: 5em/);
});

test("原文内联 HTML 被转义为纯文本而非注入 DOM", () => {
  const html = renderMarkdown("你好<script>alert(1)</script><img src=x onerror=alert(1)>");
  expect(html).not.toContain("<script");
  expect(html).not.toContain("<img");
  expect(html).toContain("&lt;script&gt;");
});

test("危险链接协议被拦截且正常链接不受影响", () => {
  for (const hostile of ["[点我](javascript:alert(1))", "[点我](vbscript:x)", "[图](data:text/html;base64,xx)"]) {
    const html = renderMarkdown(hostile);
    expect(html).not.toMatch(/href\s*=\s*"[^"]*(javascript|vbscript|data:text)/);
  }
  expect(renderMarkdown("[安全](https://example.com)")).toContain('href="https://example.com"');
});

test("链接统一在新标签打开并携带 noopener", () => {
  const html = renderMarkdown("[文档](https://example.com)");
  expect(html).toContain('target="_blank"');
  expect(html).toContain('rel="noopener noreferrer"');
});

test("流式半截 Markdown 稳定渲染不抛错", () => {
  expect(() => renderMarkdown("**未闭合加粗")).not.toThrow();
  expect(renderMarkdown("## 未完成\n\n**加粗")).toContain("<h2>未完成</h2>");
  // 表头与分隔行未完整时降级为普通段落，不产生破损表格
  const partial = renderMarkdown("| 列A | 列B |\n| --- |");
  expect(partial).toContain("<p>| 列A | 列B |");
  expect(partial).not.toContain("md-table-scroll");
  const grown = renderMarkdown("**加粗**与表格\n\n| 列A | 列B |\n| --- | --- |\n| 甲 | 乙 |");
  expect(grown).toContain("<strong>加粗</strong>");
  expect(grown).toContain("md-table-scroll");
  expect(grown).toContain("<td>乙</td>");
});

test("可解析引用标记渲染为按钮并统一顺序编号，未知标记保持纯文本", () => {
  const resolve = (raw) => (raw === "1" ? { item: { kind: "case", id: "c-1" }, order: 1 }
    : raw === "kn" ? { item: { kind: "knowledge", id: "kn" }, order: 2 } : null);
  const { html, citations } = renderAnswer("见〔1〕、[kn]与〔1〕，另有〔未知〕和[8]。", resolve);
  expect(html.match(/class="ai-marker"/g)).toHaveLength(3);
  expect(html).toContain('data-citation-order="1"');
  expect(html).toContain("〔2〕");
  expect(html).toContain("〔未知〕");
  expect(html).toContain("[8]");
  expect(citations.map((entry) => entry.order)).toEqual([1, 2, 1]);
});

test("引用标记在标题、列表、粗体与表格单元格内仍保留交互", () => {
  const html = renderAnswer(
    "## 结论〔1〕\n\n- **要点〔1〕**\n\n| 指标〔1〕 | 数值 |\n| --- | --- |\n| 甲 | 12 |",
    resolveOnly1,
  ).html;
  expect(html.match(/class="ai-marker"/g)).toHaveLength(3);
  expect(html).toContain("<h2>");
  expect(html).toContain("<strong>");
  expect(html).toContain("<td>");
});

test("数字普通链接保持原样，URL 不被污染", () => {
  const { html, citations } = renderAnswer("参考[1](https://example.org)说明。", resolveOnly1);
  expect(html).toContain('<a href="https://example.org"');
  expect(html).toContain(">1</a>");
  expect(html).not.toContain("ai-marker");
  expect(citations).toHaveLength(0);
});

test("链接文本内的标记被跳过", () => {
  const { html, citations } = renderAnswer("[见〔1〕](https://example.org)", resolveOnly1);
  expect(html).toContain("<a");
  expect(html).not.toContain("ai-marker");
  expect(html).toContain("〔1〕");
  expect(citations).toHaveLength(0);
});

test("代码 span 与围栏内的标记不转换也不进入来源", () => {
  const { html, citations } = renderAnswer("代码`〔1〕`与：\n\n```\n〔1〕\n```\n\n正文〔1〕", resolveOnly1);
  expect(html.match(/class="ai-marker"/g)).toHaveLength(1);
  expect(html).toContain("<code>〔1〕</code>");
  expect(html).toContain("<pre><code>〔1〕");
  expect(citations).toHaveLength(1);
});

test("伪标记文本不产生按钮", () => {
  const { html, citations } = renderAnswer("文本 %%CIT1%% 与〔1〕。", resolveOnly1);
  expect(html.match(/class="ai-marker"/g)).toHaveLength(1);
  expect(html).toContain("%%CIT1%%");
  expect(citations.map((entry) => entry.item.id)).toEqual(["c-1"]);
});

test("来源列表与渲染标记同源且按出现顺序", () => {
  const resolve = (raw) => (raw === "1" ? { item: { kind: "case", id: "c-1" }, order: 1 }
    : raw === "kn" ? { item: { kind: "knowledge", id: "kn-1" }, order: 2 } : null);
  const { citations } = renderAnswer("a〔1〕 b〔未知〕 c[kn] `〔1〕` d[1](https://example.org) e〔1〕", resolve);
  expect(citations.map((entry) => `${entry.item.kind}:${entry.item.id}`))
    .toEqual(["case:c-1", "knowledge:kn-1", "case:c-1"]);
});

test("不传解析器时标记一律保持纯文本", () => {
  const html = renderMarkdown("见〔1〕与[8]。%%CIT1%%");
  expect(html).not.toContain("ai-marker");
  expect(html).toContain("〔1〕");
  expect(html).toContain("[8]");
  expect(html).toContain("%%CIT1%%");
});

test("引用标记正则可全局枚举两种形式", () => {
  const matches = [..."见〔1〕与[kn]。".matchAll(CITATION_PATTERN)].map((match) => match[1] ?? match[2]);
  expect(matches).toEqual(["1", "kn"]);
});

test("安全换行支持表格且保留代码、转义及带属性标签", () => {
  const html = renderMarkdown("| 内容 |\n| --- |\n| 甲<br>乙<BR/>丙<br />丁 |\n\n`<br>` \\<br> <br onclick=alert(1)>");
  expect(html.replace(/\n/g, "")).toContain("甲<br>乙<br>丙<br>丁");
  expect(html).toContain("<code>&lt;br&gt;</code>");
  expect(html).toContain("&lt;br&gt;");
  expect(html).not.toContain("<br onclick");
});

test("任务列表显示只读勾选框，代码保持原样", () => {
  const html = renderMarkdown("- [ ] 未完成\n- [x] 已完成\n\n`- [ ] 示例`");
  expect(html.match(/type="checkbox"/g)).toHaveLength(2);
  expect(html.match(/disabled/g)).toHaveLength(2);
  expect(html).toContain('checked=');
  expect(html).toContain('<code>- [ ] 示例</code>');
});

test("候选编号不伪装成预览网址，真实来源链接保留", () => {
  const html = renderMarkdown("[预览](artifact-example) [资料](https://example.com) `artifact-example`");
  expect(html).not.toContain('href="artifact-example"');
  expect(html).toContain('预览');
  expect(html).toContain('href="https://example.com"');
  expect(html).toContain('<code>artifact-example</code>');
});
