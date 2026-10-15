'use strict';
let bottleProfile=null,bottleCurrent=null,bottleMode='write',bottleBusy=false;
let bottleDraft=new Set(),bottleSeen=[];

function bottleMessage(text,error=false){$('bottle-status').textContent=text;$('bottle-status').className='bottle-status'+(error?' error':'');}
function bottleFieldName(id){return bottleProfile?.fields.find(f=>f.id===id)?.label||id;}
function bottleDate(stamp){return new Date(stamp*1000).toLocaleDateString('zh-CN');}
function bottleSetMode(mode){
  bottleMode=mode;bottleCurrent=null;$('bottle-detail').hidden=true;
  for(const key of ['pick','write','mine']){
    $('bottle-'+key+'-view').hidden=key!==mode;
    if(key!=='write')$('bottle-nav-'+key).setAttribute('aria-pressed',String(key===mode));
  }
  $('bottle-field-label').hidden=mode==='mine';
  $('bottle-inbox-tabs').hidden=mode==='write';
  $('bottle-open').setAttribute('aria-expanded',String(!$('bottle-panel').hidden&&mode==='write'));
  $('bottle-receive').setAttribute('aria-expanded',String(!$('bottle-panel').hidden&&mode!=='write'));
}
async function bottleRun(task){
  if(bottleBusy)return;bottleBusy=true;
  const controls=[...$('bottle-panel').querySelectorAll('button,input,select,textarea')].filter(e=>e.id!=='bottle-close');
  controls.forEach(e=>e.disabled=true);
  try{await task();}catch(error){
    if([403,404,410].includes(error.status)){bottleCurrent=null;$('bottle-detail').hidden=true;}
    bottleMessage(error.message||'漂流瓶暂时无法连接，请稍后再试。',true);
  }
  finally{bottleBusy=false;controls.forEach(e=>e.disabled=false);}
}
function renderBottleProfile(data,mode=bottleMode){
  bottleProfile=data;bottleDraft=new Set(data.interests);
  $('bottle-profile-form').hidden=data.joined||mode!=='write';$('bottle-workbench').hidden=!data.joined;
  $('bottle-profile-cancel').hidden=!data.joined;$('bottle-interest-consent').checked=false;
  $('bottle-field-warning').hidden=!data.joined;$('bottle-withdraw').hidden=!data.joined;
  const fields=$('bottle-fields');fields.replaceChildren();
  for(const field of data.fields){
    const label=element('label','','bottle-field-chip'),input=document.createElement('input');
    input.type='checkbox';input.value=field.id;input.checked=bottleDraft.has(field.id);
    input.onchange=()=>{
      if(input.checked&&bottleDraft.size>=5){input.checked=false;bottleMessage('最多选择 5 个领域。',true);return;}
      if(input.checked)bottleDraft.add(field.id);else bottleDraft.delete(field.id);
    };
    label.append(input,element('span',field.label));fields.append(label);
  }
  const selected=$('bottle-field').value;$('bottle-field').replaceChildren();
  for(const id of data.interests)$('bottle-field').append(new Option(bottleFieldName(id),id));
  if(data.interests.includes(selected))$('bottle-field').value=selected;
  bottleSetMode(mode);
}
function renderBottle(data){
  bottleCurrent=data;$('bottle-detail').hidden=false;
  $('bottle-note-meta').textContent=bottleFieldName(data.field)+' · '+(data.mine?'你投出的瓶子':'来自同领域的参与者')+' · '+bottleDate(data.created);
  $('bottle-note').innerHTML=BetweenMarkdown.render(data.body);
  $('bottle-delete').hidden=!data.mine;
  const replies=$('bottle-replies');replies.replaceChildren();
  if(!data.replies.length)replies.append(element('p','还没有回声。不必急着得到答案。','subtle'));
  for(const reply of data.replies){
    const note=element('article','','bottle-reply'),head=element('div','','bottle-note-head');
    head.append(element('span',(reply.mine?'你的回声':reply.from_author?'瓶主的补充':'同路人的回声')+' · '+bottleDate(reply.created)));
    if(reply.mine){
      const remove=element('button','撤回','quiet');
      remove.onclick=()=>{
        if(!confirm('撤回你写的这条回声？此操作不可恢复。'))return;
        bottleRun(async()=>{await api('bottles/delete-reply',{reply_id:reply.id,confirm:'DELETE'});if(bottleMode==='mine')renderBottleMine(await api('bottles/mine',{}));renderBottle((await api('bottles/read',{bottle_id:data.id})).bottle);bottleMessage('你的这条回声已撤回。');});
      };head.append(remove);
    }
    const body=element('div','','markdown');body.innerHTML=BetweenMarkdown.render(reply.body);note.append(head,body);replies.append(note);
  }
  $('bottle-reply').value='';$('bottle-reply').dataset.requestId='';$('bottle-reply-consent').checked=false;
}
function renderBottleMine(data){
  const root=$('bottle-mine-view');root.replaceChildren();
  if(!data.bottles.length&&!data.replies.length){root.append(element('p','还没有投出的瓶子或回声。','subtle'));return;}
  if(data.bottles.length)root.append(element('h3','投出的瓶子'));
  for(const bottle of data.bottles){
    const card=element('button','','bottle-mine-card');
    card.append(element('span',bottleFieldName(bottle.field)+' · '+bottleDate(bottle.created)),element('p',BetweenMarkdown.plainText(bottle.body).slice(0,160)),element('small',bottle.reply_count+' 条回声 · 打开查看 ↗'));
    card.onclick=()=>bottleRun(async()=>{renderBottle((await api('bottles/read',{bottle_id:bottle.id})).bottle);bottleMessage('回声已更新。');});root.append(card);
  }
  if(data.replies.length)root.append(element('h3','留下的回声'));
  for(const reply of data.replies){
    const card=element('button','','bottle-mine-card');
    card.append(element('span',bottleFieldName(reply.field)+' · '+bottleDate(reply.created)),element('p',BetweenMarkdown.plainText(reply.body).slice(0,160)),element('small','打开原瓶子 · 可撤回自己的回声 ↗'));
    card.onclick=()=>bottleRun(async()=>{renderBottle((await api('bottles/read',{bottle_id:reply.bottle_id})).bottle);bottleMessage('已打开你留下回声的瓶子。');});root.append(card);
  }
}
function bottleConsent(input){if(!$(input).checked)throw new Error('请先明确同意共享，再提交。');}
function bottleRequestId(id){const input=$(id);return input.dataset.requestId||(input.dataset.requestId=crypto.randomUUID());}

