'use strict';
const $ = (id) => document.getElementById(id);
const fragment = location.hash.slice(1);
if (fragment) { sessionStorage.setItem('awe-key', fragment); history.replaceState(null, '', '/'); }
const token = sessionStorage.getItem('awe-key') || '';
let mode = 'timeline', state = null, inventory = '', signalCursor = null;
let dismissed = new Set(), panelClosed = false, loading = false;
let sessionsExpanded = false, sessionInventory = '';
let chronicleData = null, selectedTopic = '', chronicleDomain = '', chronicleKind = '', contentRequest = 0;
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
$('session-toggle').onclick=()=>{
  sessionsExpanded=!sessionsExpanded;$('session-list').hidden=!sessionsExpanded;
  $('session-toggle').setAttribute('aria-expanded',String(sessionsExpanded));renderSessions();
};
$('notice-dismiss').onclick=()=>{$('notice').hidden=true;};
for (const dialog of document.querySelectorAll('dialog')) dialog.querySelector('.dialog-close').onclick=()=>dialog.close();
$('settings-open').onclick=()=>$('settings-dialog').showModal();

async function source(event, card=null) {
  try {
    const data=await api('source',{event_id:event.event_id});
    $('source-verified').textContent=data.verified?'✓ 原始记录哈希与摘录一致':'⚠ 原始记录已变化或不可用；下面是导入时保存的摘录';
    $('source-quote').textContent=data.summary;
    const dl=$('source-location');dl.replaceChildren();
    for(const [name,value] of [['会话',data.source_provider+' / '+data.source_session_id],['原始位置',data.source_path+':'+data.source_line],['记录 SHA-256',data.source_hash]])dl.append(element('dt',name),element('dd',value));
    $('source-dialog').showModal();
    await api('read',{event_id:event.event_id});event.read_at=Date.now()/1000;
    const marker=card?.querySelector('.unread');if(marker)marker.textContent='已读';
    if(chronicleData?.selected){
      for(const entry of [...chronicleData.selected.events,...Object.values(chronicleData.selected.chapters)]){
        if(entry?.event_id===event.event_id)entry.read_at=event.read_at;
      }
      if(mode==='timeline')renderChronicles(chronicleData);
    }
  } catch(error) { showError(error.message); }
}
async function loadCards() {
  if(!state)return;
  const request=++contentRequest,requestedMode=mode;
  if(!state.history_enabled){
    chronicleData=null;$('chronicles').replaceChildren();$('cards').replaceChildren();
    const target=mode==='timeline'?$('chronicles'):$('cards');
    target.append(element('div','历史分析已关闭。你仍可以展开上方的会话列表；需要时在隐私设置中重新启用。','empty'));return;
  }
  try {
    if(mode==='timeline'){
      const data=await api('chronicles?'+new URLSearchParams({month:$('month').value,topic:selectedTopic}));
      if(request!==contentRequest||mode!==requestedMode)return;
      chronicleData=data;renderChronicles(data);return;
    }
    const params=new URLSearchParams({mode,month:$('month').value,topic:$('topic').value});
    const events=await api('events?'+params);
    if(request!==contentRequest||mode!==requestedMode)return;
    $('cards').replaceChildren();
    if(!events.length){empty(mode==='discovery'?'还没有明确标记为未解决的问题。我们不会把普通提问推断成遗留问题。':'这个范围里还没有历史卡片。请在本机授权导入历史，或切换月份和主题。');return;}
    for(const event of events)$('cards').append(eventCard(event));
  }catch(error){if(request===contentRequest&&mode===requestedMode)showError(error.message);}
}
function eventCard(event) {
  const card=$('card-template').content.firstElementChild.cloneNode(true);
  for(const [selector,text]of[['.card-date',event.date],['.kind',kinds[event.kind]||event.kind],['.category',categories[event.category]||event.category],['.unread',event.read_at?'已读':'未读'],['h2',event.title],['.quote',event.summary],['.provider',event.source_provider.toUpperCase()+' · 原文摘录']])card.querySelector(selector).textContent=text;
  card.querySelector('.evidence').onclick=()=>source(event,card);return card;
}
async function openChronicle(key) {
  selectedTopic=key;chronicleKind='';await loadCards();$('chronicles').scrollIntoView({block:'start'});
}
function renderChronicles(data) {
  const root=$('chronicles');root.replaceChildren();
  if(data.selected){renderDossier(data.selected,root);return;}
  const heading=element('div','','chronicle-heading');
  heading.append(element('p','PERSONAL CHRONICLES','eyebrow'),element('h2','专题列传'),element('p','把零散对话收进不同的卷，沿着课题回看自己的来路。','subtle'));
  root.append(heading);
  if(!data.stats.events){root.append(element('div','这个月份还没有可归档的片段。可以切换月份，或在本机授权导入历史。','empty'));return;}
  const stats=element('div','','chronicle-stats');
  for(const [value,label]of[[data.stats.topics,'个专题'],[data.stats.sessions,'段会话'],[data.stats.events,'条原文']]){
    const stat=element('div');stat.append(element('strong',String(value)),element('span',label));stats.append(stat);
  }
  stats.append(element('p',data.stats.first_date+' — '+data.stats.last_date,'chronicle-range'));root.append(stats);
  const filters=element('div','','domain-filters');filters.setAttribute('aria-label','专题分类');
  for(const domain of[{id:'',title:'全部专题',count:data.stats.topics},...data.domains]){
    const button=element('button',domain.title+' · '+domain.count,'domain-chip'+(chronicleDomain===domain.id?' active':''));
    button.setAttribute('aria-pressed',String(chronicleDomain===domain.id));button.onclick=()=>{chronicleDomain=domain.id;renderChronicles(chronicleData);};filters.append(button);
  }
  root.append(filters);
  const grid=element('div','','topic-grid');
  const topics=data.topics.filter(t=>!chronicleDomain||t.domain===chronicleDomain);
  if(!topics.length)grid.append(element('p','这个分类在当前月份没有记录。','empty'));
  topics.forEach((topic)=>{
    const book=element('button','','topic-book');book.setAttribute('aria-label','阅读'+topic.title+'列传');
    book.append(element('span',topic.domain_label+' / 卷 '+String(data.topics.indexOf(topic)+1).padStart(2,'0'),'book-label'),element('h3',topic.title),element('p',topic.subtitle,'book-subtitle'),element('p','“'+topic.preview+'”','book-preview'));
    const bottom=element('div','','book-bottom');bottom.append(element('span',topic.count+' 条原文 · '+topic.sessions+' 段会话'),element('span','翻开这一卷 ↗'));
    book.append(element('p',topic.first_date+' — '+topic.last_date,'book-dates'),bottom);book.onclick=()=>openChronicle(topic.id);grid.append(book);
  });
  root.append(grid,element('p','按原文关键词归档；跨专题的记录会交叉收录，总原文数去重计算。分类不是对经历或成果的推断。','chronicle-note'));
}
function renderDossier(topic,root) {
  const back=element('button','← 返回专题书架','quiet dossier-back');back.onclick=()=>openChronicle('');root.append(back);
  const heading=element('div','','dossier-heading');
  heading.append(element('p',topic.domain_label+' / 专题列传','eyebrow'),element('h2',topic.title),element('p',topic.subtitle,'subtle'));root.append(heading);
  if(!topic.events.length){root.append(element('div','当前月份没有这一专题的原文。可以切换月份或返回书架。','empty'));return;}
  root.append(element('p',`现有记录覆盖 ${topic.first_date} 至 ${topic.last_date}，来自 ${topic.sessions} 段会话，共 ${topic.count} 条原文。以下只串联当时的记录，不补写结局。`,'dossier-intro'));
  const chapters=element('div','','chapter-grid');
  for(const[kind,title]of[['request','卷首 · 当时的请求'],['decision','转折 · 明确的选择'],['reported_result','回声 · 助手自报的阶段结果'],['open_question','留白 · 当时尚未解决']]){
    const event=topic.chapters[kind];if(!event)continue;
    const chapter=element('article','','chapter');chapter.append(element('h3',title),element('small',event.date),element('p',event.summary));
    const link=element('button','查看这段原文 ↗','evidence');link.onclick=()=>source(event);chapter.append(link);chapters.append(chapter);
  }
  root.append(chapters,element('p','章节为现有记录的选段。助手自报不等于独立验证；当时未解的问题也可能已在后续会话解决。同日记录按会话与原文行号排列，不代表跨会话先后。','chronicle-note'));
  const filters=element('div','','dossier-filters');
  for(const[kind,title]of[['','全部记录'],['request','当时请求'],['decision','明确选择'],['reported_result','阶段自报'],['open_question','历史未解']]){
    const count=kind?topic.kinds[kind]:topic.count;
    const button=element('button',title+' · '+count,'domain-chip'+(chronicleKind===kind?' active':''));
    button.setAttribute('aria-pressed',String(chronicleKind===kind));button.onclick=()=>{chronicleKind=kind;renderChronicles(chronicleData);};filters.append(button);
  }
  root.append(filters);
  const records=element('div','','dossier-events');let month='';
  for(const event of topic.events.filter(e=>!chronicleKind||e.kind===chronicleKind)){
    if(event.date.slice(0,7)!==month){month=event.date.slice(0,7);records.append(element('h3',month,'dossier-month'));}
    records.append(eventCard(event));
  }
  if(!records.children.length)records.append(element('div','这卷暂时没有这一类记录；没有证据时，我们保留空白。','empty'));
  root.append(records);
}
function sessionUrl(session) {
  const match=session.provider==='codex'&&/^codex:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(session.id);
  return match?'codex://threads/'+match[1]:'';
}
function renderSessions() {
  if(!state)return;
  const priority={WAITING_USER:0,WORKING:1,FAILED:2,COMPLETED:3,IDLE:4};
  const sessions=[...state.sessions].sort((a,b)=>(priority[a.state]??5)-(priority[b.state]??5)||(b.started||0)-(a.started||0)||a.id.localeCompare(b.id));
  $('session-toggle').textContent=(sessionsExpanded?'收起会话':'展开会话')+' · '+sessions.length+(sessionsExpanded?' ▴':' ▾');
  // Tool/elapsed ticks must not recreate focused links or collapse the list.
  const next=JSON.stringify(sessions.map(s=>[s.id,s.provider,s.project_name,s.state,s.stale]));
  if(next===sessionInventory)return;sessionInventory=next;
  const box=$('session-list');box.replaceChildren();
  box.append(element('p','点击会话可回到本地 ChatGPT；只打开会话，不发送消息或代你授权。','session-hint'));
  if(!sessions.length){box.append(element('p','暂无会话信号。启动 Agent 后，会在这里显示。','empty'));return;}
  for(const session of sessions){
    const url=sessionUrl(session),card=element(url?'a':'article','','session'+(url?' session-link':''));
    const name=session.project_name||(session.provider==='demo'?'模拟演示':'未命名项目');
    if(url){card.setAttribute('href',url);card.setAttribute('aria-label','在 ChatGPT 打开 '+name+' 会话（'+session.id.slice(6,14)+'）');}
    const copy=element('div','','session-copy');
    copy.append(element('strong',name+' · '+(labels[session.state]||session.state)),element('small',session.provider.toUpperCase()+' · '+session.id.split(':').slice(1).join(':').slice(0,8)));
    if(session.stale)copy.append(element('p','信号超过 15 分钟未更新，状态不确定。'));
    card.append(copy,element('span',url?'在 ChatGPT 打开 ↗':'仅状态 · 暂不支持跳转','session-action'));
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
    renderSessions();
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
  }catch(error){showError(error.message+'。若服务重启，请运行 python3 demo/app.py open 重新连接。');}
  finally{loading=false;}
}
for(const button of document.querySelectorAll('.tab'))button.onclick=()=>{
  mode=button.dataset.mode;
  document.querySelectorAll('.tab').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));});
  $('cards').hidden=mode!=='discovery';$('chronicles').hidden=mode!=='timeline';$('category-filter').hidden=mode!=='discovery';
  $('content-hint').textContent=mode==='discovery'?'仅展示当时明确的未解决记录，当前是否解决仍需核实。':'以课题为卷，沿着原文回看。';
  loadCards();
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
