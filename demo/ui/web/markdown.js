'use strict';
const BetweenMarkdown = (() => {
  const md=markdownit({html:false,linkify:false,typographer:false});
  md.validateLink=(value)=>{
    if(/^codex:\/\/threads\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value))return true;
    try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password;}catch(_){return false;}
  };
  // Never load history-controlled images, tracking pixels, or embedded HTML.
  md.renderer.rules.image=(tokens,index)=>md.utils.escapeHtml(tokens[index].content);
  const linkOpen=md.renderer.rules.link_open||((tokens,index,options,env,self)=>self.renderToken(tokens,index,options));
  md.renderer.rules.link_open=(tokens,index,options,env,self)=>{
    tokens[index].attrSet('rel','noopener noreferrer');
    if(/^https?:/i.test(tokens[index].attrGet('href')))tokens[index].attrSet('target','_blank');
    return linkOpen(tokens,index,options,env,self);
  };
  md.renderer.rules.table_open=()=>'<div class="markdown-table" tabindex="0" role="region" aria-label="表格"><table>\n';
  md.renderer.rules.table_close=()=>'</table></div>\n';
  function inlineText(tokens){return tokens.map(t=>t.children?inlineText(t.children):(['softbreak','hardbreak'].includes(t.type)?' ':t.content||'')).join('');}
  return Object.freeze({
    render:(text)=>md.render(String(text||'')),
    plainText:(text)=>md.parse(String(text||''),{}).map(t=>t.type==='inline'?inlineText(t.children):(['fence','code_block'].includes(t.type)?t.content:'')).filter(Boolean).join('\n').trim(),
  });
})();
