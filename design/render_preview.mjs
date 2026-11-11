const job = __PREVIEW_JOB__;
const task = await claimTaskSpace(job.spaceId);
const original = (await task.tabs()).find(tab => tab.url.includes(`file-id=${job.fileId}`));
if (!original) throw new Error('Penpot 设计标签页不存在');
let design;
if (original.label) {
  design = task.page(original.label);
} else {
  for (let index = 2; index < 100; index += 1) {
    try {
      design = await task.adopt(original.page, { as: `p${index}` });
      break;
    } catch (error) {
      if (!String(error).includes('page label already used')) throw error;
    }
  }
}
if (!design) throw new Error('无法接入 Penpot 设计标签页');
const preview = task.page('p1');
await design.cdp('Page.bringToFront', {});
if (!(await preview.url()).endsWith('/rasterizer.html')) {
  await preview.goto('https://design.penpot.app/rasterizer.html');
}
await design.cdp('Page.bringToFront', {});
await design.evaluate(() => {
  const hideCanvas = () => {
    for (const shape of document.querySelectorAll('svg, canvas')) {
      const bounds = shape.getBoundingClientRect();
      if (bounds.width < 300 || bounds.height < 200) continue;
      shape.dataset.casePreviewHidden = 'true';
      shape.style.setProperty('visibility', 'hidden', 'important');
    }
  };
  hideCanvas();
  if (window.caseLibraryCanvasObserver) return;
  const observer = new MutationObserver(() => {
    clearTimeout(window.caseLibraryCanvasTimer);
    window.caseLibraryCanvasTimer = setTimeout(hideCanvas, 50);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  window.caseLibraryCanvasObserver = observer;
});
if (await design.evaluate(() => performance.memory?.usedJSHeapSize > 1000000000)) {
  await design.cdp('HeapProfiler.collectGarbage', {}, { timeout: 30000 });
}

const fontRules = await design.evaluate(({ characters, weights }) => {
  const points = [...new Set([...characters].map(character => character.codePointAt(0)))];
  const matches = (range, points) => {
    const [startText, endText] = range.trim().replace(/^U\+/i, '').split('-');
    const start = parseInt(startText.replaceAll('?', '0'), 16);
    const end = parseInt((endText || startText).replaceAll('?', 'F'), 16);
    return points.some(point => point >= start && point <= end);
  };
  const weightMatches = (value, weights) => {
    const values = value.split(/\s+/).map(Number).filter(Number.isFinite);
    if (values.length === 2) return weights.some(weight => weight >= values[0] && weight <= values[1]);
    return values.some(value => weights.includes(value));
  };
  const rules = [];
  for (const sheet of document.styleSheets) {
    for (const rule of sheet.cssRules) {
      if (rule.type !== CSSRule.FONT_FACE_RULE || !rule.style.fontFamily.includes('Noto Sans SC')) continue;
      const unicodeRange = rule.style.unicodeRange;
      if (!weightMatches(rule.style.fontWeight || '400', weights)) continue;
      if (unicodeRange && !unicodeRange.split(',').some(range => matches(range, points))) continue;
      const source = rule.style.src.match(/url\(["']?([^"')]+)["']?\)/);
      if (!source) throw new Error('字体缺少可下载地址');
      rules.push({ cssText: rule.cssText, url: new URL(source[1], sheet.href || location.href).href });
    }
  }
  return rules;
}, job.fontInput);
if (job.fontInput.characters && fontRules.length === 0) {
  throw new Error('原站字体尚未加载，停止生成预览');
}

const result = await preview.evaluate(async ({ svg, fontRules, fontInput }) => {
  const documentNode = new DOMParser().parseFromString(svg, 'image/svg+xml');
  const parserError = documentNode.querySelector('parsererror');
  if (parserError) throw new Error(parserError.textContent);
  const cache = window.caseLibraryPreviewCache ||= new Map();
  const dataUrl = async url => {
    if (cache.has(url)) return cache.get(url);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`资源读取失败 ${response.status}: ${url}`);
    const blob = await response.blob();
    const value = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
    cache.set(url, value);
    return value;
  };
  const css = [];
  for (const rule of fontRules) {
    css.push(rule.cssText.replace(rule.url, await dataUrl(rule.url)));
  }
  const previewStyle = document.createElement('style');
  previewStyle.textContent = css.join('\n');
  document.head.appendChild(previewStyle);
  const loaded = await Promise.all(fontInput.weights.map(weight => document.fonts.load(`${weight} 16px "Noto Sans SC"`, fontInput.characters)));
  if (loaded.some(fonts => !fonts.length || fonts.some(font => font.status === 'error'))) {
    throw new Error('原站字体加载失败');
  }
  await document.fonts.ready;
  const style = documentNode.createElementNS('http://www.w3.org/2000/svg', 'style');
  style.textContent = css.join('\n');
  documentNode.documentElement.insertBefore(style, documentNode.documentElement.firstChild);
  let imageCount = 0;
  for (const image of documentNode.querySelectorAll('image')) {
    const href = image.getAttribute('href') || image.getAttributeNS('http://www.w3.org/1999/xlink', 'href');
    if (!href || href.startsWith('data:')) continue;
    const url = new URL(href, location.href).href;
    const embedded = await dataUrl(url);
    image.setAttribute('href', embedded);
    image.setAttributeNS('http://www.w3.org/1999/xlink', 'href', embedded);
    imageCount += 1;
  }
  const serialized = new XMLSerializer().serializeToString(documentNode);
  const blobUrl = URL.createObjectURL(new Blob([serialized], { type: 'image/svg+xml;charset=utf-8' }));
  const image = new Image();
  image.src = blobUrl;
  await image.decode();
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext('2d');
  context.drawImage(image, 0, 0);
  const data = canvas.toDataURL('image/png').split(',')[1];
  URL.revokeObjectURL(blobUrl);
  document.body.replaceChildren(canvas);
  return { data, width: canvas.width, height: canvas.height, fontCount: fontRules.length, imageCount };
}, { svg: job.svg, fontRules, fontInput: job.fontInput });

await design.cdp('Page.bringToFront', {});
const fs = await import('node:fs/promises');
await fs.writeFile(job.output, Buffer.from(result.data, 'base64'));
console.log(JSON.stringify({ output: job.output, width: result.width, height: result.height, fontCount: result.fontCount, imageCount: result.imageCount }));
