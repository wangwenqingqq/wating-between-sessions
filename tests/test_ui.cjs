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
  const context = vm.createContext({document, location: {hash: ''}, sessionStorage: {getItem: () => ''},
    fetch: () => new Promise(() => {}), setInterval() {}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../demo/ui/web/app.js'), 'utf8'), context);
  return {nodes,context};
}

test('Progress prefixes each status with its own project name', () => {
  const {nodes,context}=setup();
  vm.runInContext(`state = {sessions: [
    {project_name: 'Alpha', state: 'COMPLETED', provider: 'codex'},
    {project_name: 'Beta', state: 'WORKING', provider: 'claude'},
    {state: 'COMPLETED', provider: 'codex'},
    {state: 'COMPLETED', provider: 'demo'}
  ]}; progress();`, context);
  assert.deepEqual(nodes.get('progress').children.map(card => card.children[0].textContent), [
    'Alpha · 本轮执行已结束 · codex', 'Beta · Agent 正在工作 · claude',
    '未命名项目 · 本轮执行已结束 · codex', '模拟演示 · 本轮执行已结束 · demo',
  ]);
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
  await vm.runInContext(`chronicleData={selected:{title:'GTS',domain_label:'研究',subtitle:'选段',sessions:1,count:1,kinds:{request:1},
    events:[{event_id:'read-me',kind:'request',source_provider:'codex',date:'2026-10-12',read_at:0}],
    chapters:{request:{event_id:'read-me',read_at:0}}}};
    source(chronicleData.selected.chapters.request);`,context);
  const root=nodes.get('chronicles');
  root.children.find(e=>e.className==='dossier-filters').children[1].onclick();
  const card=root.children.find(e=>e.className==='dossier-events').children.find(e=>e.className==='card');
  assert.equal(card.querySelector('.unread').textContent,'已读');
  assert.equal(vm.runInContext('chronicleData.selected.chapters.request.read_at>0',context),true);
});
