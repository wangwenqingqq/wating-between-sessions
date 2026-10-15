const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function setup() {
  const nodes = new Map();
  const element = (tag='div') => ({tagName:tag.toUpperCase(),children: [],
    append(...items) { this.children.push(...items); }, replaceChildren() { this.children = []; },
    setAttribute(key,value) { this[key]=value; },scrollIntoView() {},showModal() {}});
  const document = {
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, element());
      if (id==='card-template') nodes.get(id).content={firstElementChild:{cloneNode:()=>{
        const card=element('article'),parts=new Map();card.className='card';
        card.querySelector=(selector)=>{if(!parts.has(selector))parts.set(selector,element());return parts.get(selector);};return card;
      }}};
      return nodes.get(id);
    },
    createElement: element,
    querySelectorAll: () => [],
  };
  const context = vm.createContext({document, URL, atob, location: {hash: ''}, sessionStorage: {getItem: () => ''},
    fetch: () => new Promise(() => {}), setInterval() {}});
  for(const file of ['vendor/markdown-it.min.js','markdown.js','app.js'])vm.runInContext(fs.readFileSync(path.join(__dirname, '../demo/ui/web',file), 'utf8'), context);
  return {nodes,context};
}

test('Status list keeps project names and prioritizes active sessions', () => {
  const {nodes,context}=setup();
  vm.runInContext(`state = {sessions: [
    {id:'codex:a',project_name: 'Alpha', state: 'COMPLETED', provider: 'codex'},
    {id:'claude:b',project_name: 'Beta', state: 'WORKING', provider: 'claude'},
    {id:'codex:e',project_name: 'Needs input', state: 'WAITING_USER', provider: 'codex'},
    {id:'codex:c',state: 'COMPLETED', provider: 'codex'},
    {id:'demo:d',state: 'COMPLETED', provider: 'demo'}
  ]}; renderSessions();`, context);
  assert.deepEqual(nodes.get('session-list').children.filter(e=>e.className==='session'||e.className==='session session-link').map(card => card.children[0].children[0].textContent), [
    'Needs input · Agent 需要你的确认', 'Beta · Agent 正在工作', 'Alpha · 本轮执行已结束',
    '未命名项目 · 本轮执行已结束', '模拟演示 · 本轮执行已结束',
  ]);
});

test('Only strict local Codex UUIDs become ChatGPT deep links', () => {
  const {nodes,context}=setup();
  const id='00000000-0000-4000-8000-000000000001';
  context.sessionID=id;
  assert.equal(vm.runInContext("sessionUrl({provider:'codex',id:'codex:'+sessionID})",context),'codex://threads/'+id);
  for(const [provider,session] of [['claude','codex:'+id],['demo','codex:'+id],['codex','codex:javascript:alert(1)'],['codex','codex:'+id+'?prompt=send'],['codex','codex:../../settings'],['codex',id]]){
    context.fixture={provider,id:session};assert.equal(vm.runInContext('sessionUrl(fixture)',context),'');
  }
  vm.runInContext("state={sessions:[{id:'codex:'+sessionID,provider:'codex',state:'WORKING',project_name:'<img onerror=bad>',stale:true}]};renderSessions();",context);
  const row=nodes.get('session-list').children[1];
  assert.equal(row.tagName,'A');assert.equal(row.href,'codex://threads/'+id);
  assert.equal(row.children[0].children[0].textContent,'<img onerror=bad> · Agent 正在工作');
  assert.match(row.children[0].children[2].textContent,/不确定/);
});

test('Session list expands independently and preserves links on tool ticks', () => {
  const {nodes,context}=setup();
  vm.runInContext("state={sessions:[{id:'codex:s',provider:'codex',state:'WORKING',project_name:'Project'}]};renderSessions();",context);
  const button=nodes.get('session-toggle'),list=nodes.get('session-list');
  button.onclick();assert.equal(button['aria-expanded'],'true');assert.equal(list.hidden,false);
  const row=list.children[1];
  vm.runInContext("state.sessions[0].detail='PreToolUse';state.sessions[0].elapsed=20;renderSessions();",context);
  assert.equal(list.children[1],row);assert.equal(list.hidden,false);
  vm.runInContext("state.sessions[0].state='COMPLETED';renderSessions();",context);
  assert.match(list.children[1].children[0].children[0].textContent,/本轮执行已结束/);assert.equal(list.hidden,false);
  nodes.get('panel-close').onclick();assert.equal(nodes.get('panel').hidden,true);assert.equal(list.hidden,false);
  button.onclick();assert.equal(button['aria-expanded'],'false');assert.equal(list.hidden,true);
  vm.runInContext('state.sessions=[];renderSessions();',context);
  assert.equal(list.children[1].className,'empty');
});

