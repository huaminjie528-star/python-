'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="agent-token"]').content;
let job = null, stream = null, selected = '', completeFile = false, currentSettings = {}, cards = new Map();
const url = path => `${path}${path.includes('?')?'&':'?'}token=${encodeURIComponent(token)}`;
async function api(path, data) {
  const response = await fetch(url(path), data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Agent-Token':token},body:JSON.stringify(data)});
  const result = await response.json();
  if(!response.ok) throw new Error(result.error || '请求失败');
  return result;
}
function toast(message){$('toast').textContent=message;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',3500);}
function element(tag, className, text){const e=document.createElement(tag);if(className)e.className=className;if(text!==undefined)e.textContent=text;return e;}
function append(e){$('timeline').append(e);$('timeline').scrollTop=$('timeline').scrollHeight;return e;}
function diffPre(text){const p=element('pre');for(const line of text.split('\n')){const c=line.startsWith('+++')||line.startsWith('---')||line.startsWith('@@')?'diff-header':line.startsWith('+')?'diff-add':line.startsWith('-')?'diff-remove':'';p.append(element('span',c,line+'\n'));}return p;}
async function state(){const s=await api('/api/state');currentSettings=s.settings;$('workspace-label').textContent=s.workspace;$('folder').textContent='▾  '+s.workspace.split('/').pop().toUpperCase();$('mode-badge').textContent=s.settings.mode==='live'?'真实模型':'离线验收';$('setting-mode').value=s.settings.mode;$('setting-url').value=s.settings.base_url;$('setting-model').value=s.settings.model;$('setting-key').placeholder=s.has_key?'后端已有 Key，留空保持':'输入 Key（不写入磁盘）';$('setting-mcp').checked=s.settings.mcp_enabled;$('setting-mcp-path').value=s.settings.mcp_config||'';}
async function tree(){const result=await api('/api/tree');$('files').replaceChildren();for(const path of result.files){const b=element('button','file'+(path===selected?' selected':''));b.title=path;b.append(element('span','file-icon',path.endsWith('.py')?'Py':'◇'),document.createTextNode(path));b.onclick=()=>openFile(path).catch(e=>toast(e.message));$('files').append(b);}}
function lineNumbers(){const count=$('editor').value.split('\n').length;$('line-numbers').textContent=Array.from({length:count},(_,i)=>i+1).join('\n');}
async function openFile(path){const result=await api('/api/file?path='+encodeURIComponent(path));selected=path;$('filename').textContent=path.split('/').pop();$('breadcrumb').textContent=path;$('welcome').hidden=true;
 if(result.content){$('code-area').hidden=true;$('image-area').hidden=false;$('image-area').replaceChildren();for(const b of result.content){const img=element('img');img.src=`data:${b.mimeType};base64,${b.data}`;$('image-area').append(img);}completeFile=false;}
 else{$('code-area').hidden=false;$('image-area').hidden=true;$('editor').value=result.text.split('\n').map(l=>l.replace(/^\s*\d+ \| /,'')).join('\n')+(result.final_newline?'\n':'');completeFile=result.remaining_lines===0 && !result.shortened_lines;$('editor').readOnly=!completeFile;$('file-meta').textContent=result.total_lines+' 行'+(!completeFile?' · 分页预览，只读':'');lineNumbers();}
 $('save-file').disabled=!completeFile;await tree();}
function busy(value){$('send').disabled=value;$('stop').disabled=!value;$('save-file').disabled=value||!completeFile;$('choose-workspace').disabled=value;}
function event(e){
 if(e.type==='task')append(element('div','event user-message',e.task));
 if(e.type==='message') {const d=element('div','event assistant-text');d.append(element('span','event-label','LITTLE CURSOR'),document.createTextNode(e.text));append(d);}
 if(e.type==='status')append(element('div','status-event',e.text));
 if(e.type==='step')$('run-status').textContent=`正在执行 · 第 ${e.step} 步`;
 if(e.type==='mcp'){$('mcp-status').textContent='● MCP 已连接 · '+e.servers.join(', ');append(element('div','status-event','MCP · '+e.tools.join(', ')));}
 if(e.type==='tool_start'){const d=element('details','tool-event');d.open=true;const s=element('summary',null,e.name);s.append(element('span','tool-tag',e.name.startsWith('mcp__')?'外部 MCP':'内置工具'));d.append(s,element('pre',null,e.arguments));cards.set(e.id,d);append(d);}
 if(e.type==='tool_result'){const d=cards.get(e.id);if(d){if(!e.ok)d.classList.add('failed');d.querySelector('summary').firstChild.textContent=(e.ok?'✓ ':'✕ ')+e.name;const r=e.result||{};if(r.diff)d.append(diffPre(r.diff));if(r.content&&r.content.some(b=>b.type==='image')){for(const b of r.content){if(b.type==='image'){const img=element('img','tool-image');img.src=`data:${b.mimeType};base64,${b.data}`;d.append(img);}}}else{const copy={...r};delete copy.diff;d.append(element('pre',null,(e.error?e.error+'\n':'')+JSON.stringify(copy,null,2)));}if(e.ok&&r.diff&&selected===r.path)openFile(selected).catch(()=>{});}}
 if(e.type==='approval'){const d=element('div','approval');d.id='approval-'+e.approval_id;d.append(element('h3',null,e.kind==='change'?'等待批准修改 · '+e.path:'等待批准命令'));d.append(e.diff!==undefined?diffPre(e.diff):element('pre',null,e.command));const buttons=element('div','approval-buttons');for(const [label,allow] of [['批准执行',true],['拒绝',false]]){const b=element('button',allow?'approve-yes':'',label);b.onclick=async()=>{try{await api('/api/approve',{job,approval_id:e.approval_id,allow});for(const x of buttons.children)x.disabled=true;}catch(err){toast(err.message);}};buttons.append(b);}d.append(buttons);append(d);$('run-status').textContent='等待你的确认';}
 if(e.type==='approval_resolved'){const d=$('approval-'+e.approval_id);if(d){const b=d.querySelector('.approval-buttons');b.replaceChildren(element('span','status-event',e.allow?'已批准':'已拒绝 / 已中断'));}}
 if(e.type==='error')append(element('div','event error',e.text));
 if(e.type==='done'){$('run-status').textContent=e.text;busy(false);if(stream)stream.close();job=null;tree().catch(()=>{});if(selected)openFile(selected).catch(()=>{});}
}
async function send(){if(job)return;const task=$('prompt').value.trim();if(!task)return;try{busy(true);const intro=document.querySelector('.intro');if(intro)intro.remove();const r=await api('/api/task',{task});job=r.job;$('prompt').value='';stream=new EventSource(url('/api/events?job='+job));stream.onmessage=m=>event(JSON.parse(m.data));stream.onerror=()=>{if(job){$('run-status').textContent='连接中断，正在重连…';}};}catch(e){busy(false);toast(e.message);}}
$('send').onclick=send;$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}};
for(const b of document.querySelectorAll('[data-task]'))b.onclick=()=>{$('prompt').value=b.dataset.task;send();};
$('stop').onclick=async()=>{if(job){await api('/api/cancel',{job});$('run-status').textContent='正在停止工具…';}};
$('refresh').onclick=()=>tree().catch(e=>toast(e.message));
$('new-chat').onclick=async()=>{try{await api('/api/new',{});$('timeline').replaceChildren();cards.clear();toast('已开始新会话');}catch(e){toast(e.message);}};
$('save-file').onclick=async()=>{try{await api('/api/save',{path:selected,content:$('editor').value});toast('已保存');await openFile(selected);}catch(e){toast(e.message);}};
$('editor').oninput=lineNumbers;$('editor').onscroll=()=>{$('line-numbers').style.transform=`translateY(-${$('editor').scrollTop}px)`;};
$('editor').onclick=$('editor').onkeyup=()=>{const t=$('editor'),before=t.value.slice(0,t.selectionStart),lines=before.split('\n');$('cursor-position').textContent=`Ln ${lines.length}, Col ${lines.at(-1).length+1}`;};
$('settings-open').onclick=async()=>{await state();$('settings').showModal();};$('settings-close').onclick=()=>$('settings').close();
$('settings-form').onsubmit=async e=>{e.preventDefault();try{const values={mode:$('setting-mode').value,base_url:$('setting-url').value,model:$('setting-model').value,mcp_enabled:$('setting-mcp').checked,mcp_config:$('setting-mcp-path').value};if($('setting-key').value)values.api_key=$('setting-key').value;if(values.mode==='live'&&!values.model)throw new Error('请填写模型名称');await api('/api/settings',values);$('setting-key').value='';await state();$('settings').close();toast('配置已保存');}catch(err){$('settings-message').textContent=err.message;}};
$('choose-workspace').onclick=async()=>{try{if(!window.pywebview){toast('请在桌面应用中使用系统文件夹选择器');return;}const result=await window.pywebview.api.choose_workspace();if(result.error)throw new Error(result.error);selected='';await state();await tree();$('welcome').hidden=false;$('code-area').hidden=true;$('image-area').hidden=true;$('filename').textContent='欢迎';}catch(e){toast(e.message);}};
Promise.all([state(),tree()]).catch(e=>toast(e.message));
