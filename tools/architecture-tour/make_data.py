import ast,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]; out=Path(__file__).resolve().parent/'flow-app'
rev='7afc5bb9e182b1c61827d6024670002a42937fc6'; base='https://github.com/LittleDrinks/case-library/blob/'+rev+'/'
ids=['agent','ai','annotations','attachments','auth','case_materials','case_sources','cases','documents','knowledge','materials','search','skills','tags']
subs={x:x.replace('_','-') for x in ids}
labels={'agent':'AI 会话与工具','ai':'模型配置与配额','annotations':'批注与反馈','attachments':'案例附件','auth':'账号与会话','case_materials':'素材引用','case_sources':'案例引用','cases':'案例与版本','documents':'Word 文档导出','knowledge':'知识目录','materials':'素材与导入','search':'检索与摘要','skills':'Skill 资源','tags':'标签体系'}
summary={'agent':'组织 AI 对话、来源、工具和稿件操作','ai':'管理模型配置、配额与模型请求','annotations':'把批注与回复绑定到正文版本','attachments':'维护案例上传文件和文件字节','auth':'保存身份、密码与登录会话','case_materials':'把素材关联到一个案例','case_sources':'引用另一篇案例的固定版本','cases':'管理私稿、版本、投稿与发布状态','documents':'把案例和来源信息渲染成 Word','knowledge':'提供知识目录与章节','materials':'接收、整理和授权素材','search':'检索案例、素材与知识并生成摘要','skills':'安装与发布 AI Skill 资源','tags':'维护标签目录并校验案例标签'}
modules=[]
for i in ids:
 p='backend/app/modules/'+i
 files=[]
 for f in sorted((root/p).glob('*.py')):
  rel=str(f.relative_to(root)); files.append({'path':rel,'name':f.name,'url':base+rel})
 modules.append({'id':subs[i],'sub':subs[i],'label':labels[i],'path':p,'summary':summary[i],'detail':summary[i], 'files':files})
imports={}
for src in ids:
 p=root/'backend/app/modules'/src
 for f in p.glob('*.py'):
  try: tree=ast.parse(f.read_text())
  except: continue
  for n in ast.walk(tree):
   names=[]
   if isinstance(n,ast.ImportFrom) and n.module: names=[n.module]
   elif isinstance(n,ast.Import): names=[a.name for a in n.names]
   for name in names:
    b=name.split('.')
    if len(b)>=3 and b[:2]==['app','modules']:
     dst=b[2]
     if dst in ids and dst!=src:
      key=(src,dst); rel=str(f.relative_to(root)); imports.setdefault(key,[]).append({'path':rel,'line':n.lineno,'url':base+rel+'#L'+str(n.lineno),'code':f'{name}'})
imp=[{'id':f'imp-{a}-{b}','a':a.replace('_','-'),'b':b.replace('_','-'),'evidence':v} for (a,b),v in sorted(imports.items())]
# Layout node positions from previous verified view
pos={'agent':(45,105),'ai':(1125,158),'annotations':(591,122),'attachments':(861,336),'auth':(1383,282),'case-materials':(45,480),'case-sources':(591,325),'cases':(321,227),'documents':(591,218),'knowledge':(45,208),'materials':(591,427),'search':(861,240),'skills':(591,523),'tags':(1125,56)}
children=[{'id':i,'x':pos[i][0],'y':pos[i][1],'width':210,'height':64} for i in pos]
def edgeset(pairs):
 by={i:(pos[i][0],pos[i][1]) for i in pos}; es=[]
 for idx,(a,b) in enumerate(pairs):
  ax,ay=by[a];bx,byy=by[b]; sx=ax+210; sy=ay+32; tx=bx;ty=byy+32; mx=(sx+tx)/2
  es.append({'id':f'e-{idx}-{a}-{b}','sources':[a],'targets':[b],'sections':[{'startPoint':{'x':sx,'y':sy},'bendPoints':[{'x':mx,'y':sy},{'x':mx,'y':ty}], 'endPoint':{'x':tx,'y':ty}}]})
 return es
allpairs=[(x['a'],x['b']) for x in imp]
overpairs=[('agent','cases'),('agent','search'),('agent','ai'),('agent','skills'),('agent','annotations'),('cases','case-materials'),('cases','case-sources'),('cases','documents'),('cases','tags'),('case-materials','materials'),('materials','attachments'),('knowledge','cases'),('ai','auth')]
for p in (allpairs,overpairs):
 if p is allpairs: (out/'all.layout.json').write_text(json.dumps({'children':children,'edges':edgeset(p)},indent=2))
 else: (out/'overview.layout.json').write_text(json.dumps({'children':children,'edges':edgeset(p)},indent=2))
req=[]
for rid,title,pairs,inc in [('browse','查找资料',[('agent','search'),('search','materials')],False),('write','写作与版本',[('cases','annotations'),('cases','materials')],False),('review','投稿审核',[('cases','annotations'),('annotations','cases')],False),('sources','引用资料',[('cases','case-materials'),('cases','case-sources')],False),('assist','AI 创作',[('agent','ai'),('agent','search')],False),('import','资料导入',[('materials','attachments'),('materials','search')],False),('export','Word 导出',[('cases','documents')],False),('login','登录',[('auth','cases')],False),('accounts','账号管理',[('auth','agent')],True),('campus','校内授权',[('auth','materials'),('auth','agent')],True)]:
 eids=[]
 for a,b in pairs:
  eids += [x['id'] for x in imp if x['a']==a and x['b']==b]
 req.append({'id':rid,'title':title,'edges':eids,'increment':inc})
front=[]
for i, (id,label) in enumerate([('views','views/'),('components','components/'),('composables','composables/'),('lib','lib/'),('styles','styles/'),('router.js','router.js'),('api.js','api.js'),('session.js','session.js')]):front.append({'id':id,'label':label,'sub':label,'files':[]})
data={'revision':rev,'base':base,'modules':modules,'imports':imp,'edges':imp,'requirements':req,'delta':{m['id']:True for m in modules if m['id'] in ['auth','agent','materials','attachments','search']},'frontend':front,'statuses':[],'runtime':[]}
(out/'data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
print('modules',len(modules),'imports',len(imp))
