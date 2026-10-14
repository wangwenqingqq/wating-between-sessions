'use strict';
const $ = (id) => document.getElementById(id);
const fragment = location.hash.slice(1);
if (fragment) { sessionStorage.setItem('awe-key', fragment); history.replaceState(null, '', '/'); }
const token = sessionStorage.getItem('awe-key') || '';
let mode = 'timeline', state = null, inventory = '', signalCursor = null;
let dismissed = new Set(), panelClosed = false, loading = false;
const kinds = {request:'当时的请求', reported_result:'助手自报结果 · 未独立验证', decision:'用户明确选择', open_question:'当时尚未解决'};
const categories = {research:'研究',engineering:'工程',learning:'学习',general:'日常'};
const labels = {IDLE:'等待新任务',WORKING:'Agent 正在工作',WAITING_USER:'Agent 需要你的确认',COMPLETED:'本轮执行已结束',FAILED:'执行中断或失败'};
const duration = (s) => s >= 60 ? `${Math.floor(s/60)} 分 ${Math.floor(s%60)} 秒` : `${Math.floor(s)} 秒`;

async function api(path, data) {
  const response = await fetch('/api/' + path, {headers:{Authorization:'Bearer '+token, ...(data ? {'Content-Type':'application/json'} : {})}, method:data ? 'POST' : 'GET', body:data ? JSON.stringify(data) : undefined});
  if (!response.ok) { const body = await response.json(); throw new Error(body.error || '本地服务不可用'); }
  return response.json();
}
function element(tag, text, cls='') { const e=document.createElement(tag); e.textContent=text; if(cls)e.className=cls; return e; }
function empty(text) { $('cards').replaceChildren(element('div',text,'empty')); }
function closePanel() { panelClosed=true; $('panel').hidden=true; $('panel-reopen').hidden=false; if(state)state.sessions.forEach(s=>dismissed.add(s.id+':'+s.turn_id)); }
function openPanel() { panelClosed=false; $('panel').hidden=false; $('panel-reopen').hidden=true; }
$('panel-close').onclick=closePanel; $('panel-reopen').onclick=openPanel;
$('notice-dismiss').onclick=()=>{$('notice').hidden=true;};
for (const dialog of document.querySelectorAll('dialog')) dialog.querySelector('.dialog-close').onclick=()=>dialog.close();
$('settings-open').onclick=()=>$('settings-dialog').showModal();

