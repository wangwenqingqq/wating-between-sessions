const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

test('Progress prefixes each status with its own project name', () => {
  const nodes = new Map();
  const element = () => ({children: [], append(...items) { this.children.push(...items); }, replaceChildren() { this.children = []; }});
  const document = {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); },
    createElement: element,
    querySelectorAll: () => [],
  };
  const context = vm.createContext({document, location: {hash: ''}, sessionStorage: {getItem: () => ''},
    fetch: () => new Promise(() => {}), setInterval() {}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../demo/ui/web/app.js'), 'utf8'), context);
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
