const CATS={all:{label:"전체",icon:"◉"},csr:{label:"기업 사회공헌 사례",icon:"◆"},ngo:{label:"NGO 모금 및 사업사례",icon:"♡"},disaster:{label:"국내외 재해 및 발생상황",icon:"△"},kbs:{label:"KBS 동행 모니터링",icon:"▶"}};
const SUBS={all:"법규 전체",tax_reform:"공익법인 세법개정안",corporate_tax:"공익법인 법인세법",gift_tax:"상속세 및 증여세법",fair_trade:"공정거래법상 공익법인 규제",accounting:"공익법인 회계기준"};
if("scrollRestoration" in history)history.scrollRestoration="manual";
window.scrollTo(0,0);
let all=[],shown=12,lawShown=8,active="all",activeSub="all",activePeriod="1";const $=s=>document.querySelector(s);const esc=s=>String(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));const date=v=>{const d=new Date(v);return isNaN(d)?"날짜 미상":new Intl.DateTimeFormat("ko-KR",{year:"numeric",month:"2-digit",day:"2-digit"}).format(d)};
async function boot(){try{const r=await fetch("data/news.json?"+Date.now(),{cache:"no-store"});if(!r.ok)throw Error(r.status);const d=await r.json();all=d.items||[];$("#updatedAt").textContent=date(d.updated_at)+" "+new Date(d.updated_at).toLocaleTimeString("ko-KR",{hour:"2-digit",minute:"2-digit"});const ai=d.ai_status||{};$("#aiStatus").textContent=ai.analyzed?("AI 분석 "+ai.analyzed+"건 · "+(ai.model||"OpenAI")):"기본 요약 모드";tabs();lawTabs();periodTabs();render();renderLaw()}catch(e){$("#updatedAt").textContent="데이터 확인 필요";$("#newsGrid").innerHTML='<div class="empty"><b>데이터를 불러오지 못했습니다.</b><br>GitHub Actions를 실행해 주세요.</div>';$("#lawGrid").innerHTML='<div class="empty">법규 데이터를 불러오지 못했습니다.</div>';tabs();lawTabs();periodTabs()}}
function tabs(){$("#categoryTabs").innerHTML=Object.entries(CATS).map(([k,v])=>'<button type="button" role="tab" data-cat="'+k+'" class="'+(k===active?"active":"")+'">'+v.icon+" "+v.label+"</button>").join("");$("#categoryTabs").onclick=e=>{const b=e.target.closest("button");if(!b)return;active=b.dataset.cat;shown=12;tabs();render()}}
function lawTabs(){const box=$("#lawSubTabs");box.innerHTML=Object.entries(SUBS).map(([k,v])=>'<button type="button" data-sub="'+k+'" class="'+(k===activeSub?"active":"")+'">'+v+"</button>").join("");box.onclick=e=>{const b=e.target.closest("button");if(!b)return;activeSub=b.dataset.sub;lawShown=8;lawTabs();renderLaw()}}
function periodItems(days){const cut=Date.now()-Number(days)*864e5;return all.filter(n=>n.category!=="law"&&Number.isFinite(new Date(n.published_at).getTime())&&new Date(n.published_at).getTime()>=cut)}
function periodTabs(){const counts={1:periodItems(1).length,7:periodItems(7).length,30:periodItems(30).length};$("#dailyCount").textContent=counts[1]+"건";$("#weeklyCount").textContent=counts[7]+"건";$("#monthlyCount").textContent=counts[30]+"건";document.querySelectorAll(".period-card").forEach(b=>{b.classList.toggle("active",b.dataset.period===activePeriod);b.setAttribute("aria-pressed",b.dataset.period===activePeriod)})}
function filtered(){const q=$("#searchInput").value.trim().toLowerCase(),p=activePeriod;let x=all.filter(n=>n.category!=="law"&&(active==="all"||n.category===active)&&(!q||[n.title,n.summary,n.insight,n.source,...(n.keywords||[]),...(n.trend_tags||[])].join(" ").toLowerCase().includes(q)));const cut=Date.now()-Number(p)*864e5;x=x.filter(n=>Number.isFinite(new Date(n.published_at).getTime())&&new Date(n.published_at).getTime()>=cut);x.sort((a,b)=>$("#sortFilter").value==="priority"?(b.priority||0)-(a.priority||0):new Date(b.published_at)-new Date(a.published_at));return x}
const LAW_STATUS={
 "시행예정":{rank:6,label:"시행 예정"},"입법예고":{rank:5,label:"입법예고"},
 "국회심사":{rank:4,label:"국회 심사"},"개정공포":{rank:3,label:"개정·공포"},
 "현행":{rank:2,label:"현행"},"해설":{rank:1,label:"해설·동향"}
};
function lawStatus(n){
 const explicit=String(n.legal_status||"").replace(/\s/g,"");
 if(LAW_STATUS[explicit])return explicit;
 const t=[n.title,n.summary,n.insight,...(n.trend_tags||[])].join(" ");
 if(/시행\s*예정|시행을?\s*앞|시행일/.test(t))return "시행예정";
 if(/입법\s*예고|행정\s*예고/.test(t))return "입법예고";
 if(/국회|의안|법안|위원회\s*(심사|통과)/.test(t))return "국회심사";
 if(/공포|개정|일부개정|전부개정/.test(t))return "개정공포";
 if(n.official_baseline||/현행/.test(t))return "현행";
 return "해설";
}
function effectiveDate(n){const v=n.effective_date||n.enforcement_date||"";const d=new Date(v);return Number.isFinite(d.getTime())?d:null}
function effectiveOrder(n){
 const d=effectiveDate(n);if(!d)return Number.MAX_SAFE_INTEGER;
 const delta=d.getTime()-Date.now();
 return delta>=0?delta:1e15-d.getTime();
}
function laws(){return all.filter(n=>n.category==="law"&&(activeSub==="all"||n.subcategory===activeSub)).sort((a,b)=>{
 const status=LAW_STATUS[lawStatus(b)].rank-LAW_STATUS[lawStatus(a)].rank;
 if(status)return status;
 const importance=(Number(b.priority)||0)-(Number(a.priority)||0);
 if(importance)return importance;
 const effective=effectiveOrder(a)-effectiveOrder(b);
 if(effective)return effective;
 return new Date(b.published_at)-new Date(a.published_at)
})}
function card(n,law=false){const status=law?lawStatus(n):"";const eff=law?effectiveDate(n):null;const lawMeta=law?'<div class="law-meta"><span class="status status-'+status+'">'+LAW_STATUS[status].label+'</span><span>시행일 '+(eff?date(eff):'원문 확인')+'</span></div>':"";return '<article class="card '+(law?"law-card":"")+'"><div class="card-top"><span class="tag">'+esc(n.subcategory_label||(law?"공익법인 법규":CATS[n.category]?.label||n.category))+'</span><span class="priority">'+((n.priority||0)>=4?"주요 자료":"")+'</span></div>'+lawMeta+'<h3>'+esc(n.title)+'</h3><p>'+esc(n.summary||"원문에서 상세 내용을 확인하세요.")+'</p>'+(n.insight?'<div class="insight"><b>'+(law?"검토 포인트":"AI 시사점")+'</b>'+esc(n.insight)+'</div>':'')+'<div class="keywords">'+[...(n.trend_tags||[]),...(n.keywords||[])].slice(0,4).map(k=>"<span>#"+esc(k)+"</span>").join("")+'</div><div class="card-foot"><span>'+esc(n.source)+" · "+(law&&n.official_baseline?"확인 "+date(n.verified_at||n.published_at):date(n.published_at))+(n.ai_analyzed?" · AI 요약":"")+'</span><a href="'+esc(n.url)+'" target="_blank" rel="noopener noreferrer">원문 보기 →</a></div></article>'}
function render(){const x=filtered(),periodLabel={"1":"일일 동향 · 최근 24시간","7":"주간 동향 · 최근 7일","30":"월간 추세 · 최근 30일"}[activePeriod];$("#resultCount").textContent=x.length+"건";$("#activeLabel").textContent=periodLabel+" · "+CATS[active].label;$("#newsGrid").innerHTML=x.slice(0,shown).map(n=>card(n)).join("")||'<div class="empty">조건에 맞는 소식이 없습니다.</div>';$("#moreButton").hidden=shown>=x.length}
function renderLaw(){const x=laws();$("#lawResultCount").textContent=x.length+"건";$("#lawActiveLabel").textContent=SUBS[activeSub];$("#lawGrid").innerHTML=x.slice(0,lawShown).map(n=>card(n,true)).join("")||'<div class="empty">조건에 맞는 법규 자료가 없습니다.</div>';$("#lawMoreButton").hidden=lawShown>=x.length}
$(".period-monitor").addEventListener("click",e=>{const b=e.target.closest(".period-card");if(!b)return;activePeriod=b.dataset.period;shown=12;periodTabs();render()});$("#searchInput").addEventListener("input",()=>{shown=12;render()});$("#sortFilter").addEventListener("change",render);$("#moreButton").addEventListener("click",()=>{shown+=12;render()});$("#lawMoreButton").addEventListener("click",()=>{lawShown+=8;renderLaw()});boot().finally(()=>requestAnimationFrame(()=>window.scrollTo(0,0)));
