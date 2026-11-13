const test = require('node:test');
const assert = require('node:assert/strict');
const {relocateViewerUrl, planRelocations} = require('./links.cjs');

const options = {publicUri:'http://localhost:9001', fileId:'local-file', sourceFileIds:['cloud-file']};
const oldLink = 'https://design.penpot.app/#/view?file-id=cloud-file&page-id=reading&frame-id=article&section=interactions&zoom=fit';

test('迁移旧版原型链接，同时替换站点和文件 ID，保留目标页面与画板', () => {
  const result = new URL(relocateViewerUrl(oldLink, options));
  assert.equal(result.origin, 'http://localhost:9001');
  assert.equal(result.hash, '');
  assert.deepEqual(Object.fromEntries(result.searchParams), {
    'file-id':'local-file','page-id':'reading','frame-id':'article',section:'interactions',zoom:'fit',screen:'viewer'
  });
});

test('当前 query 路由支持自定义部署路径，重复迁移不再改变链接', () => {
  const current='https://design.penpot.app/?screen=viewer&file-id=local-file&page-id=reading&frame-id=article&zoom=fit';
  const config={...options,publicUri:'https://design.example.test/penpot'};
  const moved=relocateViewerUrl(current,config);
  assert.equal(new URL(moved).pathname,'/penpot/');
  assert.equal(relocateViewerUrl(moved,config),moved);
});

test('其他设计文件和普通外部网页保持原地址', () => {
  for(const value of ['https://penpot.app/pricing/self-host','https://example.test/','mailto:hello@example.test',oldLink.replace('cloud-file','another-file')]) {
    assert.equal(relocateViewerUrl(value,options),value);
  }
});

test('公共地址中的凭据、查询参数或非 HTTP 协议不会写进设计', () => {
  for(const publicUri of ['https://user:secret@example.test/','https://example.test/?userToken=secret','file:///root/design','https://example.test/#/view']) {
    assert.throws(()=>relocateViewerUrl(oldLink,{...options,publicUri}));
  }
});

test('修改前检查真实目标页面与画板；无效目标阻止整批迁移', () => {
  const catalog={file:{id:'local-file'},pages:[{id:'home',boards:[],links:[{shapeId:'button',index:0,url:oldLink}]},{id:'reading',boards:['article'],links:[]}]};
  const plan=planRelocations(catalog,options);
  assert.equal(plan.changes.length,1);
  assert.equal(plan.changes[0].pageId,'home');
  assert.throws(()=>planRelocations({...catalog,pages:[catalog.pages[0]]},options),/reading/);
  assert.throws(()=>planRelocations({...catalog,pages:[catalog.pages[0],{...catalog.pages[1],boards:[]}]},options),/article/);
});
