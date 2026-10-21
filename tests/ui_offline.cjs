// Offline DOM regression tests: all data and API responses are in memory; no network.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
let JSDOM;try{({JSDOM}=require('jsdom'));}catch{({JSDOM}=require('../work/dom-test/node_modules/jsdom'));}
const root=path.join(__dirname,'..');const dom=new JSDOM(fs.readFileSync(path.join(root,'web/index.html'),'utf8'),{url:'http://zhixu.test/',runScripts:'outside-only',pretendToBeVisual:true});
const vm=require('node:vm');const run=s=>vm.runInContext(s,dom.getInternalVMContext());const w=dom.window;let entries=[],media=[],calls=[],next=0,settings={font_size:'standard',task_sort:'priority',default_priority:'normal',show_stats:true,show_inspiration:false,hide_completed:false,theme:'#2f6859'};
const date=new Date().toLocaleDateString('en-CA');
w.scrollTo=()=>{};w.HTMLElement.prototype.scrollIntoView=function(){};w.confirm=()=>true;w.document.execCommand=()=>true;w.document.queryCommandState=()=>false;w.document.queryCommandIndeterm=()=>false;w.document.queryCommandValue=()=>'';w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new w.Event('close'));};
Object.defineProperty(w.HTMLElement.prototype,'innerText',{get(){return this.textContent;},set(v){this.textContent=v;},configurable:true});
w.HTMLMediaElement.prototype.pause=()=>{};
const tick=()=>new Promise(r=>setTimeout(r,10));
w.fetch=async(url,options={})=>{const u=new URL(url,'http://zhixu.test'),data=typeof options.body==='string'?JSON.parse(options.body):options.body;calls.push(u.pathname);let result={ok:true};
 if(u.pathname==='/api/info')result={token:'test',data:'test-only',version:'1.3.0'};
 if(u.pathname==='/api/history')result=[];
 if(u.pathname==='/api/library')result={categories:[],albums:[]};
 if(u.pathname==='/api/state')result={settings,categories:[],notifications:[],todos:[],server_date:date};
 if(u.pathname==='/api/storage')result={path:'D:\\test-only'};
 if(u.pathname==='/api/day')result={day:{title:'',body:''},todos:[],attachments:media};
 if(u.pathname==='/api/entries')result={entries:entries.map(x=>({...x})),attachments:media};
 if(u.pathname==='/api/entry/save'){const id=data.id||(++next).toString(16).padStart(32,'0');let row=entries.find(x=>x.id===id);if(!row){row={id,created:new Date().toISOString(),collapsed:0};entries.push(row);}Object.assign(row,data,{id});result={id};}
 if(u.pathname==='/api/entry/fold')entries.find(x=>x.id===data.id).collapsed=data.collapsed;
 if(u.pathname==='/api/upload'){const id=(++next).toString(16).padStart(32,'0');media.push({id,date,name:u.searchParams.get('name'),mime:'image/png',size:4,entry_id:u.searchParams.get('entry'),journal_visible:1,annotation:'',imported_at:new Date().toISOString()});result={id};}
 if(u.pathname==='/api/settings')Object.assign(settings,data);
 if(u.pathname==='/api/media/update')Object.assign(media.find(x=>x.id===data.id),data);
 return {ok:true,json:async()=>result};};
for(const name of ['app.js','v11.js','v12.js','v13.js'])run(fs.readFileSync(path.join(root,'web',name),'utf8'));
(async()=>{await tick();await tick();assert.notEqual(w.document.getElementById('saveState').textContent,'连接失败，请重启知序');assert.ok(w.document.getElementById('dataPath'));assert.equal(w.document.getElementById('pref_density'),null);
 await run('newEntry()');w.document.getElementById('title').value='第一篇';w.document.getElementById('editor').innerHTML='<p>第一篇正文</p>';run('changed()');await run('save()');
 await run('newEntry()');w.document.getElementById('title').value='第二篇';w.document.getElementById('editor').innerHTML='<p>第二篇正文</p>';run('changed()');await run('save()');assert.equal(entries.length,2);
 await run('activateEntry(entryCache[0].id)');assert.equal(w.document.getElementById('title').value,'第一篇');assert.equal(w.document.querySelectorAll('.entry-preview').length,1);
 await run(`upload([new File(['data'],'sample.png',{type:'image/png'})])`);assert.equal(w.document.querySelectorAll('#editor figure img').length,1);assert.equal(entries.length,2);assert.ok(entries[0].body.includes('figure'));
 await run('openInlineMedia(dayMedia[0])');assert.ok(w.document.getElementById('mediaDialog').open);assert.equal(w.document.getElementById('mediaRename').value,'sample');assert.equal(w.document.querySelector('.viewer-meta').open,false);run('zoomMedia(.25)');assert.equal(w.document.querySelector('#mediaPreview img').style.width,'125%');
 w.document.getElementById('mediaDialog').close();await run('showSettings()');await tick();assert.equal(w.document.getElementById('settingsView').hidden,false);assert.ok(w.document.getElementById('storagePath'));assert.equal(w.document.getElementById('storagePath').value,'D:\\test-only');
 console.log('Offline UI checks passed: multi-entry editing, inline upload, viewer zoom, metadata collapse, settings and storage controls.');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>w.close());