function closeBottles(){
  $('bottle-panel').hidden=true;
  $('bottle-open').setAttribute('aria-expanded','false');$('bottle-receive').setAttribute('aria-expanded','false');
}
function openBottles(mode){
  if(bottleBusy)return;
  if(!$('bottle-panel').hidden&&(bottleMode==='write')===(mode==='write')){closeBottles();return;}
  $('bottle-panel').hidden=false;bottleSetMode(mode);bottleMessage('');
  hideInvitation();if(state)rememberOffers(state.sessions);
  bottleRun(async()=>{
    renderBottleProfile(await api('bottles/status'),mode);
    if(mode==='mine'){
      if(bottleProfile.joined)renderBottleMine(await api('bottles/mine',{}));
      else bottleMessage('还没有投出的瓶子或回声。');
    }
  });
}
$('bottle-open').onclick=()=>openBottles('write');
$('bottle-receive').onclick=()=>openBottles('mine');
$('bottle-close').onclick=closeBottles;
$('bottle-profile-form').onsubmit=event=>{
  event.preventDefault();bottleRun(async()=>{
    bottleConsent('bottle-interest-consent');if(!bottleDraft.size)throw new Error('请至少选择一个领域。');
    renderBottleProfile(await api('bottles/profile',{interests:[...bottleDraft],consent:true}),'write');bottleSeen=[];bottleMessage('');
  });
};
$('bottle-manage').onclick=()=>{renderBottleProfile(bottleProfile,'write');$('bottle-profile-form').hidden=false;$('bottle-workbench').hidden=true;};
$('bottle-profile-cancel').onclick=()=>renderBottleProfile(bottleProfile);
$('bottle-withdraw').onclick=()=>{
  if(!confirm('退出漂流瓶，并撤回你共享的全部领域、瓶子和回声？别人在你的瓶子下的回声也会一起移除。原始对话和编年史不受影响。此操作不可恢复。'))return;
  bottleRun(async()=>{renderBottleProfile(await api('bottles/withdraw',{confirm:'WITHDRAW'}));bottleSeen=[];$('bottle-message').value='';$('bottle-note').replaceChildren();$('bottle-replies').replaceChildren();$('bottle-mine-view').replaceChildren();$('bottle-reply').value='';bottleMessage('已退出，全部共享内容已从本机试用池撤回。已打开的页面、截图或备份不在此操作范围内。');});
};
for(const mode of ['pick','mine'])$('bottle-nav-'+mode).onclick=()=>{
  bottleSetMode(mode);bottleMessage('');
  if(mode==='mine')bottleRun(async()=>renderBottleMine(await api('bottles/mine',{})));
};
$('bottle-field').onchange=()=>{bottleSeen=[];bottleCurrent=null;$('bottle-detail').hidden=true;$('bottle-message').dataset.requestId='';bottleMessage('已切换领域。');};
$('bottle-pick').onclick=()=>bottleRun(async()=>{
  const data=await api('bottles/pick',{field:$('bottle-field').value,exclude:bottleSeen});
  if(data.bottle){bottleSeen=[...bottleSeen,data.bottle.id].slice(-100);renderBottle(data.bottle);bottleMessage('');}
  else{bottleCurrent=null;$('bottle-detail').hidden=true;bottleMessage('暂时没有新的同领域漂流瓶。');}
});
$('bottle-write-view').onsubmit=event=>{
  event.preventDefault();bottleRun(async()=>{
    bottleConsent('bottle-message-consent');
    const data=await api('bottles/throw',{field:$('bottle-field').value,body:$('bottle-message').value,consent:true,request_id:bottleRequestId('bottle-message')});
    $('bottle-message').value='';$('bottle-message').dataset.requestId='';$('bottle-message-consent').checked=false;
    bottleSetMode('mine');renderBottleMine(await api('bottles/mine',{}));renderBottle(data.bottle);bottleMessage('已投递。');
  });
};
$('bottle-reply-form').onsubmit=event=>{
  event.preventDefault();bottleRun(async()=>{
    bottleConsent('bottle-reply-consent');if(!bottleCurrent)throw new Error('请先打开一只瓶子。');
    const data=await api('bottles/reply',{bottle_id:bottleCurrent.id,body:$('bottle-reply').value,consent:true,request_id:bottleRequestId('bottle-reply')});
    renderBottle(data.bottle);bottleMessage('回声已送出，谢谢你的善意。');
  });
};
for(const id of ['bottle-message','bottle-reply'])$(id).oninput=()=>{$(id).dataset.requestId='';};
$('bottle-delete').onclick=()=>{
  if(!bottleCurrent||!confirm('撤回这只瓶子及瓶中的全部回声？此操作不可恢复。'))return;
  const id=bottleCurrent.id;bottleRun(async()=>{await api('bottles/delete',{bottle_id:id,confirm:'DELETE'});bottleSetMode('mine');renderBottleMine(await api('bottles/mine',{}));bottleMessage('这只瓶子和其中的回声已撤回。');});
};