test('Only reading modes remain and sessions sit under the status strip', () => {
  const html=fs.readFileSync(path.join(__dirname,'../demo/ui/web/index.html'),'utf8');
  assert.deepEqual([...html.matchAll(/data-mode="([^"]+)"/g)].map(m=>m[1]),['timeline','discovery']);
  assert.match(html,/id="session-toggle" aria-expanded="false" aria-controls="session-list"/);
  assert.match(html,/id="session-list"[^>]+hidden/);
  assert.ok(html.indexOf('id="session-list"')<html.indexOf('id="panel"'));
  assert.ok(!html.includes('id="progress"'));
});

test('Chronicle shelves group topics without counting cross-references as new events', () => {
  const {nodes,context}=setup();
  vm.runInContext(`chronicleData={stats:{events:2,sessions:1,topics:2,first_date:'2026-08-01',last_date:'2026-10-12'},domains:[{id:'research',title:'研究与实验',count:2}],topics:[
    {id:'gts-tide',domain:'research',domain_label:'研究与实验',title:'GTS 与 TIDE',subtitle:'原文',preview:'<img onerror=bad>',count:2,sessions:1,first_date:'2026-08-01',last_date:'2026-10-12'},
    {id:'gpu-computing',domain:'research',domain_label:'研究与实验',title:'GPU',subtitle:'原文',preview:'CUDA',count:1,sessions:1,first_date:'2026-10-12',last_date:'2026-10-12'}
  ]};renderChronicles(chronicleData);`,context);
  const root=nodes.get('chronicles'),grid=root.children.find(e=>e.className==='topic-grid');
  assert.equal(grid.children.length,2);
  assert.equal(grid.children[0]['aria-label'],'阅读GTS 与 TIDE列传');
  assert.equal(grid.children[0].children.find(e=>e.className==='book-preview').textContent,'“<img onerror=bad>”');
  assert.match(root.children.find(e=>e.className==='chronicle-note').textContent,/去重/);
});

test('Dossier renders sourced chapters and every record, with no invented decisions', () => {
  const {nodes,context}=setup();
  vm.runInContext(`const entries=[
    {event_id:'a',date:'2026-08-01',title:'GTS request',summary:'真实请求',kind:'request',category:'research',source_provider:'codex'},
    {event_id:'b',date:'2026-10-12',title:'GTS result',summary:'助手自报结果',kind:'reported_result',category:'research',source_provider:'codex'}
  ];chronicleData={selected:{title:'GTS 与 TIDE',domain_label:'研究与实验',subtitle:'原文',first_date:'2026-08-01',last_date:'2026-10-12',sessions:1,count:2,kinds:{request:1,decision:0,reported_result:1,open_question:0},events:entries,chapters:{request:entries[0],decision:null,reported_result:entries[1],open_question:null}}};renderChronicles(chronicleData);`,context);
  const root=nodes.get('chronicles');
  assert.equal(root.children.find(e=>e.className==='chapter-grid').children.length,2);
  assert.equal(root.children.find(e=>e.className==='dossier-events').children.filter(e=>e.className==='card').length,2);
  const filters=root.children.find(e=>e.className==='dossier-filters');filters.children[2].onclick();
  assert.equal(root.children.find(e=>e.className==='dossier-events').children[0].className,'empty');
  assert.match(root.children.find(e=>e.className==='dossier-events').children[0].textContent,/没有证据/);
});

test('Reading chapter evidence keeps its record read after cached filter redraw', async () => {
  const {nodes,context}=setup();
  context.fetch=async()=>({ok:true,json:async()=>({verified:true,summary:'原文',source_provider:'codex',source_session_id:'s'})});
  await vm.runInContext(`state={history_enabled:true};chronicleData={selected:{title:'GTS',domain_label:'研究',subtitle:'选段',sessions:1,count:1,kinds:{request:1},
    events:[{event_id:'read-me',kind:'request',source_provider:'codex',date:'2026-10-12',read_at:0}],
    chapters:{request:{event_id:'read-me',read_at:0}}}};
    source(chronicleData.selected.chapters.request);`,context);
  const root=nodes.get('chronicles');
  root.children.find(e=>e.className==='dossier-filters').children[1].onclick();
  const card=root.children.find(e=>e.className==='dossier-events').children.find(e=>e.className==='card');
  assert.equal(card.querySelector('.unread').textContent,'已读');
  assert.equal(vm.runInContext('chronicleData.selected.chapters.request.read_at>0',context),true);
});

test('Markdown renders headings, lists, tables, quotes and code without source markers', () => {
  const {context}=setup();
  context.fixture='# Heading\n\n**bold** and *italic* and `inline`\n\n- one\n- two\n\n> quote\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n```js\nconst x = "<safe>";\n```';
  const html=vm.runInContext('BetweenMarkdown.render(fixture)',context);
  for(const pattern of [/<h1>Heading<\/h1>/,/<strong>bold<\/strong>/,/<em>italic<\/em>/,/<ul>/,/<blockquote>/,/<table>/,/<td>1<\/td>/,/<pre><code class="language-js">/,/&lt;safe&gt;/])assert.match(html,pattern);
  assert.ok(!html.includes('```'));assert.ok(!html.includes('**bold**'));
  assert.equal(vm.runInContext("BetweenMarkdown.plainText('## **Heading** with `code`')",context),'Heading with code');
});

test('Markdown escapes HTML, blocks unsafe links and never loads remote images', () => {
  const {context}=setup();
  context.fixture='<script>alert(1)</script>\n\n<img src=x onerror=bad>\n\n![tracker](https://example.invalid/pixel)\n\n[x](javascript:alert(1)) [x](data:text/html,evil) [x](file:///etc/passwd) [x](https://user:secret@example.invalid/) [safe](https://example.invalid/page)';
  const html=vm.runInContext('BetweenMarkdown.render(fixture)',context);
  assert.doesNotMatch(html,/<script|<img|<iframe|href="(?:javascript|data|file):|href="https:\/\/user:/i);
  assert.match(html,/&lt;script&gt;/);assert.match(html,/tracker/);
  assert.match(html,/<a href="https:\/\/example.invalid\/page" rel="noopener noreferrer" target="_blank">safe<\/a>/);
});

test('Verified formatting hydrates cards once and does not mark them read', async () => {
  const {context}=setup();let calls=0;
  context.fetch=async(url)=>{assert.equal(url,'/api/source');calls++;return {ok:true,json:async()=>({markdown:'## Title\n\n- **formatted**',summary:'saved'})};};
  await vm.runInContext("state={history_enabled:true};var body=document.createElement('div');body.isConnected=true;fillMarkdown(body,{event_id:'md',source_hash:'hash',summary:'saved'});hydrateMarkdown(body);",context);
  assert.match(vm.runInContext('body.innerHTML',context),/<h2>Title<\/h2>/);
  assert.match(vm.runInContext('body.innerHTML',context),/<strong>formatted<\/strong>/);
  assert.equal(calls,1);
});

test('Disabled history discards pending Markdown and clears its memory cache', async () => {
  const {context}=setup();let resolve;
  context.fetch=()=>new Promise(r=>{resolve=r;});
  vm.runInContext("state={history_enabled:true};var body=document.createElement('div');body.isConnected=true;fillMarkdown(body,{event_id:'md',summary:'saved'});",context);
  const pending=vm.runInContext('hydrateMarkdown(body)',context);
  await vm.runInContext('state.history_enabled=false;loadCards();',context);
  resolve({ok:true,json:async()=>({markdown:'## Private new text',summary:'saved'})});await pending;
  assert.doesNotMatch(vm.runInContext("body.innerHTML||body.textContent||''",context),/Private/);
  assert.equal(vm.runInContext('markdownCache.size',context),0);
});

test('Non-observer fallback waits for new nodes to attach before hydration', async () => {
  const {context}=setup();let calls=0;
  context.fetch=async()=>{calls++;return {ok:true,json:async()=>({markdown:'## Recovered',summary:'saved'})};};
  vm.runInContext("state={history_enabled:true};var body=document.createElement('div');body.isConnected=false;fillMarkdown(body,{event_id:'late',summary:'saved'});body.isConnected=true;",context);
  await new Promise(setImmediate);
  assert.equal(calls,1);assert.match(vm.runInContext('body.innerHTML',context),/<h2>Recovered<\/h2>/);
});

test('Rendering never guesses list or table boundaries in flattened saved text', () => {
  const {context}=setup();
  context.fixture='计算 7 - 3 + 2 = 6。余额变动 - 5 元。 | Name | Empty | Last | | --- | --- | --- | | A | | B |';
  const html=vm.runInContext('BetweenMarkdown.render(fixture)',context);
  assert.doesNotMatch(html,/<ul>|<ol>|<table>/);
  assert.match(html,/7 - 3 \+ 2 = 6/);assert.match(html,/余额变动 - 5 元/);
  assert.match(html,/\| A \| \| B \|/);
});