async function source(event, card) {
  try {
    const data=await api('source',{event_id:event.event_id});
    $('source-verified').textContent=data.verified?'✓ 原始记录哈希与摘录一致':'⚠ 原始记录已变化或不可用；下面是导入时保存的摘录';
    $('source-quote').textContent=data.summary;
    const dl=$('source-location');dl.replaceChildren();
    for(const [name,value] of [['会话',data.source_provider+' / '+data.source_session_id],['原始位置',data.source_path+':'+data.source_line],['记录 SHA-256',data.source_hash]])dl.append(element('dt',name),element('dd',value));
    $('source-dialog').showModal();
    await api('read',{event_id:event.event_id});card.querySelector('.unread').textContent='已读';
  } catch(error) { showError(error.message); }
}
async function loadCards() {
  if(mode==='progress'||!state)return;
  if(!state.history_enabled){empty('历史分析已关闭。你仍可以查看 Progress；需要时在隐私设置中重新启用。');return;}
  try {
    const params=new URLSearchParams({mode,month:$('month').value,topic:$('topic').value});
    const events=await api('events?'+params);
    $('cards').replaceChildren();
    if(!events.length){empty(mode==='discovery'?'还没有明确标记为未解决的问题。我们不会把普通提问推断成遗留问题。':'这个范围里还没有历史卡片。请在本机授权导入历史，或切换月份和主题。');return;}
    for(const event of events){
      const card=$('card-template').content.firstElementChild.cloneNode(true);
      card.querySelector('.card-date').textContent=event.date;
      card.querySelector('.kind').textContent=kinds[event.kind]||event.kind;
      card.querySelector('.category').textContent=categories[event.category]||event.category;
      card.querySelector('.unread').textContent=event.read_at?'已读':'未读';
      card.querySelector('h2').textContent=event.title;
      card.querySelector('.quote').textContent=event.summary;
      card.querySelector('.provider').textContent=event.source_provider.toUpperCase()+' · 原文摘录';
      card.querySelector('.evidence').onclick=()=>source(event,card);
      $('cards').append(card);
    }
  }catch(error){showError(error.message);}
}
function progress() {
  const box=$('progress');box.replaceChildren();
  if(!state.sessions.length){box.append(element('p','暂无生命周期事件。启动带插件的 Agent，或启用只读 Codex 适配器。','empty'));return;}
  for(const session of state.sessions){
    const card=element('article','','session');
    const name=session.project_name||(session.provider==='demo'?'模拟演示':'未命名项目');
    card.append(element('strong',name+' · '+labels[session.state]+' · '+session.provider),element('p',session.stale?'信号超过 15 分钟未更新，状态不确定；不会擅自判断失败。':session.detail),element('small',session.id+' · '+session.event));
    box.append(card);
  }
}
function showError(message){$('connection-error').textContent=message;$('connection-error').hidden=false;}
function announce(session) {
  const text=session.state==='COMPLETED'?'本轮已结束。你可以继续阅读，准备好后回到 Agent。':session.state==='WAITING_USER'?'Agent 需要你的确认，请回到主界面处理。':'执行已中断或失败，请回到 Agent 查看原因。';
  const origin=session.id.startsWith('demo:')?'模拟演示（非真实任务）':session.id.split(':')[0].toUpperCase()+' · '+session.id.split(':').slice(1).join(':').slice(0,8);
  $('notice-text').textContent=origin+'：'+text;$('notice').hidden=false;
  if(session.state!=='WAITING_USER')document.title='✓ 本轮已结束 · Between';
  if(document.visibilityState==='hidden'&&'Notification' in window&&Notification.permission==='granted'){
    try{new Notification('Between · '+origin,{body:text,tag:session.id+':'+session.turn_id});}catch(_){/* In-panel notice remains available when notifications are unsupported. */}
  }
}
async function poll() {
  if(loading)return;loading=true;
  try{
    const next=await api('state'+(signalCursor===null?'':'?after='+signalCursor));state=next;$('connection-error').hidden=true;
    $('auto-show').checked=state.auto_show;$('history-enabled').checked=state.history_enabled;
    const active=state.sessions.filter(s=>['WORKING','WAITING_USER'].includes(s.state));
    const current=active.find(s=>s.state==='WAITING_USER')||active[0]||state.sessions[0];
    $('status-title').textContent=current?(labels[current.state]+(active.length>1?` · ${active.length} 个会话`:'')):'等待你的下一个任务';
    $('status-detail').textContent=current?(current.stale?'信号暂未更新，状态不确定':current.provider.toUpperCase()+' · '+current.detail):'连接已就绪。超过 5 秒的工作会自动展示，不代你授权。';
    $('status-dot').className='status-dot'+(current?.state==='WORKING'?' working':current?.state==='WAITING_USER'?' attention':'');
    $('elapsed').textContent=current&&active.length?duration(current.elapsed):'已就绪';
    if(active.length)document.title=(current.state==='WAITING_USER'?'需要确认':`${active.length} 个会话工作中`)+' · Between';
    $('inventory').textContent=`${state.histories} 段会话 · ${state.events} 个片段`;
    const nextInventory=JSON.stringify([state.events,state.histories,state.history_enabled,state.months]);
    if(nextInventory!==inventory){
      inventory=nextInventory;const selected=$('month').value;
      $('month').replaceChildren(new Option('全部月份',''),...state.months.map(m=>new Option(m,m)));
      if(state.months.includes(selected))$('month').value=selected;
      await loadCards();
    }
    for(const s of state.sessions){
      const key=s.id+':'+s.turn_id;
      if(s.panel_due&&state.auto_show&&!dismissed.has(key)&&panelClosed)openPanel();
    }
    for(const signal of state.signals){
      if(signal.state!=='WAITING_USER'||state.sessions.some(s=>s.id===signal.id&&s.turn_id===signal.turn_id&&s.state==='WAITING_USER'))announce(signal);
    }
    signalCursor=state.next_signal;
    if(mode==='progress')progress();
  }catch(error){showError(error.message+'。若服务重启，请运行 python3 demo/app.py open 重新连接。');}
  finally{loading=false;}
}
for(const button of document.querySelectorAll('.tab'))button.onclick=()=>{
  mode=button.dataset.mode;
  document.querySelectorAll('.tab').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  $('filters').hidden=mode==='progress';$('cards').hidden=mode==='progress';$('progress').hidden=mode!=='progress';
  $('content-hint').textContent=mode==='discovery'?'仅展示当时明确的未解决记录，当前是否解决仍需核实。':'来自原始对话，不替历史补写结论。';
  if(mode==='progress')progress();else loadCards();
};
$('month').onchange=loadCards;$('topic').onchange=loadCards;
for(const [id,key]of[['auto-show','auto_show'],['history-enabled','history_enabled']])$(id).onchange=async()=>{
  try{await api('settings',{[key]:$(id).checked});inventory='';await poll();}catch(error){showError(error.message);}
};
$('delete-history').onclick=async()=>{
  if(!confirm('删除所有本地派生历史并关闭分析？原始会话不会被删除。'))return;
  try{await api('delete-history',{confirm:'DELETE'});inventory='';await poll();}catch(error){showError(error.message);}
};
$('notify-enable').onclick=async()=>{
  if(!('Notification'in window)){$('notify-status').textContent='此浏览器不支持系统通知，仍会显示页内提醒。';return;}
  const result=await Notification.requestPermission();$('notify-status').textContent=result==='granted'?'已允许：页面在后台时发送完成提醒。':'未获授权：仍会显示页内提醒。';
};
poll();setInterval(poll,1000);
