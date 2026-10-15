'use strict';
const $ = (id) => document.getElementById(id);
const fragment = location.hash.slice(1);
if (fragment) { sessionStorage.setItem('awe-key', fragment); history.replaceState(null, '', '/'); }
const token = sessionStorage.getItem('awe-key') || '';
let mode = 'timeline', state = null, inventory = '', signalCursor = null;
let loading = false, invitationTurns = [], invitationNotification = null;
let offered = new Set();
try { offered = new Set(JSON.parse(sessionStorage.getItem('awe-invited') || '[]')); } catch (_) { /* A damaged tab cache must not prevent entry. */ }
let sessionsExpanded = false, sessionInventory = '';
let chronicleData = null, selectedTopic = '', chronicleDomain = '', chronicleKind = '', contentRequest = 0;
let discoveryFields = null, discoveryRequest = 0;
const kinds = {request:'当时的请求', reported_result:'助手自报结果 · 未独立验证', decision:'用户明确选择', open_question:'当时尚未解决'};
const categories = {research:'研究',engineering:'工程',learning:'学习',general:'日常'};
const labels = {IDLE:'等待新任务',WORKING:'Agent 正在工作',WAITING_USER:'Agent 需要你的确认',COMPLETED:'本轮执行已结束',FAILED:'执行中断或失败'};
const duration = (s) => s >= 60 ? `${Math.floor(s/60)} 分 ${Math.floor(s%60)} 秒` : `${Math.floor(s)} 秒`;
const markdownCache=new Map(),markdownJobs=new WeakMap();
const markdownObserver=typeof IntersectionObserver==='undefined'?null:new IntersectionObserver(entries=>{
  for(const entry of entries){
    if(entry.isIntersecting){markdownObserver.unobserve(entry.target);hydrateMarkdown(entry.target);}
    else if(!entry.target.isConnected)markdownObserver.unobserve(entry.target);
  }
},{rootMargin:'160px'});

