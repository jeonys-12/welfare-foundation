import json
import unittest
from unittest.mock import patch

import scripts.collect_news as collector


def item(url, analyzed=False):
 return {"id":url.rsplit("/",1)[-1],"url":url,"category":"csr","subcategory":"csr",
         "title":"새 소식","summary":"이 원문은 공익 사업의 구체적인 대상과 일정, 지원 내용 및 향후 계획을 충분히 설명합니다.","source":"기관",
         "published_at":"2026-08-25T00:00:00+00:00","ai_analyzed":analyzed}


class AiCostTests(unittest.TestCase):
 def fake_response(self, request):
  rows=json.loads(request["input"].split("\n")[-1])
  output={"items":[{"i":x["i"],"t":x["t"],"s":"짧은 요약","n":"실무 시사점",
                    "g":["태그"],"p":3,"c":"보통"} for x in rows]}
  return json.dumps({"output_text":json.dumps(output,ensure_ascii=False),
                     "usage":{"input_tokens":100,"output_tokens":50,
                              "input_tokens_details":{"cached_tokens":20}}})

 def test_reuses_paid_analysis_without_second_call(self):
  calls=[]
  def fake_fetch(url,data=None,**kwargs):
   calls.append(json.loads(data))
   return self.fake_response(calls[-1])
  fresh=item("https://example.com/1")
  with patch.object(collector,"OPENAI_API_KEY","test"), patch.object(collector,"fetch",fake_fetch):
   first,status1=collector.analyze_with_openai([dict(fresh)],[])
   second,status2=collector.analyze_with_openai([dict(fresh)],[dict(first[0])])
  self.assertEqual(len(calls),1)
  self.assertEqual(status1["cached_tokens"],20)
  self.assertEqual(status2["reused"],1)
  self.assertEqual(status2["analyzed"],0)

 def test_reuses_identical_input_when_url_changes(self):
  calls=[]
  def fake_fetch(url,data=None,**kwargs):
   calls.append(json.loads(data))
   return self.fake_response(calls[-1])
  first=item("https://example.com/original")
  moved=item("https://mirror.example.com/moved")
  with patch.object(collector,"OPENAI_API_KEY","test"), patch.object(collector,"fetch",fake_fetch):
   analyzed,_=collector.analyze_with_openai([dict(first)],[])
   _,status=collector.analyze_with_openai([dict(moved)],[dict(analyzed[0])])
  self.assertEqual(len(calls),1)
  self.assertEqual(status["reused"],1)

 def test_does_not_backfill_old_unanalyzed_items(self):
  old=item("https://example.com/old")
  with patch.object(collector,"OPENAI_API_KEY","test"), patch.object(
      collector,"fetch",side_effect=AssertionError("API must not be called")):
   _,status=collector.analyze_with_openai([dict(old)],[dict(old)])
  self.assertEqual(status["analyzed"],0)

 def test_skips_thin_new_input_without_api_call(self):
  thin=item("https://example.com/thin")
  thin["summary"]=thin["title"]
  with patch.object(collector,"OPENAI_API_KEY","test"), patch.object(
      collector,"fetch",side_effect=AssertionError("API must not be called")):
   _,status=collector.analyze_with_openai([thin],[])
  self.assertEqual(status["analyzed"],0)
  self.assertEqual(status["skipped_thin"],1)

 def test_sends_only_new_item_and_compact_keys(self):
  old=item("https://example.com/old")
  new=item("https://example.com/new")
  calls=[]
  def fake_fetch(url,data=None,**kwargs):
   calls.append(json.loads(data))
   return self.fake_response(calls[-1])
  with patch.object(collector,"OPENAI_API_KEY","test"), patch.object(collector,"fetch",fake_fetch):
   collector.analyze_with_openai([dict(old),dict(new)],[dict(old)])
  rows=json.loads(calls[0]["input"].split("\n")[-1])
  self.assertEqual(len(rows),1)
  self.assertEqual(set(rows[0]),{"i","k","t","s"})
  self.assertEqual(calls[0]["max_output_tokens"],420)


if __name__=="__main__":
 unittest.main()
