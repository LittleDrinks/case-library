const {execFileSync} = require('node:child_process');
const {existsSync, readFileSync, mkdirSync, mkdtempSync, writeFileSync, rmSync} = require('node:fs');
const {resolve, join} = require('node:path');
const {parseArgs, parseEnv} = require('node:util');

function publicBase(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('PENPOT_PUBLIC_URI 必须是无凭据、查询参数和片段的 HTTP(S) 地址');
  }
  if (!url.pathname.endsWith('/')) url.pathname += '/';
  return url;
}

function relocateViewerUrl(value, {publicUri, fileId, sourceFileIds = []}) {
  const target = publicBase(publicUri);
  let source;
  try { source = new URL(value, target); }
  catch { return value; }
  if (!['http:', 'https:'].includes(source.protocol)) return value;
  const legacy = source.hash.startsWith('#/view?');
  const params = legacy ? new URLSearchParams(source.hash.slice('#/view?'.length)) : source.searchParams;
  if (!legacy && params.get('screen') !== 'viewer') return value;
  if (![fileId, ...sourceFileIds].includes(params.get('file-id'))) return value;
  params.set('screen', 'viewer');
  params.set('file-id', fileId);
  target.search = params.toString();
  return target.href;
}

function planRelocations(catalog, options) {
  if (catalog.file.id !== options.fileId) throw new Error('MCP 当前文件与目标文件 ID 不一致');
  const pages = new Map(catalog.pages.map(p => [p.id, new Set(p.boards)]));
  const changes = [];
  for (const page of catalog.pages) {
    for (const link of page.links) {
      const to = relocateViewerUrl(link.url, options);
      if (to === link.url) continue;
      const params = new URL(to).searchParams;
      const pageId = params.get('page-id');
      const frameId = params.get('frame-id');
      if (!pages.has(pageId)) throw new Error(`链接的目标页面不存在：${pageId}`);
      if (frameId && !pages.get(pageId).has(frameId)) throw new Error(`链接的目标画板不存在：${frameId}`);
      changes.push({pageId:page.id, shapeId:link.shapeId, index:link.index, from:link.url, to});
    }
  }
  return {file:catalog.file, publicUri:publicBase(options.publicUri).href, changes};
}

const catalogCode = `
return {
  file: {id:penpot.currentFile.id,name:penpot.currentFile.name},
  pages: penpot.currentFile.pages.map(page => {
    const shapes=page.findShapes();
    return {id:page.id,name:page.name,boards:shapes.filter(s=>s.type==='board').map(s=>s.id),
      links:shapes.flatMap(shape=>shape.interactions.flatMap((interaction,index)=>
        interaction.action.type==='open-url'?[{shapeId:shape.id,index,url:interaction.action.url}]:[]))};
  })
};`;

function applyCode(plan) {
  return `
const plan=${JSON.stringify(plan)};
if(penpot.currentFile.id!==plan.file.id)throw new Error('当前设计文件已改变');
const pages=new Map(penpot.currentFile.pages.map(p=>[p.id,p]));
const targets=plan.changes.map(change=>{
  const interaction=pages.get(change.pageId)?.getShapeById(change.shapeId)?.interactions[change.index];
  if(interaction?.action.type!=='open-url'||interaction.action.url!==change.from)
    throw new Error('链接在检查后发生变化，请重新生成迁移计划');
  return {interaction,change};
});
await penpot.currentFile.saveVersion('原型链接迁移前');
for(const {interaction,change} of targets)interaction.action={...interaction.action,url:change.to};
await penpot.waitForLayoutUpdate();
return {updated:targets.length};`;
}

function callCode(code) {
  const root = resolve(__dirname, '../..');
  const scratch = join(root, '.scratch');
  mkdirSync(scratch, {recursive:true});
  const directory = mkdtempSync(join(scratch, 'penpot-links-'));
  try {
    const path = join(directory, 'execute.js');
    writeFileSync(path, code, {mode:0o600});
    const result = JSON.parse(execFileSync(process.execPath, [join(__dirname,'mcp.cjs'),'execute',path], {
      env:{...process.env,PENPOT_JSON_RESPONSE:'1'}, encoding:'utf8', timeout:240000, maxBuffer:32*1024*1024,
    }));
    const text = result.content.filter(p=>p.type==='text').map(p=>p.text).join('');
    if(result.isError || text.startsWith('Tool execution failed:')) throw new Error(text);
    return JSON.parse(text).result;
  } finally {
    rmSync(directory, {recursive:true,force:true});
  }
}

function main() {
  const {values} = parseArgs({options:{
    'env-file':{type:'string'},'file-id':{type:'string'},
    'from-file-id':{type:'string',multiple:true,default:[]},
    apply:{type:'boolean',default:false}, help:{type:'boolean',default:false},
  }});
  if(values.help) {
    console.log('node tools/penpot/links.cjs [--env-file PATH] [--file-id ID] [--from-file-id OLD_ID] [--apply]\n默认只检查；PENPOT_PUBLIC_URI 指定访问地址，默认使用 MCP 当前文件，可用 --file-id 限定目标。');
    return;
  }
  const root = resolve(__dirname,'../..');
  const envPath = values['env-file'] || join(root,'deploy/penpot/.env');
  const config = existsSync(envPath) ? parseEnv(readFileSync(envPath,'utf8')) : {};
  const publicUri = process.env.PENPOT_PUBLIC_URI || config.PENPOT_PUBLIC_URI;
  if(!publicUri) throw new Error('请配置 PENPOT_PUBLIC_URI');
  publicBase(publicUri);
  const catalog = callCode(catalogCode);
  const fileId = values['file-id'] || catalog.file.id;
  const options = {publicUri,fileId,sourceFileIds:values['from-file-id']};
  const plan = planRelocations(catalog,options);
  console.log(JSON.stringify({mode:values.apply?'apply':'check',file:plan.file,publicUri:plan.publicUri,planned:plan.changes.length,samples:plan.changes.slice(0,3)},null,2));
  if(values.apply && plan.changes.length) {
    const result=callCode(applyCode(plan));
    const after=callCode(catalogCode);
    const remaining=planRelocations(after,options).changes.length;
    if(remaining) throw new Error(`仍有 ${remaining} 条链接未迁移`);
    console.log(JSON.stringify({...result,remaining}));
  }
}

module.exports = {relocateViewerUrl,planRelocations,catalogCode,applyCode};
if(require.main===module) {
  try { main(); }
  catch(error) { console.error(error.message); process.exitCode=1; }
}
