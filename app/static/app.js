const state={providers:[],usage:[],health:null,setup:null,snippets:null,catalog:null,activeSnippet:'python'};
const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>new Intl.NumberFormat().format(Number(n||0));
const pct=v=>Math.max(0,Math.min(100,Math.round(Number(v||0)*100)));
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});if(!r.ok){let t=await r.text();throw new Error(t||r.statusText)}return r.json()}
function show(view){$$('.view').forEach(v=>v.classList.toggle('active',v.id===view));$$('.nav').forEach(n=>n.classList.toggle('active',n.dataset.view===view));const labels={overview:['Overview','Persistent free capacity, one API.'],setup:['Setup','Connect providers and copy a drop-in client config.'],providers:['Providers','Recurring, promotional, and trial pools.'],playground:['Playground','Test routing without changing your app.'],usage:['Usage & traces','Persistent request ledger and fallback behavior.'],catalog:['Catalog review','Review upstream free-model changes before promotion.']};$('#viewTitle').textContent=labels[view][0];$('#viewSubtitle').textContent=labels[view][1]}
$$('.nav').forEach(n=>n.onclick=()=>show(n.dataset.view));
function stat(label,value,detail=''){return `<div class="stat"><span>${esc(label)}</span><strong>${esc(value)}</strong><div class="sub">${esc(detail)}</div></div>`}
function renderOverview(){const ps=state.providers;const configured=ps.filter(p=>p.configured);const active=configured.filter(p=>p.certification?.state==='active'||p.certification?.state==='unknown');const persistent=configured.filter(p=>p.tier==='persistent_free');const events=state.usage;$('#stats').innerHTML=stat('Configured',configured.length,`${persistent.length} persistent-free`)+stat('Free models',ps.reduce((n,p)=>n+p.models.length,0),'reviewed catalog entries')+stat('Requests / 24h',events.length,`${events.filter(e=>e.success).length} successful`)+stat('Healthy pools',active.length,'available/configured');
$('#capacityList').innerHTML=(configured.length?configured:ps.slice(0,8)).slice(0,10).map(p=>{const h=p.runtime?.headroom??.65;return `<div class="capacity-row"><span>${esc(p.name)}</span><div class="meter"><i style="width:${pct(h)}%"></i></div><b>${pct(h)}%</b></div>`}).join('')||'<div class="sub">Add provider API keys to unlock more capacity.</div>';$('#recentMini').innerHTML=table(events.slice(0,8),false)}
function table(events,withTrace=true){if(!events.length)return '<div class="sub">No requests yet.</div>';return `<table><thead><tr><th>Provider</th><th>Model</th><th>Status</th><th>Latency</th>${withTrace?'<th>Trace</th>':''}</tr></thead><tbody>${events.map(e=>`<tr><td>${esc(e.provider_id)}</td><td>${esc(e.model_id)}</td><td class="${e.success?'ok':'err'}">${e.success?'OK':e.status_code||'ERR'}</td><td>${e.latency_ms?Math.round(e.latency_ms)+' ms':'—'}</td>${withTrace?`<td>${e.request_id?`<button class="trace-link" data-request="${esc(e.request_id)}">${esc(e.request_id.slice(-8))}</button>`:'—'}</td>`:''}</tr>`).join('')}</tbody></table>`}
function setupRequirementRow(provider,req,writable){
  const source=req.source||'missing';
  const status=req.configured?'<span class="badge good">'+esc(source)+'</span>':'<span class="badge warn">missing</span>';
  let control='';
  if(writable&&source!=='environment'){
    if(req.configured){
      control='<button class="ghost setup-remove" data-key="'+esc(req.key)+'">Remove local</button>';
    }else{
      control='<div class="setup-input"><input type="'+(req.secret?'password':'text')+'" autocomplete="off" placeholder="'+esc(req.label)+'" data-setup-input="'+esc(req.key)+'"/><button class="primary setup-save" data-key="'+esc(req.key)+'">Save</button></div>';
    }
  }
  return '<div class="setup-requirement"><div><strong>'+esc(req.label)+'</strong><span>'+esc(req.key)+'</span></div><div class="setup-actions">'+status+control+'</div></div>';
}
function wireSetupActions(){
  $$('.setup-save').forEach(btn=>btn.onclick=async()=>{
    const key=btn.dataset.key;const input=document.querySelector('[data-setup-input="'+CSS.escape(key)+'"]');
    const value=input?.value?.trim();if(!value)return;
    const old=btn.textContent;btn.textContent='Saving…';btn.disabled=true;
    try{await api('/api/setup/value',{method:'POST',body:JSON.stringify({key,value})});if(input)input.value='';await refresh()}
    catch(e){btn.textContent='Failed';setTimeout(()=>btn.textContent=old,1400)}
    finally{btn.disabled=false}
  });
  $$('.setup-remove').forEach(btn=>btn.onclick=async()=>{
    const key=btn.dataset.key;const old=btn.textContent;btn.textContent='Removing…';btn.disabled=true;
    try{await api('/api/setup/value/'+encodeURIComponent(key),{method:'DELETE'});await refresh()}
    catch(e){btn.textContent='Failed';setTimeout(()=>btn.textContent=old,1400)}
    finally{btn.disabled=false}
  });
}
function renderSetup(){
  const s=state.setup||{};const total=Math.max(1,s.providers_total||1);const readiness=Math.round(((s.providers_ready||0)/total)*100);
  $('#setupReadiness').innerHTML='<div class="readiness"><div class="readiness-number">'+readiness+'%</div><div><strong>'+(s.providers_ready||0)+' of '+(s.providers_total||0)+' providers ready</strong><div class="sub">'+(s.persistent_ready||0)+' persistent-free pools · '+(s.no_key_ready||0)+' no-key/optional-key pools</div></div></div><div class="readiness-bar"><i style="width:'+readiness+'%"></i></div><div class="setup-flags"><span class="badge '+(s.transport==='bifrost'?'good':'')+'">transport: '+esc(s.transport||'direct')+'</span><span class="badge '+(s.promo_enabled?'warn':'')+'">promos: '+(s.promo_enabled?'on':'off')+'</span><span class="badge '+(s.trial_enabled?'warn':'')+'">trials: '+(s.trial_enabled?'on':'off')+'</span><span class="badge">'+esc(s.mode||'local-platform')+'</span></div>';
  const providers=s.provider_setup||[];
  const rows=providers.filter(p=>p.requirements?.length||p.no_key_required).map(p=>{
    const reqs=(p.requirements||[]).map(req=>setupRequirementRow(p,req,Boolean(s.writable_setup))).join('');
    const ready=p.ready?'<span class="badge good">ready</span>':'<span class="badge warn">needs setup</span>';
    const noKey=p.no_key_required?'<span class="badge">no key required</span>':'';
    return '<div class="setup-provider"><div class="setup-provider-head"><div><strong>'+esc(p.name)+'</strong><span>'+esc(p.tier)+'</span></div><div class="badges">'+ready+noKey+'</div></div>'+reqs+'<div class="provider-links">'+(p.signup_url?'<a href="'+esc(p.signup_url)+'" target="_blank" rel="noreferrer">Get key</a>':'')+(p.docs_url?'<a href="'+esc(p.docs_url)+'" target="_blank" rel="noreferrer">Docs</a>':'')+'</div></div>';
  });
  $('#setupMissing').innerHTML=rows.join('')||'<div class="success-box">No provider configuration is required.</div>';
  if(!s.writable_setup){
    $('#setupMissing').insertAdjacentHTML('afterbegin','<div class="setup-warning">Browser credential writes are disabled in hosted/Vercel mode. Configure provider keys as deployment environment variables.</div>');
  }
  wireSetupActions();renderSnippet();
}
function renderSnippet(){const code=state.snippets?.snippets?.[state.activeSnippet]||'Loading…';$('#snippetCode').textContent=code;$$('.snippet-tab').forEach(b=>b.classList.toggle('active',b.dataset.snippet===state.activeSnippet))}
function renderProviders(){const q=$('#providerSearch').value.toLowerCase();const tier=$('#tierFilter').value;const rows=state.providers.filter(p=>(tier==='all'||p.tier===tier)&&(`${p.name} ${p.id} ${p.models.map(m=>m.id).join(' ')}`).toLowerCase().includes(q));$('#providerGrid').innerHTML=rows.map(p=>{const cert=p.certification?.state||'unknown';const certClass=cert==='active'?'good':cert==='quarantine'?'bad':cert==='retry_later'?'warn':'';return `<article class="provider-card"><div class="provider-top"><div><h3>${esc(p.name)}</h3><div class="sub">${esc(p.id)}</div></div><div class="sub">${p.configured?'configured':'needs key'}</div></div><div class="badges"><span class="badge ${p.tier==='persistent_free'?'good':'warn'}">${esc(p.tier)}</span><span class="badge ${certClass}">${esc(cert)}</span><span class="badge">${pct(p.runtime?.headroom??0)}% headroom</span></div><div class="models">${p.models.slice(0,5).map(m=>esc(m.label||m.id)).join('<br>')}${p.models.length>5?`<br>+${p.models.length-5} more`:''}</div><div class="provider-links">${p.signup_url?`<a href="${esc(p.signup_url)}" target="_blank" rel="noreferrer">Signup</a>`:''}${p.docs_url?`<a href="${esc(p.docs_url)}" target="_blank" rel="noreferrer">Docs</a>`:''}</div><div class="provider-telemetry">${p.runtime?.provider_quota?.credit_limit_remaining!==undefined?'<span>credit remaining: '+esc(p.runtime.provider_quota.credit_limit_remaining)+'</span>':''}${p.runtime?.provider_quota?.credit_usage_daily!==undefined?'<span>daily credit usage: '+esc(p.runtime.provider_quota.credit_usage_daily)+'</span>':''}</div><div class="actions">${p.id==='openrouter'?'<button class="ghost quota-refresh" data-provider="'+esc(p.id)+'">Refresh quota</button>':''}<button class="ghost certify" data-provider="${esc(p.id)}">Probe</button></div></article>`}).join('');$('.certify').forEach(b=>b.onclick=()=>certify(b.dataset.provider,b));$('.quota-refresh').forEach(b=>b.onclick=()=>refreshQuota(b.dataset.provider,b))
async function refreshQuota(id,btn){
  const old=btn.textContent;btn.textContent='Refreshing…';btn.disabled=true;
  try{await api('/api/providers/'+encodeURIComponent(id)+'/quota/refresh',{method:'POST'});btn.textContent='Updated';await refresh()}
  catch(e){btn.textContent='Unavailable'}
  finally{setTimeout(()=>{btn.textContent=old;btn.disabled=false},1400)}
}
async function certify(id,btn){const old=btn.textContent;btn.textContent='Probing…';btn.disabled=true;try{const r=await api(`/api/providers/${encodeURIComponent(id)}/certify`,{method:'POST'});btn.textContent=r.ok?'Active':r.state;await refresh()}catch(e){btn.textContent='Failed'}finally{setTimeout(()=>{btn.textContent=old;btn.disabled=false},1200)}}
function renderCatalog(){
  const r=state.catalog||{};
  if(!r.available){
    $('#catalogStats').innerHTML=stat('Report','Not generated','run discovery + reconciliation')+stat('Auto promotion','Off','review required')+stat('Source','free-coding-models','safe text parse')+stat('Routing impact','None','until registry edit');
    $('#catalogStatus').textContent=r.message||'No reconciliation report.';
    $('#catalogChanges').innerHTML='<div class="setup-note">Run python scripts/fcm_discovery.py and python scripts/reconcile_fcm.py on the router host to populate this review queue.</div>';
    return;
  }
  const providers=r.providers||{};const changed=Object.entries(providers).filter(([,v])=>(v.candidate_additions?.length||0)+(v.missing_upstream?.length||0)>0);
  $('#catalogStats').innerHTML=stat('New candidates',fmt(r.candidate_additions),'not routable yet')+stat('Missing upstream',fmt(r.missing_upstream),'review for retirement')+stat('Providers changed',changed.length,'need human review')+stat('Auto promotion','Off','safe by design');
  $('#catalogStatus').textContent='Review-only diff. No item shown here can enter free/auto until config/providers.yaml is explicitly updated.';
  $('#catalogChanges').innerHTML=changed.length?changed.map(([id,v])=>{
    const adds=(v.candidate_additions||[]).map(x=>'<span class="catalog-chip add">+ '+esc(x)+'</span>').join('');
    const removes=(v.missing_upstream||[]).map(x=>'<span class="catalog-chip remove">− '+esc(x)+'</span>').join('');
    return '<div class="catalog-provider"><div class="catalog-provider-head"><strong>'+esc(id)+'</strong><span>'+fmt(v.reviewed_count)+' reviewed / '+fmt(v.upstream_count)+' upstream</span></div><div class="catalog-chips">'+adds+removes+'</div></div>';
  }).join(''):'<div class="success-box">Reviewed registry and upstream snapshot are aligned.</div>';
}
function renderUsage(summary){const t=summary.totals||{};$('#usageStats').innerHTML=stat('Requests',fmt(t.requests),'last 24 hours')+stat('Successes',fmt(t.successes),t.requests?`${Math.round((t.successes/t.requests)*100)}% success`:'—')+stat('Tokens',fmt(t.tokens),'reported by providers')+stat('Avg latency',t.avg_latency_ms?`${Math.round(t.avg_latency_ms)} ms`:'—','successful + failed');$('#usageTable').innerHTML=table(state.usage,true);$$('.trace-link').forEach(b=>b.onclick=()=>loadTrace(b.dataset.request))}
async function loadTrace(requestId){$('#traceId').textContent=requestId;$('#traceDetail').innerHTML='<div class="sub">Loading trace…</div>';try{const r=await api(`/api/usage/trace/${encodeURIComponent(requestId)}`);$('#traceDetail').innerHTML=r.events.map((e,i)=>`<div class="trace-step ${e.success?'trace-ok':'trace-fail'}"><div class="trace-index">${i+1}</div><div><strong>${esc(e.provider_id)} / ${esc(e.model_id)}</strong><div class="sub">${e.success?'success':`failed · ${esc(e.status_code||'error')}`} · ${e.latency_ms?Math.round(e.latency_ms)+' ms':'no latency'} · ${fmt(e.total_tokens)} tokens</div>${e.error?`<div class="trace-error">${esc(e.error)}</div>`:''}</div></div>`).join('')}catch(e){$('#traceDetail').innerHTML=`<div class="err">${esc(e.message)}</div>`}}
async function refresh(){try{const [health,p,usage,summary,setup,snippets,catalog]=await Promise.all([api('/health'),api('/api/providers'),api('/api/usage/recent?limit=100'),api('/api/usage/summary?hours=24'),api('/api/setup/status'),api('/api/setup/snippets'),api('/api/catalog/reconciliation')]);state.health=health;state.providers=p.providers;state.usage=usage.events;state.setup=setup;state.snippets=snippets;state.catalog=catalog;$('#healthDot').style.background='#63d9a5';$('#healthLabel').textContent=`${health.configured_providers}/${health.providers} providers configured`;renderOverview();renderSetup();renderProviders();renderUsage(summary);renderCatalog()}catch(e){$('#healthDot').style.background='#ff7b8b';$('#healthLabel').textContent='Router unavailable'}}
$('#providerSearch').oninput=renderProviders;$('#tierFilter').onchange=renderProviders;$('#refreshBtn').onclick=refresh;
$('#baseUrl').textContent=location.origin+'/v1';$('#copyBase').onclick=()=>navigator.clipboard.writeText(location.origin+'/v1');
$$('.snippet-tab').forEach(b=>b.onclick=()=>{state.activeSnippet=b.dataset.snippet;renderSnippet()});$('#copySnippet').onclick=()=>navigator.clipboard.writeText($('#snippetCode').textContent);
function playgroundRequest(){const messages=[];if($('#systemPrompt').value.trim())messages.push({role:'system',content:$('#systemPrompt').value.trim()});messages.push({role:'user',content:$('#userPrompt').value});return {model:$('#playModel').value,messages,stream:false,temperature:Number($('#temperature').value),max_tokens:Number($('#maxTokens').value)}}
$('#previewRoute').onclick=async()=>{const box=$('#routePreview');box.innerHTML='<div class="sub">Scoring candidates…</div>';try{const r=await api('/api/route/preview',{method:'POST',body:JSON.stringify(playgroundRequest())});box.innerHTML=r.candidates.slice(0,6).map((c,i)=>`<div class="route-chip"><div><span>${i+1}. ${esc(c.provider_id)}/${esc(c.model_id)}</span><small>${esc(c.reason)}</small></div><b>${c.score.toFixed(3)}</b></div>`).join('')||'<div class="sub">No eligible candidate. Configure API keys or choose another pool.</div>'}catch(e){box.innerHTML=`<div class="err">${esc(e.message)}</div>`}};
$('#sendPrompt').onclick=async()=>{const out=$('#playOutput'),meta=$('#routeMeta'),btn=$('#sendPrompt');out.textContent='Routing…';meta.textContent='';btn.disabled=true;try{const r=await fetch('/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(playgroundRequest())});const data=await r.json();if(!r.ok)throw new Error(data.detail||JSON.stringify(data));const result=data.choices?.[0]?.message?.content??JSON.stringify(data,null,2);out.textContent=typeof result==='string'?result:JSON.stringify(result,null,2);meta.textContent=`${r.headers.get('x-router-provider')||data.router?.provider} / ${r.headers.get('x-router-model')||data.router?.model} · fallback ${r.headers.get('x-router-fallback-count')||0}`;await refresh();if(data.router?.request_id)loadTrace(data.router.request_id)}catch(e){out.textContent=e.message;meta.textContent='Request failed'}finally{btn.disabled=false}};
refresh();
