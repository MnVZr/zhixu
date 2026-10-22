'use strict';
// A single compact strip gives the remaining dialog area to the image/video.
pathsV12.trash='M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6';
pathsV12.download='M12 3v12M7 10l5 5 5-5M4 17v4h16v-4';
pathsV12.fit='M3 9V3h6M15 3h6v6M21 15v6h-6M9 21H3v-6';
pathsV12.addNote='M4 3h16v14H9l-5 4zM8 8h8M12 5v6';
const viewerBar15=element('div','viewer-bar15');viewer.insertBefore(viewerBar15,viewer.firstChild);viewerBar15.append($('mediaTitle'),info145,viewerTools,$('closeMedia'));
viewer.querySelector('.media-dialog-head').hidden=true;
const fit15=viewerTools.querySelectorAll('button')[1];fit15.replaceChildren(iconV12('fit'));fit15.title='适应窗口';fit15.setAttribute('aria-label',fit15.title);
for(const [control,name,label] of [[addNote145,'addNote','添加图注'],[source145,'note','查看对应日志'],[cover145,'album','设为相册封面'],[$('downloadMedia'),'download','下载原文件'],[$('removeMedia'),'trash','从此相册移除']]){control.replaceChildren(iconV12(name));control.title=label;control.setAttribute('aria-label',label);}
const compactViewerPrevious15=showViewerItem;showViewerItem=function(item){compactViewerPrevious15(item);info145.title=info145.textContent;const date=String(item.imported_at||item.date||'').slice(0,10);info145.textContent=(date||'日期未知')+' · '+(mediaViewerIndex+1)+'/'+mediaViewerItems.length;notesVisible145=true;drawCaption14();updateCaptionButton14();};
// Line icons change with the selected mood/weather and always stay visible.
const moodPaths15={
 '开心':'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M8 9h.01M16 9h.01M8 14s1 3 4 3 4-3 4-3',
 '平静':'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M7 9h3M14 9h3M9 15h6',
 '一般':'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M8 9h.01M16 9h.01M8 15h8',
 '低落':'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M8 9h.01M16 9h.01M8 17s1-3 4-3 4 3 4 3M17 11l-1 2a1 1 0 0 0 2 0z',
 '疲惫':'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M7 10l3 1M17 10l-3 1M10 16h4'};
const weatherPaths15={
 '晴':'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2',
 '多云':'M8 5V3M3 8H1M4 4 2 2M14 5l2-2M5 12a4 4 0 1 1 7-5M6 20h12a4 4 0 0 0 0-8 5 5 0 0 0-9-2 5 5 0 0 0-3 10',
 '阴':'M5 19h13a4 4 0 0 0 0-8 6 6 0 0 0-11-2 5 5 0 0 0-2 10',
 '雨':'M5 15h13a3 3 0 0 0 0-6 6 6 0 0 0-11-2 4 4 0 0 0-2 8M7 18l-1 3M12 18l-1 3M17 18l-1 3',
 '雪':'M5 14h13a3 3 0 0 0 0-6 6 6 0 0 0-11-2 4 4 0 0 0-2 8M7 18v4M5 20h4M16 18v4M14 20h4',
 '风':'M3 8h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 17h7a2 2 0 1 1-2 2'};
