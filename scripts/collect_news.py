#!/usr/bin/env python3
"""Public-interest monitoring collector with optional OpenAI analysis."""
import hashlib, html, json, os, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/news.json"
UA="Mozilla/5.0 (compatible; PublicValueMonitor/2.0; +https://github.com/jeonys-12/welfare-foundation)"
OPENAI_API_KEY=(os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_API_KEY") or "").strip()
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5-mini").strip()
KBS_PROGRAM_URL="https://program.kbs.co.kr/1tv/culture/accompany/pc/list.html?smenu=c2cc5a"
KBS_SEARCH_URLS=[
 "https://www.kbs.co.kr/m/search/main.html?keyword=%EB%8F%99%ED%96%89",
 "https://www.kbs.co.kr/m/search/replay.html?keyword=%EB%8F%99%ED%96%89",
]
DISASTER_DAYS=30
NGO_DAYS=30
MAX_RESPONSE_BYTES=5*1024*1024
MAX_PAGE_LINKS=300
NGO_KEYWORDS=[
 "NGO","비정부기구","모금","후원","후원금","기부","기부금","나눔","캠페인","구호",
 "긴급구호","긴급지원","인도적 지원","지원사업","아동지원","취약계층","국제개발협력",
 "현지사업","봉사","배분사업","공모사업","사업성과","후원자","정기후원"
]
NGO_SOURCES=[
 {"name":"월드비전","domains":["worldvision.or.kr"],"pages":["https://www.worldvision.or.kr/informationCenter/story"]},
 {"name":"굿네이버스","domains":["goodneighbors.kr"],"pages":["https://www.goodneighbors.kr/story/gnnews"]},
 {"name":"유니세프한국위원회","domains":["unicef.or.kr"],"pages":["https://www.unicef.or.kr/what-we-do/news/"]},
 {"name":"대한적십자사","domains":["redcross.or.kr"],"pages":["https://www.redcross.or.kr/news/news_press.do"]},
 {"name":"세이브더칠드런","domains":["sc.or.kr"],"pages":["https://www.sc.or.kr/news/noticeList.do"]},
 {"name":"초록우산","domains":["childfund.or.kr"],"pages":["https://www.childfund.or.kr/news/pressList.do"]},
]
KR_DISASTER_KEYWORDS=[
 "재난","재해","산불","화재","홍수","침수","범람","지진","태풍","호우","집중호우",
 "산사태","폭염","대설","한파","강풍","붕괴","폭발","대피","인명피해",
 "비상대응","중앙재난안전대책본부","중대본","특보"
]
GLOBAL_DISASTER_KEYWORDS=[
 "earthquake","flood","wildfire","typhoon","disaster","humanitarian","cyclone",
 "hurricane","landslide","heatwave","tsunami","volcanic eruption","eruption",
 "storm","drought","casualties","evacuation","emergency","tropical depression"
]
KR_OFFICIAL_PAGES=[
 ("행정안전부","https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardList.do?bbsId=BBSMSTR_000000000336"),
 ("기상청","https://www.weather.go.kr/w/eqk-vol/recent-eqk.do"),
 ("소방청","https://www.nfa.go.kr/nfa/news/pressrelease/press/?boardId=bbs_0000000000000010&mode=list"),
]
GDACS_RSS_URL="https://www.gdacs.org/xml/rss.xml"
GDACS_MIN_SCORE=1.0
RELIEFWEB_API_URL="https://api.reliefweb.int/v1/reports?appname=welfare-foundation-monitor&limit=40&profile=list&preset=latest"
USGS_FEED_URL="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_month.geojson"

KBS_VERIFIED_SEEDS=[
 ("동행 567회 산골 소녀 지민이의 독립 선언","2026-07-18","https://vod.kbs.co.kr/m/index.html?program_code=T2014-0877&program_id=PS-2026122474-01-000&section_code=05&sname=vod&source=episode&stype=vod"),
 ("동행 566회 기적의 아빠, 상봉 씨","2026-07-11","https://vod.kbs.co.kr/m/index.html?program_code=T2014-0877&program_id=PS-2026112095-01-000&section_code=05&sname=vod&source=episode&stype=vod"),
 ("동행 565회 오늘도 활짝, 무공해 삼 남매","2026-07-04","https://vod.kbs.co.kr/m/index.html?program_code=T2014-0877&program_id=PS-2026112094-01-000&section_code=05&sname=vod&source=episode&stype=vod"),
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
 "disaster_kr":KR_DISASTER_KEYWORDS,
 "disaster_global":GLOBAL_DISASTER_KEYWORDS,
 "ngo":NGO_KEYWORDS,
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

class AnchorParser(HTMLParser):
 def __init__(self,limit=MAX_PAGE_LINKS):
  super().__init__(convert_charrefs=True); self.limit=limit; self.links=[]; self.href=None; self.parts=[]
 def handle_starttag(self,tag,attrs):
  if tag.lower()=="a" and self.href is None and len(self.links)<self.limit:
   self.href=dict(attrs).get("href"); self.parts=[]
 def handle_data(self,data):
  if self.href is not None: self.parts.append(data)
 def handle_endtag(self,tag):
  if tag.lower()=="a" and self.href is not None:
   self.links.append((self.href," ".join(self.parts))); self.href=None; self.parts=[]

def parse_anchors(doc,limit=MAX_PAGE_LINKS):
 parser=AnchorParser(limit); parser.feed(doc); parser.close(); return parser.links

def fetch(url, data=None, headers=None, tries=2, timeout=35):
 hdr={"User-Agent":UA, **(headers or {})}
 for i in range(tries):
  try:
   with urlopen(Request(url,data=data,headers=hdr),timeout=timeout) as r:
    raw=r.read(MAX_RESPONSE_BYTES+1)
    if len(raw)>MAX_RESPONSE_BYTES:
     raise ValueError(f"response too large: {len(raw)} bytes")
    return raw
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


def disaster_item(sub,title,url,summary,published_at,source,source_type):
 title=clean(title); summary=clean(summary)
 if not title or not url: return None
 keywords=KR_DISASTER_KEYWORDS if sub=="disaster_kr" else GLOBAL_DISASTER_KEYWORDS
 text=(title+" "+summary).lower()
 matched=[k for k in keywords if k.lower() in text]
 if not matched: return None
 return {
  "id":"","category":"disaster","subcategory":sub,
  "subcategory_label":SUB_LABELS[sub],"title":title,
  "summary":summary[:360] or title,"source":source,"url":url,
  "published_at":published_at,"keywords":matched[:6],
  "priority":min(5,3+min(2,len(matched)//2)),"ai_analyzed":False,
  "insight":"","trend_tags":[],"confidence":"공식기관 자료",
  "source_type":source_type,"final_source":source,"verification_url":url
 }

def parse_date_flexible(text):
 text=clean(text)
 patterns=[
  r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})",
  r"(20\d{2})(\d{2})(\d{2})"
 ]
 for pattern in patterns:
  m=re.search(pattern,text)
  if not m: continue
  try: return datetime(int(m.group(1)),int(m.group(2)),int(m.group(3)),tzinfo=timezone.utc).isoformat()
  except ValueError: pass
 return ""

def collect_kr_official():
 out=[]; errors=[]
 for source,url in KR_OFFICIAL_PAGES:
  try:
   doc=fetch(url).decode("utf-8","replace")
   seen=set()
   for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',doc,re.I|re.S):
    link=urljoin(url,html.unescape(m.group(1)))
    title=clean(m.group(2))
    context=clean(doc[max(0,m.start()-350):min(len(doc),m.end()+350)])
    stamp=parse_date_flexible(context)
    if not stamp or link in seen: continue
    item=disaster_item("disaster_kr",title,link,context,stamp,source,"국내 공식기관 직접수집")
    if item: seen.add(link); out.append(item)
  except Exception as e:
   errors.append({"source":"국내 공식 "+source,"error":str(e)[:160]})
 return out,errors


def gdacs_api_score(event_type,event_id):
 if not event_type or not event_id: return None
 url=("https://www.gdacs.org/gdacsapi/api/events/geteventdata?eventtype="
      +quote(event_type)+"&eventid="+quote(event_id))
 payload=json.loads(fetch(url,tries=1,timeout=25))
 preferred=[]; fallback=[]
 def walk(value):
  if isinstance(value,dict):
   for key,val in value.items():
    name=str(key).lower().replace("_","")
    if name=="alertscore": preferred.append(val)
    elif name=="score": fallback.append(val)
    walk(val)
  elif isinstance(value,list):
   for val in value: walk(val)
 walk(payload)
 for value in preferred+fallback:
  try: return float(value)
  except (TypeError,ValueError): pass
 return None

def gdacs_xml_value(element,name):
 for child in element.iter():
  if child.tag.rsplit("}",1)[-1].lower()==name:
   value=clean(child.text)
   if value: return value
 return ""

def parse_gdacs_rss(raw,min_score=GDACS_MIN_SCORE):
 root=ET.fromstring(raw); out=[]
 for e in root.findall(".//item")[:40]:
  score_text=""
  # GDACS RSS에는 여러 종류의 score가 있으므로 정확한 alertscore만 사용한다.
  # 일반 <score>를 허용하면 severity/episode score를 GDACS Score로 오인할 수 있다.
  for child in e.iter():
   local=child.tag.rsplit("}",1)[-1].lower()
   if local=="alertscore":
    score_text=clean(child.text)
    if score_text: break
  event_type=gdacs_xml_value(e,"eventtype")
  event_id=gdacs_xml_value(e,"eventid")
  try: rss_score=float(score_text)
  except (TypeError,ValueError): continue
  # 상세 API의 수치가 웹 이벤트 화면과 동일한 최종 GDACS Score다.
  # RSS 값만으로 통과시키지 않으며 API 검증 실패 항목도 보수적으로 제외한다.
  try: score=gdacs_api_score(event_type,event_id)
  except Exception: continue
  if score is None or score<min_score: continue
  title=clean(e.findtext("title")); link=clean(e.findtext("link"))
  desc=clean(e.findtext("description")); source=clean(e.findtext("source")) or "GDACS"
  combined=title+" "+desc+" "+source
  if not title or not link or not relevant("disaster","disaster_global",combined): continue
  pub=clean(e.findtext("pubDate"))
  try: stamp=datetime.strptime(pub,"%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).isoformat()
  except Exception: stamp=datetime.now(timezone.utc).isoformat()
  item=disaster_item("disaster_global",title,link,desc,stamp,"GDACS","해외 공식 재난경보")
  if not item: continue
  item.update({"gdacs_score":score,"keywords":item["keywords"][:6],
               "final_source":"GDACS","confidence":"공식기관 자료",
               "verification_url":link})
  out.append(item)
 return out

def collect_global_official():
 out=[]; errors=[]
 try:
  for item in parse_gdacs_rss(fetch(GDACS_RSS_URL)):
   item.update({"source":"GDACS","source_type":"해외 공식 재난경보",
                "final_source":"GDACS","confidence":"공식기관 자료",
                "verification_url":item["url"]})
   out.append(item)
 except Exception as e: errors.append({"source":"GDACS","error":str(e)[:160]})
 try:
  payload=json.loads(fetch(RELIEFWEB_API_URL))
  for row in payload.get("data",[]):
   f=row.get("fields",{})
   stamp=f.get("date",{}).get("created") or f.get("date",{}).get("original") or ""
   url=f.get("url_alias") or ("https://reliefweb.int/node/"+str(row.get("id","")))
   item=disaster_item("disaster_global",f.get("title",""),url,
                      f.get("body-html",""),stamp,"ReliefWeb","해외 공식 상황보고")
   if item: out.append(item)
 except Exception as e: errors.append({"source":"ReliefWeb","error":str(e)[:160]})
 try:
  payload=json.loads(fetch(USGS_FEED_URL))
  for row in payload.get("features",[]):
   p=row.get("properties",{}); epoch=p.get("time")
   if not epoch: continue
   stamp=datetime.fromtimestamp(epoch/1000,tz=timezone.utc).isoformat()
   mag=p.get("mag"); title=p.get("title","")
   summary=("USGS significant earthquake"+((" magnitude "+str(mag)) if mag is not None else ""))
   item=disaster_item("disaster_global",title,p.get("url",""),summary,stamp,
                      "USGS","해외 공식 지진정보")
   if item: out.append(item)
 except Exception as e: errors.append({"source":"USGS","error":str(e)[:160]})
 return out,errors

def keep_recent_disasters(old_items,days=DISASTER_DAYS):
 cutoff=datetime.now(timezone.utc)-timedelta(days=days)
 kept=[]
 for item in old_items:
  if item.get("category")!="disaster": continue
  if item.get("source")=="GDACS":
   # GDACS는 매 실행마다 공식 RSS에서 다시 수집·검증한다.
   # 과거 데이터에 잘못 저장된 score가 30일 병합으로 되살아나는 것을 차단한다.
   continue
  try:
   stamp=datetime.fromisoformat(item.get("published_at","").replace("Z","+00:00"))
   if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
  except Exception: continue
  if stamp>=cutoff: kept.append(item)
 return kept

def ngo_item(title,url,context,published_at,source,source_type):
 title=clean(title); context=clean(context)
 if not title or not url or not published_at: return None
 text=(title+" "+context).lower()
 matched=[k for k in NGO_KEYWORDS if k.lower() in text]
 if not matched: return None
 return {
  "id":"","category":"ngo","subcategory":"ngo","subcategory_label":SUB_LABELS["ngo"],
  "title":title,"summary":context[:360] or title,"source":source,"url":url,
  "published_at":published_at,"keywords":matched[:6],"priority":min(5,2+min(3,len(matched)//2)),
  "ai_analyzed":False,"insight":"","trend_tags":[],"confidence":"공식 NGO 자료" if "공식" in source_type else "원문 확인 필요",
  "source_type":source_type,"final_source":source,"verification_url":url
 }

def is_official_ngo(url,domains):
 host=urlparse(url).netloc.lower().split(":")[0]
 return any(host==d or host.endswith("."+d) for d in domains)

def collect_ngo_official():
 out=[]; errors=[]
 for ngo in NGO_SOURCES:
  for page_url in ngo["pages"]:
   try:
    doc=fetch(page_url).decode("utf-8","replace"); seen=set()
    for href,anchor_text in parse_anchors(doc):
     url=urljoin(page_url,html.unescape(href))
     if not is_official_ngo(url,ngo["domains"]) or url in seen: continue
     title=clean(anchor_text)
     pos=doc.find(href)
     context=clean(doc[max(0,pos-500):min(len(doc),pos+len(href)+500)]) if pos>=0 else title
     stamp=parse_date_flexible(context)
     item=ngo_item(title,url,context,stamp,ngo["name"],"NGO 공식 홈페이지 직접수집")
     if item: seen.add(url); out.append(item)
   except Exception as e:
    errors.append({"source":"NGO 공식 "+ngo["name"],"error":str(e)[:160]})
 return out,errors

def collect_ngo_google():
 out=[]; errors=[]
 activity='("모금" OR "후원" OR "기부" OR "캠페인" OR "긴급구호" OR "지원사업" OR "아동지원" OR "국제개발협력" OR "사업성과")'
 for ngo in NGO_SOURCES:
  domains=" OR ".join("site:"+d for d in ngo["domains"])
  query='"'+ngo["name"]+'" '+activity+" OR ("+domains+") "+activity
  try: out+=parse_rss(fetch(google_rss(query)),"ngo","ngo")
  except Exception as e: errors.append({"source":"NGO Google 뉴스 "+ngo["name"],"error":str(e)[:160]})
 return out,errors

def keep_recent_ngo(old_items,days=NGO_DAYS):
 cutoff=datetime.now(timezone.utc)-timedelta(days=days); kept=[]
 for item in old_items:
  if item.get("category")!="ngo": continue
  try:
   stamp=datetime.fromisoformat(item.get("published_at","").replace("Z","+00:00"))
   if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
  except Exception: continue
  if stamp>=cutoff: kept.append(item)
 return kept

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

def verified_kbs_seeds(days=30):
 cutoff=datetime.now(timezone.utc)-timedelta(days=days)
 out=[]
 for title,date,url in KBS_VERIFIED_SEEDS:
  stamp=datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
  if stamp<cutoff: continue
  item=kbs_item(title,url,title+" "+date,"KBS 공식 다시보기")
  if item: out.append(item)
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
 # NGO 공식 홈페이지는 주 수집원, 기관별 OR 검색 Google 뉴스는 보조 수집원이다.
 ngo_official,ngo_official_errors=collect_ngo_official()
 ngo_google,ngo_google_errors=collect_ngo_google()
 items+=ngo_official+ngo_google
 errors+=ngo_official_errors+ngo_google_errors
 # 개별 기관 실패나 신규 게시물 부재와 관계없이 기존 NGO 자료는 게시일 기준 30일 유지한다.
 items+=keep_recent_ngo(old.get("items",[]),NGO_DAYS)
 # 국내·해외 공식 재해 수집은 서로 독립 실행하며 Google 뉴스 RSS는 보조 경로다.
 kr_disasters,kr_errors=collect_kr_official()
 global_disasters,global_errors=collect_global_official()
 items+=kr_disasters+global_disasters
 errors+=kr_errors+global_errors
 # 일부 공식기관이 응답하지 않거나 신규 게시물이 없어도 기존 재해 기록은 30일간 유지한다.
 items+=keep_recent_disasters(old.get("items",[]),DISASTER_DAYS)
 # KBS 공식 프로그램·통합검색은 주 수집원, Google 뉴스는 보조 수집원이다.
 kbs_items,kbs_errors=collect_kbs_official()
 items+=kbs_items
 # KBS가 검색 목록을 동적으로 제공하는 동안에는 검증된 공식 회차를 초기 기록으로 사용한다.
 items+=verified_kbs_seeds(30)
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
