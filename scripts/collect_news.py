#!/usr/bin/env python3
"""Public-interest monitoring collector with optional OpenAI analysis."""
import hashlib, html, json, os, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/news.json"
UA="Mozilla/5.0 (compatible; PublicValueMonitor/2.0; +https://github.com/jeonys-12/welfare-foundation)"
OPENAI_API_KEY=(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_API_KEY") or "").strip()
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5-mini").strip()
KBS_PROGRAM_URL="https://program.kbs.co.kr/1tv/culture/accompany/pc/list.html?smenu=c2cc5a"
KBS_SEARCH_URLS=[
 "https://search.kbs.co.kr/index.html?keyword=%EB%8F%99%ED%96%89",
 "https://search.kbs.co.kr/search?keyword=%EB%8F%99%ED%96%89",
]

SOURCES=[
 # category, subcategory, query, authoritative discovery domains
 ("law","tax_reform","공익법인 세법개정안 OR 세제개편 OR 세법 개정",[ "moef.go.kr","likms.assembly.go.kr","assembly.go.kr"]),
 ("law","corporate_tax","공익법인 법인세법 OR 법인세법 시행령 OR 기부금 세무",[ "law.go.kr","taxlaw.nts.go.kr","nts.go.kr"]),
 ("law","gift_tax","공익법인 상속세 및 증여세법 OR 출연재산 OR 의무지출",[ "law.go.kr","taxlaw.nts.go.kr","nts.go.kr"]),
 ("law","fair_trade","대기업집단 공익법인 공정거래법 OR 공익법인 의결권",[ "ftc.go.kr","law.go.kr"]),
 ("law","accounting","공익법인회계기준 OR 공익법인 결산서류 공시 OR 외부회계감사",[ "law.go.kr","nts.go.kr","kasb.or.kr"]),
 ("csr","csr","기업 사회공헌 사례 ESG 기부 트렌드 사회적가치",[]),
 ("disaster","disaster_kr","국내 재난 발생 산불 홍수 지진 태풍 피해",[ "mois.go.kr","kma.go.kr","nfa.go.kr"]),
 ("disaster","disaster_global","해외 재난 발생 earthquake flood wildfire typhoon humanitarian",[ "reliefweb.int","gdacs.org","unocha.org"]),
 ("ngo","ngo","NGO 모금 캠페인 사업 사례 구호 월드비전 굿네이버스 유니세프",[]),
 ("kbs","kbs_donghaeng",'"KBS 동행" 프로그램 OR "동행" 후원',[ "kbs.co.kr"]),
]
SUB_LABELS={
 "tax_reform":"공익법인 세법개정안","corporate_tax":"공익법인 법인세법",
 "gift_tax":"상속세 및 증여세법","fair_trade":"공정거래법상 공익법인 규제",
 "accounting":"공익법인 회계기준","csr":"기업 사회공헌 사례",
 "disaster_kr":"국내 재해","disaster_global":"해외 재해",
 "ngo":"NGO 모금·사업","kbs_donghaeng":"KBS 동행"
}
KEYS={
 "tax_reform":["공익법인","세법개정","세제개편","세법 개정"],"corporate_tax":["공익법인","법인세법","기부금"],
 "gift_tax":["공익법인","증여세","상속세","출연재산","의무지출"],"fair_trade":["공익법인","공정거래","대기업집단","의결권"],
 "accounting":["공익법인","회계기준","결산서류","공시"],
 "csr":["사회공헌","ESG","기부","사회적 가치","지속가능"],
 "disaster_kr":["재난","산불","홍수","지진","태풍","피해"],
 "disaster_global":["earthquake","flood","wildfire","typhoon","disaster","humanitarian"],
 "ngo":["NGO","모금","캠페인","구호","지원사업"],
 "kbs_donghaeng":["동행","후원"]
}

SOURCE_GUIDES={
 "tax_reform":{"type":"개정안·입법동향","final_source":"기획재정부·국회 의안정보시스템","url":"https://www.moef.go.kr/"},
 "corporate_tax":{"type":"현행법·세무해석","final_source":"국가법령정보센터·국세법령정보시스템","url":"https://taxlaw.nts.go.kr/"},
 "gift_tax":{"type":"현행법·세무해석","final_source":"국가법령정보센터·국세법령정보시스템","url":"https://www.law.go.kr/"},
 "fair_trade":{"type":"규제·정책","final_source":"공정거래위원회·국가법령정보센터","url":"https://www.ftc.go.kr/"},
 "accounting":{"type":"회계기준·공시","final_source":"국세청·국가법령정보센터","url":"https://www.nts.go.kr/"}
}

def clean(s):
 s=html.unescape(re.sub(r"<[^>]+>"," ",s or ""))
 return re.sub(r"\s+"," ",s).strip()

def fetch(url, data=None, headers=None, tries=2, timeout=35):
 hdr={"User-Agent":UA, **(headers or {})}
 for i in range(tries):
  try:
   with urlopen(Request(url,data=data,headers=hdr),timeout=timeout) as r:
    return r.read()
  except Exception:
   if i+1==tries: raise
   time.sleep(1+i)

def google_rss(q):
 return "https://news.google.com/rss/search?q="+quote(q+" when:30d")+"&hl=ko&gl=KR&ceid=KR:ko"

def relevant(cat,sub,text):
 t=text.lower()
 if cat=="law":
  return "공익법인" in text and any(k.lower() in t for k in KEYS[sub][1:])
 if cat=="kbs":
  return "동행" in text and ("kbs" in t or "한국방송" in text)
 return any(k.lower() in t for k in KEYS[sub])

def parse_rss(raw,cat,sub):
 root=ET.fromstring(raw); out=[]
 for e in root.findall(".//item")[:40]:
  title=clean(e.findtext("title")); link=clean(e.findtext("link")); desc=clean(e.findtext("description"))
  source=clean(e.findtext("source")) or urlparse(link).netloc
  combined=title+" "+desc+" "+source
  if not title or not link or not relevant(cat,sub,combined): continue
  pub=clean(e.findtext("pubDate"))
  try: stamp=datetime.strptime(pub,"%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).isoformat()
  except Exception: stamp=datetime.now(timezone.utc).isoformat()
  matched=[k for k in KEYS[sub] if k.lower() in combined.lower()]
  out.append({
   "id":"","category":cat,"subcategory":sub,"subcategory_label":SUB_LABELS[sub],
   "title":title,"summary":desc[:360] or title,"source":source,"url":link,
   "published_at":stamp,"keywords":matched[:4],"priority":min(5,2+len(matched)),
   "ai_analyzed":False,"insight":"","trend_tags":[],"confidence":"원문 확인 필요",
   "source_type":SOURCE_GUIDES.get(sub,{}).get("type","뉴스·기관자료"),
   "final_source":SOURCE_GUIDES.get(sub,{}).get("final_source","원문 제공기관"),
   "verification_url":SOURCE_GUIDES.get(sub,{}).get("url",link)
  })
 return out

def is_official_kbs(url):
 host=urlparse(url).netloc.lower().split(":")[0]
 return host=="kbs.co.kr" or host.endswith(".kbs.co.kr")

def parse_kbs_date(text):
 patterns=[
  (r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})",("%Y","%m","%d")),
  (r"(20\d{2})(\d{2})(\d{2})",("%Y","%m","%d")),
 ]
 for pattern,_ in patterns:
  m=re.search(pattern,text)
  if not m: continue
  try:
   return datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),tzinfo=timezone.utc).isoformat()
  except ValueError: pass
 return ""