drawContext145=function(){for(const [key,b] of Object.entries(contextButtons145)){b.hidden=false;const value=context145[key]||'';const svg=b.querySelector('svg');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.8');svg.querySelector('path').setAttribute('d',key==='mood'?(moodPaths15[value]||moodPaths15['一般']):(weatherPaths15[value]||weatherPaths15['多云']));b.lastElementChild.textContent=value||(key==='mood'?'心情':'天气');b.title='记录当日'+(key==='mood'?'心情':'天气');}};
drawContext145();
// Journal deletion keeps source files and album membership, with an undo action.
let pendingDelete15=null,lastDelete15=null;
const deleteDialog15=element('dialog','delete-dialog15');deleteDialog15.innerHTML='<h2>删除这篇日志？</h2><p id="deleteEntryName15"></p><p class="subtle">已加入相册的图片、视频会保留。删除后可撤销。</p><div class="dialog-actions"><button id="cancelDelete15" class="secondary">取消</button><button id="confirmDelete15" class="danger">删除日志</button></div>';document.body.append(deleteDialog15);
async function requestDelete15(id){await save();const entry=entryCache.find(e=>e.id===id);if(!entry)return;pendingDelete15={id,date:entry.date};$('deleteEntryName15').textContent=entry.title||'未命名日志';deleteDialog15.showModal();}
const undo15=button('撤销删除','secondary',async()=>{if(!lastDelete15)return;const result=await api('/api/entry/restore',{id:lastDelete15.id});lastDelete15=null;undo15.hidden=true;await switchDay(result.date,result.id);await loadHistory();toast('日志已恢复');});undo15.id='undoEntryDelete15';undo15.hidden=true;entryBar.append(undo15);
$('cancelDelete15').onclick=()=>{pendingDelete15=null;deleteDialog15.close();};$('confirmDelete15').onclick=async()=>{const entry=pendingDelete15;if(!entry)return;const b=$('confirmDelete15');b.disabled=true;try{await api('/api/entry/delete',{id:entry.id});lastDelete15=entry;pendingDelete15=null;dirty=false;entryCache=entryCache.filter(x=>x.id!==entry.id);if(activeEntryId===entry.id){activeEntryId='';setActiveEntry(null);}deleteDialog15.close();await switchDay(entry.date);await loadHistory();undo15.hidden=false;toast('日志已删除，可撤销');}catch(e){report(e);}finally{b.disabled=false;}};
const deleteActive15=button('删除','danger entry-delete15',()=>requestDelete15(activeEntryId));deleteActive15.title='删除当前日志';journalCard.querySelector('.card-header').append(deleteActive15);
const renderStackPrevious15=renderEntryStack;renderEntryStack=function(){renderStackPrevious15();deleteActive15.hidden=!activeEntryId;for(const card of entryStack.querySelectorAll('.entry-preview')){const b=button('删除','danger entry-delete15',()=>requestDelete15(card.dataset.entryId));b.title='删除这篇日志';card.querySelector('.entry-preview-head').append(b);}};
// Dismissible, remembered first-launch guide; available again from Settings.
const guide15=element('dialog','welcome-guide15');guide15.id='welcomeGuide15';guide15.innerHTML='<div class="guide-head15"><h2>欢迎使用知序</h2><button id="closeGuide15" class="secondary" aria-label="关闭新手指南">×</button></div><p class="subtle">让生活更有序，从一条记录开始。</p><div id="guideCards15"></div><label class="checkbox-line"><input type="checkbox" id="guideShortcut15" checked> 创建桌面快捷方式</label><p id="guideError15" role="alert"></p><div class="dialog-actions"><button id="skipGuide15" class="secondary">关闭指南</button><button id="finishGuide15" class="primary">开始记录</button></div>';document.body.append(guide15);
for(const [icon,title,text] of [['note','图文日志','选日期，新建日志；可插入图片或视频。自动保存，一天可写多篇，支持折叠与删除。'],['check','每日待办','填写事项，按需设置时段、提醒与番茄钟；用颜色区分优先级。'],['album','相册与图注','照片视频可分类收藏，双击日志插图查看大图；在图上点击添加图注，可跳回来源日志。'],['info','番茄钟与当天状态','点击右下角闹钟设置专注与休息，整个图标可拖动。点击统计栏的心情或天气图标记录当天状态。'],['settings','你的本地资料','设置中更改主题、保存位置。更新前备份全部数据，新版可读取旧目录或恢复备份。']]){const card=element('section','guide-card15');card.append(iconV12(icon));const textBox=element('div');textBox.append(element('h3','',title),element('p','',text));card.append(textBox);$('guideCards15').append(card);}
let guideFirst15=false;
function openGuide15(first=false){guideFirst15=first;$('guideShortcut15').checked=first;$('guideError15').textContent='';guide15.showModal();}
async function finishGuide15(create=false){const buttons=[...guide15.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);try{if(create&&$('guideShortcut15').checked)await api('/api/desktop-shortcut',{});if(guideFirst15)await api('/api/welcome',{completed:true});guide15.close();}catch(e){$('guideError15').textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}}
$('finishGuide15').onclick=()=>finishGuide15(true);$('skipGuide15').onclick=()=>finishGuide15(false);$('closeGuide15').onclick=()=>finishGuide15(false);guide15.addEventListener('cancel',e=>{e.preventDefault();finishGuide15(false);});
const guideOpen15=button('新手指南','secondary',()=>guardSettingsLeave135(()=>openGuide15()));const shortcut15=button('创建桌面快捷方式','secondary',async()=>{await api('/api/desktop-shortcut',{});toast('桌面快捷方式已创建');});$('settingsView').querySelector('.app-info').append(guideOpen15,shortcut15);
let guideChecked15=false;const guideInit15=setInterval(async()=>{if(!token||guideChecked15)return;guideChecked15=true;clearInterval(guideInit15);try{const s=await api('/api/welcome');if(!s.completed)openGuide15(true);}catch(e){report(e);}},500);

const renderMediaPrevious15=renderMedia;renderMedia=function(){renderMediaPrevious15();for(const card of $('mediaGrid').querySelectorAll('.media-card')){const info=card.querySelector('.media-info'),extra=element('div','media-extra15');extra.setAttribute('role','tooltip');for(const child of [...info.children])if(child.tagName!=='STRONG')extra.append(child);info.append(extra);}};
