const {Client} = require('@modelcontextprotocol/sdk/client/index.js');
const {StreamableHTTPClientTransport} = require('@modelcontextprotocol/sdk/client/streamableHttp.js');
const {execFileSync} = require('node:child_process');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');

async function main() {
  const configPath = process.env.PENPOT_MCP_CONFIG || resolve(__dirname, '../../.codex/config.toml');
  const config = process.env.PENPOT_MCP_URL ? {url: process.env.PENPOT_MCP_URL} : JSON.parse(execFileSync('python3', ['-c',
    'import json,sys,tomllib; print(json.dumps(tomllib.load(open(sys.argv[1],"rb"))["mcp_servers"]["penpot"]))',
    configPath], {encoding:'utf8'}));
  const url = new URL(config.url);
  const client = new Client({name:'case-library-penpot',version:'1.0'});
  let secret = url.searchParams.get('userToken');
  try {
    await client.connect(new StreamableHTTPClientTransport(url));
    const action = process.argv[2] || 'check';
    let request;
    if (action === 'list') {
      console.log(JSON.stringify(await client.listTools()));
      return;
    }
    if (action === 'check') {
      request = {name:'execute_code',arguments:{code:'return {file:{id:penpot.currentFile.id,name:penpot.currentFile.name},page:{id:penpot.currentPage.id,name:penpot.currentPage.name},version:penpot.version};'}};
    } else if (action === 'execute') {
      request = {name:'execute_code',arguments:{code:readFileSync(process.argv[3],'utf8')}};
    } else if (action === 'tool') {
      request = {name:process.argv[3],arguments:JSON.parse(process.argv[4] || '{}')};
    } else {
      throw new Error('用法：node mcp.cjs check | execute <代码文件> | tool <工具名> <JSON参数>');
    }
    let result;
    for(let attempt=0;attempt<35;attempt++){
      result=await client.callTool(request,undefined,{timeout:action==='check'?30000:120000});
      const message=(result.content||[]).filter(p=>p.type==='text').map(p=>p.text).join('');
      if(action==='check'||!message.includes('plugin tab appears to be suspended'))break;
      await new Promise(resolve=>setTimeout(resolve,2000));
    }
    if (result.isError) process.exitCode=1;
    if (process.env.PENPOT_JSON_RESPONSE === '1') {
      let output = JSON.stringify(result);
      if (secret) output = output.replaceAll(secret, '<REDACTED>');
      console.log(output);
      return;
    }
    for (const part of result.content || []) {
      if (part.type === 'text') {
        let text=part.text;
        if(secret) text=text.replaceAll(secret,'<REDACTED>');
        console.log(text);
        if (/^Tool execution failed:/.test(text)) process.exitCode=1;
      } else if (part.type === 'image') {
        const {writeFileSync}=require('node:fs');
        const path=process.env.PENPOT_EXPORT_PATH || resolve(__dirname, 'last-export.'+(part.mimeType==='image/png'?'png':'jpg'));
        writeFileSync(path,Buffer.from(part.data,'base64'));
        console.log(JSON.stringify({image:path}));
      }
    }
  } catch(error) {
    let message=String(error.message).replaceAll(config.url,'<MCP_URL>');
    if(secret) message=message.replaceAll(secret,'<REDACTED>');
    console.error(message);
    process.exitCode=1;
  } finally {
    await client.close();
  }
}
main().catch(error=>{console.error('MCP 客户端启动失败：'+error.name);process.exitCode=1;});