def kbs_item(title,url,context,source):
 title=clean(title)
 if not title or not is_official_kbs(url): return None
 episode=re.search(r"(\d{1,4})\s*회",context)
 date=parse_kbs_date(context)
 # 공식 동행 프로그램 페이지에서는 KBS 문구가 없어도 인정한다.
 if "동행" not in title and episode:
  title="동행 "+episode.group(1)+"회 "+title
 if "동행" not in title: return None
 if not date:
  # 날짜가 없는 공식 검색 결과는 수집 시각을 방송일로 오인하지 않도록 제외한다.
  return None
 summary=clean(context)[:360] or title
 return {
  "id":"","category":"kbs","subcategory":"kbs_donghaeng",
  "subcategory_label":SUB_LABELS["kbs_donghaeng"],"title":title,
  "summary":summary,"source":source,"url":url,"published_at":date,
  "keywords":["동행"]+([episode.group(1)+"회"] if episode else []),
  "priority":3,"ai_analyzed":False,"insight":"","trend_tags":[],
  "confidence":"공식 KBS 자료","source_type":"KBS 공식 회차·방송정보",
  "final_source":"KBS","verification_url":url
 }

def parse_kbs_html(raw,page_url,source):
 doc=raw.decode("utf-8","replace")
 out=[]; seen=set()
 # 일반 HTML 링크와 서버 렌더링 결과
 for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',doc,re.I|re.S):
  url=urljoin(page_url,html.unescape(m.group(1)))
  if not is_official_kbs(url): continue
  title=clean(m.group(2))
  context=clean(doc[max(0,m.start()-450):min(len(doc),m.end()+450)])
  item=kbs_item(title,url,context,source)
  if item and item["url"] not in seen:
   seen.add(item["url"]); out.append(item)
 # KBS 페이지의 JSON/스크립트 렌더링 데이터
 for m in re.finditer(r'"(?:title|program_title|episode_title|contents_name)"\s*:\s*"([^"]{2,160})"',doc,re.I):
  title=clean(m.group(1).replace(r"\/","/"))
  context=clean(doc[max(0,m.start()-600):min(len(doc),m.end()+900)])
  um=re.search(r'"(?:url|link_url|contents_url)"\s*:\s*"([^"]+)"',context,re.I)
  if not um: continue
  url=urljoin(page_url,html.unescape(um.group(1).replace(r"\/","/")))
  item=kbs_item(title,url,context,source)
  if item and item["url"] not in seen:
   seen.add(item["url"]); out.append(item)
 return out