async function api(path, data) {
  const response = await fetch('/api/' + path, {headers:{Authorization:'Bearer '+token, ...(data ? {'Content-Type':'application/json'} : {})}, method:data ? 'POST' : 'GET', body:data ? JSON.stringify(data) : undefined});
  if (!response.ok) { const body = await response.json(); const error=new Error(body.error || '本地服务不可用');error.status=response.status;throw error; }
  return response.json();
}
function element(tag, text, cls='') { const e=document.createElement(tag); e.textContent=text; if(cls)e.className=cls; return e; }
function fillMarkdown(body,event,{preview=false,heading=null}={}){
  const apply=(text,fallback=false)=>{
    body.setAttribute('aria-busy','false');
    if(preview)body.textContent='“'+BetweenMarkdown.plainText(text).replace(/\s+/g,' ').slice(0,100)+'”';
    else body.innerHTML=BetweenMarkdown.render(text)+(fallback?'<p class="format-note">原始格式不可用，显示已存摘录；不猜测丢失的表格或列表边界。</p>':'');
    if(heading)heading.textContent=BetweenMarkdown.plainText(text).split('\n')[0].slice(0,64);
  };
  if(!event.event_id||!state?.history_enabled)apply(event.summary);
  else{body.textContent='正在还原原文排版…';body.setAttribute('aria-busy','true');if(heading)heading.textContent=BetweenMarkdown.plainText(event.summary).slice(0,64);}
  if(!event.event_id)return;
  markdownJobs.set(body,{event,apply});
  if(markdownObserver)markdownObserver.observe(body);else Promise.resolve().then(()=>hydrateMarkdown(body));
}
async function hydrateMarkdown(body){
  const job=markdownJobs.get(body);if(!job||!state?.history_enabled||!body.isConnected)return;
  const key=job.event.event_id+':'+(job.event.source_hash||'');
  if(!markdownCache.has(key))markdownCache.set(key,api('source',{event_id:job.event.event_id}).then(data=>({text:data.markdown||data.summary,fallback:!data.markdown})));
  try{const data=await markdownCache.get(key);if(state?.history_enabled&&body.isConnected)job.apply(data.text,data.fallback);}
  catch(_){markdownCache.delete(key);if(state?.history_enabled&&body.isConnected)job.apply(job.event.summary,true);}
}
function empty(text) { $('cards').replaceChildren(element('div',text,'empty')); }
const turnKey = (s) => s.id+':'+s.turn_id;
function rememberOffers(sessions) {
  if(sessions.every(s=>offered.has(turnKey(s))))return;
  for(const session of sessions)offered.add(turnKey(session));
  // Keep only a bounded tab-local history, never write chat identifiers to a remote service.
  offered=new Set([...offered].slice(-200));
  try { sessionStorage.setItem('awe-invited',JSON.stringify([...offered])); } catch (_) { /* In-memory deduplication still works without tab storage. */ }
}
function hideInvitation() {
  $('wait-invitation').hidden=true;invitationTurns=[];
  invitationNotification?.close();invitationNotification=null;
}
function enterWaitingSpace() {
  if(state)rememberOffers(state.sessions);hideInvitation();
  $('panel').scrollIntoView({block:'start'});
}
function updateInvitation() {
  const eligible=state?.auto_show?state.sessions.filter(s=>s.panel_due):[];
  if(document.visibilityState!=='hidden'||$('bottle-panel')?.hidden===false){rememberOffers(eligible);hideInvitation();return;}
  invitationTurns=invitationTurns.filter(key=>eligible.some(s=>turnKey(s)===key));
  if(!invitationTurns.length)hideInvitation();
  const fresh=eligible.filter(s=>!offered.has(turnKey(s)));
  if(fresh.length){invitationTurns.push(...fresh.map(turnKey));rememberOffers(fresh);}
  if(!invitationTurns.length)return;
  const firstShow=$('wait-invitation').hidden;
  const sessions=eligible.filter(s=>invitationTurns.includes(turnKey(s)));
  $('wait-invitation-text').textContent=(sessions[0].project_name||(sessions[0].provider==='demo'?'模拟演示（非真实任务）':'Agent'))+(sessions.length>1?` 等 ${sessions.length} 个会话`:'')+' 还在工作。要进来看看吗？';
  $('wait-invitation').hidden=false;
  if(firstShow&&document.visibilityState==='hidden'&&'Notification'in window&&Notification.permission==='granted'){
    try {
      const notification=invitationNotification=new Notification('Between · 等候之间',{body:'Agent 还在工作。点击进入等待空间，也可以忽略。',tag:'between-wait-invitation',silent:true});
      notification.onclick=async()=>{
        if(invitationNotification!==notification||$('wait-invitation').hidden||!state?.auto_show||!state.sessions.some(s=>s.panel_due&&invitationTurns.includes(turnKey(s))))return;
        const turns=[...invitationTurns];
        try {
          // A background tab's last poll may predate completion or an opt-out.
          const latest=await api('state');
          if(invitationNotification!==notification||$('wait-invitation').hidden)return;
          if(!latest.auto_show||!latest.sessions.some(s=>s.panel_due&&turns.includes(turnKey(s)))){hideInvitation();return;}
          state=latest;window.focus();enterWaitingSpace();
        } catch (_) {
          if(invitationNotification===notification){hideInvitation();showError('无法确认当前会话状态，未进入等待空间。你可以稍后手动进入。');}
        }
      };
    } catch (_) { /* The non-modal page invitation remains available. */ }
  }
}
$('wait-enter').onclick=enterWaitingSpace;$('wait-dismiss').onclick=hideInvitation;
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
    if(!state?.history_enabled)return;
    $('source-verified').textContent=data.verified?'✓ 原始记录哈希与摘录一致':'⚠ 原始记录已变化或不可用；下面是导入时保存的摘录';
    $('source-quote').innerHTML=BetweenMarkdown.render(data.markdown||data.summary);
    const dl=$('source-location');dl.replaceChildren();
    for(const [name,value] of [['会话',data.source_provider+' / '+data.source_session_id],['原始位置',(data.source_resolved_path||data.source_path)+':'+data.source_line],['记录 SHA-256',data.source_hash]])dl.append(element('dt',name),element('dd',value));
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
  if(mode==='discovery')loadDiscoveryFields();
  const request=++contentRequest,requestedMode=mode;
  if(!state.history_enabled){
    markdownCache.clear();markdownObserver?.disconnect();
    if($('source-dialog').open)$('source-dialog').close();
    $('source-quote').replaceChildren();$('source-location').replaceChildren();$('source-verified').textContent='';
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
    const params=new URLSearchParams({mode,topic:$('topic').value});
    const events=await api('events?'+params);
    if(request!==contentRequest||mode!==requestedMode)return;
    $('cards').replaceChildren();
    if(!events.length){empty('还没有明确标记为未解决的问题。我们不会把普通提问推断成遗留问题。');return;}
    for(const event of events)$('cards').append(eventCard(event));
  }catch(error){if(request===contentRequest&&mode===requestedMode)showError(error.message);}
}
function eventCard(event) {
  const card=$('card-template').content.firstElementChild.cloneNode(true);
  for(const [selector,text]of[['.card-date',event.date],['.kind',kinds[event.kind]||event.kind],['.category',categories[event.category]||event.category],['.unread',event.read_at?'已读':'未读'],['.provider',event.source_provider.toUpperCase()+' · 原文摘录']])card.querySelector(selector).textContent=text;
  fillMarkdown(card.querySelector('.quote'),event,{heading:card.querySelector('h2')});
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
    const preview=element('p','','book-preview');fillMarkdown(preview,{...topic.preview_event,summary:topic.preview},{preview:true});
    book.append(element('span',topic.domain_label+' / 卷 '+String(data.topics.indexOf(topic)+1).padStart(2,'0'),'book-label'),element('h3',topic.title),element('p',topic.subtitle,'book-subtitle'),preview);
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
    const chapter=element('article','','chapter'),body=element('div','','markdown');fillMarkdown(body,event);chapter.append(element('h3',title),element('small',event.date),body);
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
  const sessions=state.sessions.filter(s=>s.state==='WORKING'&&!s.stale).sort((a,b)=>(b.started||0)-(a.started||0)||a.id.localeCompare(b.id));
  $('session-toggle').textContent=(sessionsExpanded?'收起会话':'展开会话')+' · '+sessions.length+(sessionsExpanded?' ▴':' ▾');
  // Tool/elapsed ticks must not recreate focused links or collapse the list.
  const next=JSON.stringify(sessions.map(s=>[s.id,s.provider,s.project_name,s.state,s.stale]));
  if(next===sessionInventory)return;sessionInventory=next;
  const box=$('session-list');box.replaceChildren();
  box.append(element('p','仅展示正在工作且信号未过期的会话。点击按钮回到本地 ChatGPT，不发送消息或代你授权。','session-hint'));
  if(!sessions.length){box.append(element('p','暂无正在工作的会话。','empty'));return;}
  for(const session of sessions){
    const url=sessionUrl(session),card=element('article','','session');
    const name=session.project_name||(session.provider==='demo'?'模拟演示':'未命名项目');
    const copy=element('div','','session-copy');
    copy.append(element('strong',name+' · '+(labels[session.state]||session.state)),element('small',session.provider.toUpperCase()+' · '+session.id.split(':').slice(1).join(':').slice(0,8)));
    const action=element(url?'a':'button',url?'打开会话 ↗':'暂不支持跳转','session-open');
    if(url){action.setAttribute('href',url);action.setAttribute('aria-label','在 ChatGPT 打开 '+name+' 会话（'+session.id.slice(6,14)+'）');}
    else{action.type='button';action.disabled=true;action.title='仅支持有效的本地 Codex 会话链接。';}
    card.append(copy,action);
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
    $('status-detail').textContent=current?(current.stale?'信号暂未更新，状态不确定':current.provider.toUpperCase()+' · '+current.detail):'连接已就绪，等待空间已展示；完成时轻声提醒。';
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
    updateInvitation();
    for(const signal of state.signals){
      if(signal.state!=='WAITING_USER'||state.sessions.some(s=>s.id===signal.id&&s.turn_id===signal.turn_id&&s.state==='WAITING_USER'))announce(signal);
    }
    signalCursor=state.next_signal;
  }catch(error){showError(error.message+'。若服务重启，请运行 python3 demo/app.py open 重新连接。');}
  finally{loading=false;}
}
function setReadingMode(next) {
  mode=next;
  document.querySelectorAll('.tab').forEach(b=>{const selected=b.dataset.mode===mode;b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));});
  $('discovery-view').hidden=mode!=='discovery';$('chronicles').hidden=mode!=='timeline';$('filters').hidden=mode!=='timeline';
  loadCards();
}
for(const button of document.querySelectorAll('.tab'))button.onclick=()=>setReadingMode(button.dataset.mode);
function loadDiscoveryFields() {
  if(!discoveryFields)discoveryFields=api('discovery/fields').then(fields=>{
    const selected=$('discovery-field').value;
    $('discovery-field').replaceChildren(...fields.map(f=>new Option(f.label,f.id)));
    if(fields.some(f=>f.id===selected))$('discovery-field').value=selected;
  }).catch(()=>{discoveryFields=null;$('discovery-status').textContent='领域列表暂不可用，可以稍后切换页面重试。';});
}
function discoveryLink(text,url) {
  try{const parsed=new URL(url);if(parsed.protocol!=='https:'||parsed.username||parsed.password)return null;}catch(_){return null;}
  const link=element('a',text);link.href=url;link.target='_blank';link.rel='noopener noreferrer';link.referrerPolicy='no-referrer';return link;
}
function renderDiscovery(data) {
  const root=$('discovery-results');root.replaceChildren();
  const kind={paper:'论文',article:'文章',wechat:'公众号'}[data.kind];
  $('discovery-status').textContent=(data.status==='unavailable'?'来源暂不可用或限流，请稍后重试，或前往原站检索。':data.items.length?`找到 ${data.items.length} 条${kind} · 近 ${data.days} 天，按来源日期倒序。`:'公开索引暂无符合时间范围的结果，不代表没有相关内容。')+` 来源：${data.source} · ${data.cached?'缓存获取于':'检索于'} ${new Date(data.fetched_at*1000).toLocaleString('zh-CN')}`+(data.omitted?` · ${data.omitted} 条日期缺失或超出范围，已略过。`:'');
  if(data.kind==='wechat')root.append(element('p','仅收录索引明确标记为微信公众平台的条目；外站检索结果的日期仍需自行核实。','subtle'));
  for(const item of data.items){
    const link=discoveryLink(item.title+' ↗',item.url);if(!link)continue;
    const card=element('article','','discovery-card'),heading=element('h3');heading.append(link);
    card.append(element('p',`${kind} · ${item.source} · ${new Date(item.published).toLocaleDateString('zh-CN')} · ${item.date_label}`,'discovery-meta'),heading);
    if(item.summary)card.append(element('p',item.summary,'discovery-summary'));
    root.append(card);
  }
  const fallback=discoveryLink(data.kind==='wechat'?'去搜狗微信搜索（外站，日期自行核实） ↗':'去原站继续搜索 ↗',data.fallback);
  if(fallback){fallback.className='discovery-external';root.append(fallback);}
}
function resetDiscoveryResults() {
  discoveryRequest++;$('discovery-results').replaceChildren();
  $('discovery-status').textContent='条件已更新。点击搜索后才会发送所选领域与关键词。';
  $('discovery-submit').disabled=false;$('discovery-results').setAttribute('aria-busy','false');
}
$('discovery-form').onsubmit=async event=>{
  event.preventDefault();const request=++discoveryRequest;
  const body={field:$('discovery-field').value,kind:$('discovery-kind').value,days:Number($('discovery-days').value),keyword:$('discovery-keyword').value.trim(),consent:true};
  $('discovery-submit').disabled=true;$('discovery-status').textContent='正在检索公开来源…';$('discovery-results').replaceChildren();$('discovery-results').setAttribute('aria-busy','true');
  try{const data=await api('discovery/search',body);if(request===discoveryRequest)renderDiscovery(data);}
  catch(error){if(request===discoveryRequest)$('discovery-status').textContent=error.message;}
  finally{if(request===discoveryRequest){$('discovery-submit').disabled=false;$('discovery-results').setAttribute('aria-busy','false');}}
};
for(const id of ['discovery-field','discovery-kind','discovery-days'])$(id).onchange=resetDiscoveryResults;
$('discovery-keyword').oninput=resetDiscoveryResults;
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
  const result=await Notification.requestPermission();$('notify-status').textContent=result==='granted'?'已允许：页面在后台时发送可忽略的等待邀请和完成提醒，不自动打开或抢焦点。':'未获授权：仍会显示页内提醒。';
};
poll();setInterval(poll,1000);
