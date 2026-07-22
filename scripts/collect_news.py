#!/usr/bin/env python3
"""Public-interest monitoring collector. Uses Python stdlib only."""
import json, re, time, html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"data/news.json"
UA="Mozilla/5.0 (compatible; PublicValueMonitor/1.0; +https://github.com/jeonys-12/welfare-foundation)"
QUERIES=[
 ("law","공익법인 법 개정 OR 시행령 OR 국세청 OR 법제처",["law.go.kr","nts.go.kr","mois.go.kr"]),
 ("esg","ESG 기부 트렌드 사회적가치 지속가능경영",[]),
 ("csr","기업 사회공헌 기부 봉사 ESG",[]),
 ("disaster","재난 산불 홍수 지진 태풍 피해 지원",["mois.go.kr","kma.go.kr","reliefweb.int","gdacs.org"]),
 ("ngo","NGO 모금 캠페인 구호 사업 월드비전 굿네이버스 유니세프",[]),
 ("kbs","KBS 동행 프로그램",["kbs.co.kr"]),
]
KEYS={"law":["공익법인","법률","시행령","세법","공시"],"esg":["ESG","기부","지속가능","사회적 가치"],"csr":["사회공헌","기업","상생","봉사"],"disaster":["재난","산불","홍수","지진","태풍","구호"],"ngo":["NGO","모금","캠페인","지원사업"],"kbs":["동행","KBS","후원"]}
def clean(s):
 s=html.unescape(re.sub(r"<[^>]+>"," ",s or ""));return re.sub(r"\s+"," ",s).strip()
def fetch(url,tries=2):
 for i in range(tries):
  try:
   with urlopen(Request(url,headers={"User-Agent":UA}),timeout=20) as r:return r.read()
  except Exception:
   if i+1==tries:raise
   time.sleep(1+i)
def google_rss(q):
 return "https://news.google.com/rss/search?q="+quote(q+" when:30d")+"&hl=ko&gl=KR&ceid=KR:ko"
def parse_rss(raw,cat):
 root=ET.fromstring(raw); out=[]
 for e in root.findall(".//item")[:35]:
  title=clean(e.findtext("title")); link=clean(e.findtext("link")); desc=clean(e.findtext("description"))
  pub=clean(e.findtext("pubDate")); source=clean(e.findtext("source")) or urlparse(link).netloc
  try: stamp=datetime.strptime(pub,"%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).isoformat()
  except Exception: stamp=datetime.now(timezone.utc).isoformat()
  if not title or not link:continue
  matched=[k for k in KEYS[cat] if k.lower() in (title+" "+desc).lower()]
  out.append({"id":"","category":cat,"title":title,"summary":desc[:360],"source":source,"url":link,"published_at":stamp,"keywords":matched[:3],"priority":min(5,2+len(matched))})
 return out
def main():
 old={"items":[]}; errors=[]; items=[]
 try:old=json.loads(OUT.read_text(encoding="utf-8"))
 except Exception:pass
 for cat,q,domains in QUERIES:
  full=q+(" ("+" OR ".join("site:"+d for d in domains)+")" if domains else "")
  try:items+=parse_rss(fetch(google_rss(full)),cat)
  except Exception as e:errors.append({"source":cat,"error":str(e)[:160]})
 seen=set(); dedup=[]
 for x in sorted(items,key=lambda z:z["published_at"],reverse=True):
  key=re.sub(r"\W","",x["title"].lower())[:100]
  if key in seen:continue
  seen.add(key);x["id"]=str(abs(hash(x["category"]+"|"+key)));dedup.append(x)
 if not dedup:dedup=old.get("items",[])
 payload={"updated_at":datetime.now(timezone.utc).isoformat(),"item_count":len(dedup),"errors":errors,"items":dedup[:240]}
 OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
 print(f"collected={len(dedup)} errors={len(errors)}")
if __name__=="__main__":main()