def collect_kbs_official():
 out=[]; errors=[]
 targets=[(KBS_PROGRAM_URL,"KBS 동행 공식 프로그램")]
 targets += [(url,"KBS 통합검색") for url in KBS_SEARCH_URLS]
 for url,source in targets:
  try: out+=parse_kbs_html(fetch(url),url,source)
  except Exception as e: errors.append({"source":source,"error":str(e)[:160]})
 return out,errors

def keep_recent_kbs(old_items,days=30):
 cutoff=datetime.now(timezone.utc)-timedelta(days=days)
 kept=[]
 for item in old_items:
  if item.get("category")!="kbs": continue
  try:
   stamp=datetime.fromisoformat(item.get("published_at","").replace("Z","+00:00"))
   if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
  except Exception: continue
  if stamp>=cutoff: kept.append(item)
 return kept

def extract_output_text(response):
 if response.get("output_text"): return response["output_text"]
 for block in response.get("output",[]):
  for part in block.get("content",[]):
   if part.get("type")=="output_text": return part.get("text","")
 return ""

def analyze_with_openai(items):
 if not OPENAI_API_KEY or not items:
  return items, {"enabled":False,"analyzed":0,"message":"OPENAI_API_KEY가 없어 기본 요약을 사용했습니다."}
 candidates=items[:40]
 compact=[{"id":x["id"],"category":x["category"],"subcategory":x["subcategory"],
           "title":x["title"],"source":x["source"],"published_at":x["published_at"],
           "raw_summary":x["summary"][:260]} for x in candidates]
 schema={
  "type":"object","properties":{"items":{"type":"array","items":{"type":"object",
   "properties":{"id":{"type":"string"},"summary":{"type":"string"},"insight":{"type":"string"},
    "trend_tags":{"type":"array","items":{"type":"string"}},"priority":{"type":"integer","minimum":1,"maximum":5},
    "confidence":{"type":"string","enum":["높음","보통","낮음"]}},
   "required":["id","summary","insight","trend_tags","priority","confidence"],"additionalProperties":False}}},
  "required":["items"],"additionalProperties":False}
 prompt=("다음 모니터링 목록을 한국어로 분석하세요. 제공된 제목·요약에 없는 사실은 만들지 마세요. "
         "summary는 2문장 이내의 핵심 요약, insight는 공익법인 또는 사회공헌 실무 관점의 시사점 1문장, "
         "trend_tags는 최대 3개, priority는 업무 중요도 1~5입니다. 정보가 빈약하면 confidence를 낮음으로 표시하세요.\n"
         +json.dumps(compact,ensure_ascii=False))
 body={"model":OPENAI_MODEL,"store":False,"input":prompt,
       "text":{"format":{"type":"json_schema","name":"monitoring_analysis","strict":True,"schema":schema}}}
 raw=fetch("https://api.openai.com/v1/responses",data=json.dumps(body).encode(),
           headers={"Authorization":"Bearer "+OPENAI_API_KEY,"Content-Type":"application/json"},tries=1,timeout=120)
 parsed=json.loads(extract_output_text(json.loads(raw)))
 by_id={x["id"]:x for x in parsed.get("items",[])}
 analyzed=0
 for item in items:
  a=by_id.get(item["id"])
  if not a: continue
  item.update({"summary":a["summary"][:500],"insight":a["insight"][:300],
               "trend_tags":a["trend_tags"][:3],"priority":a["priority"],
               "confidence":a["confidence"],"ai_analyzed":True})
  analyzed+=1
 return items, {"enabled":True,"model":OPENAI_MODEL,"analyzed":analyzed,"message":"OpenAI 분석 완료"}

def main():
 old={"items":[]}; errors=[]; items=[]
 try: old=json.loads(OUT.read_text(encoding="utf-8"))
 except Exception: pass
 for cat,sub,q,domains in SOURCES:
  full=q+(" ("+" OR ".join("site:"+d for d in domains)+")" if domains else "")
  try: items+=parse_rss(fetch(google_rss(full)),cat,sub)
  except Exception as e: errors.append({"source":sub,"error":str(e)[:160]})
 # KBS 공식 프로그램·통합검색은 주 수집원, Google 뉴스는 보조 수집원이다.
 kbs_items,kbs_errors=collect_kbs_official()
 items+=kbs_items
 errors+=kbs_errors
 # 공식 페이지에 새 방송이 없어도 기존 KBS 기록은 방송일 기준 30일간 유지한다.
 items+=keep_recent_kbs(old.get("items",[]),30)
 seen=set(); dedup=[]
 for x in sorted(items,key=lambda z:z["published_at"],reverse=True):
  key=re.sub(r"\W","",x["title"].lower())[:120]
  if key in seen: continue
  seen.add(key)
  x["id"]=hashlib.sha256((x["category"]+"|"+x["subcategory"]+"|"+key).encode()).hexdigest()[:18]
  dedup.append(x)
 if not dedup: dedup=old.get("items",[])
 ai_status={"enabled":False,"analyzed":0,"message":"분석 미실행"}
 try: dedup,ai_status=analyze_with_openai(dedup)
 except Exception as e:
  errors.append({"source":"openai","error":str(e)[:200]})
  ai_status={"enabled":bool(OPENAI_API_KEY),"analyzed":0,"message":"AI 분석 실패 — 기본 요약 유지"}
 payload={"updated_at":datetime.now(timezone.utc).isoformat(),"item_count":len(dedup),
          "errors":errors,"ai_status":ai_status,"source_guides":SOURCE_GUIDES,"items":dedup[:240]}
 OUT.parent.mkdir(exist_ok=True)
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 print(f"collected={len(dedup)} ai={ai_status['analyzed']} errors={len(errors)}")

if __name__=="__main__": main()
