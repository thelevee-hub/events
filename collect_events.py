#!/usr/bin/env python3
"""
The Levee Phase 2 event discovery collector.

Safety rule: this script NEVER edits events.json.
It writes candidates.json and review-report.md only.

Source adapters are intentionally conservative. A candidate must contain:
title, date text, Mount Vernon evidence, and a source URL.
"""
from __future__ import annotations
import json, re, hashlib, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from difflib import SequenceMatcher

ROOT=Path(__file__).parent
MASTER=ROOT/"events.json"
CANDIDATES=ROOT/"candidates.json"
REPORT=ROOT/"review-report.md"

SOURCES=[
 {"name":"Experience Mount Vernon","url":"https://www.experiencemv.org/events"},
 {"name":"Visit Knox County","url":"https://visitknoxohio.org/events"},
 {"name":"City of Mount Vernon","url":"https://www.mtvernonoh.gov/calendar.aspx"},
 {"name":"Public Library","url":"https://www.knox.net/events.html"},
 {"name":"MVNU","url":"https://mvnu.edu/cmcal-calendar/calendar-new/"},
 {"name":"Mount Vernon City Schools","url":"https://www.mt-vernon.k12.oh.us/our-district/district-calendar"},
 {"name":"The Woodward Opera House","url":"https://www.thewoodward.org/"},
 {"name":"Knox County Chamber","url":"https://business.knoxchamber.com/events/"},
 {"name":"Paragraphs Bookstore","url":"https://paragraphsbookstore.com/upcoming-events"},
 {"name":"Nellie Six Productions","url":"https://www.nelliesix.com/event-calendar"},
]

class LinkParser(HTMLParser):
 def __init__(self):
  super().__init__(); self.links=[]; self._href=None; self._txt=[]
 def handle_starttag(self,tag,attrs):
  if tag=="a":
   self._href=dict(attrs).get("href"); self._txt=[]
 def handle_data(self,data):
  if self._href is not None:self._txt.append(data)
 def handle_endtag(self,tag):
  if tag=="a" and self._href is not None:
   txt=" ".join("".join(self._txt).split())
   if txt:self.links.append((txt,self._href))
   self._href=None; self._txt=[]

def fetch(url):
 req=urllib.request.Request(url,headers={"User-Agent":"TheLeveeEvents/1.0 (+community calendar)"})
 with urllib.request.urlopen(req,timeout=25) as r:
  return r.read().decode("utf-8","replace")

def norm(s): return re.sub(r"[^a-z0-9]+"," ",s.lower()).strip()
def similarity(a,b): return SequenceMatcher(None,norm(a),norm(b)).ratio()

def discover(source):
 """Conservative generic discovery. Site-specific adapters can replace this later."""
 try: page=fetch(source["url"])
 except Exception as exc:
  return [],f"{type(exc).__name__}: {exc}"
 p=LinkParser(); p.feed(page)
 found=[]
 date_rx=re.compile(r"\b(?:Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2}\b",re.I)
 for text,href in p.links:
  # Generic adapter only promotes links that visibly include a date.
  dm=date_rx.search(text)
  if not dm: continue
  if href.startswith("/"):
   from urllib.parse import urljoin
   href=urljoin(source["url"],href)
  if not href.startswith("http"): continue
  found.append({
   "id":hashlib.sha1((source["name"]+"|"+text+"|"+href).encode()).hexdigest()[:14],
   "title_raw":text,
   "date_raw":dm.group(0),
   "source":source["name"],
   "source_url":href,
   "status":"needs-review",
   "discovered_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
   "notes":"Generic discovery; verify Mount Vernon, Ohio location, date, time and public access before approval."
  })
 return found,None

master=json.loads(MASTER.read_text(encoding="utf-8")) if MASTER.exists() else []
old=json.loads(CANDIDATES.read_text(encoding="utf-8")) if CANDIDATES.exists() else []
old_by_id={x["id"]:x for x in old if "id" in x}

candidates=[]; errors=[]
for source in SOURCES:
 items,err=discover(source)
 if err: errors.append((source["name"],err)); continue
 for item in items:
  # Never treat a weak title match as an automatic publish decision.
  best=max((similarity(item["title_raw"],e.get("title","")) for e in master),default=0)
  item["possible_existing_match"]=round(best,3)
  if best>=0.88:item["classification"]="possible-existing-or-change"
  else:item["classification"]="new-candidate"
  if item["id"] in old_by_id:
   item["first_seen"]=old_by_id[item["id"]].get("first_seen",old_by_id[item["id"]].get("discovered_at"))
  else:item["first_seen"]=item["discovered_at"]
  candidates.append(item)

# deterministic de-dupe
dedup={c["id"]:c for c in candidates}
candidates=sorted(dedup.values(),key=lambda x:(x["source"],x["date_raw"],x["title_raw"]))
CANDIDATES.write_text(json.dumps(candidates,indent=2,ensure_ascii=False),encoding="utf-8")

new_ids={c["id"] for c in candidates}-{x.get("id") for x in old}
new=[c for c in candidates if c["id"] in new_ids]
changed=[c for c in candidates if c["classification"]=="possible-existing-or-change"]

lines=[
 "# The Levee Event Review",
 "",
 f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
 "",
 f"- New candidates this run: **{len(new)}**",
 f"- Possible existing/changed events: **{len(changed)}**",
 f"- Total candidates awaiting review: **{len(candidates)}**",
 f"- Source errors: **{len(errors)}**",
 "",
 "## New candidates",""
]
for c in new[:100]:
 lines += [f"- **{c['date_raw']} — {c['title_raw']}**",f"  - Source: {c['source']}",f"  - {c['source_url']}"]
if not new: lines.append("- None.")
lines += ["","## Possible existing events / changes",""]
for c in changed[:100]:
 lines += [f"- **{c['date_raw']} — {c['title_raw']}** — match score {c['possible_existing_match']}"]
if not changed: lines.append("- None.")
lines += ["","## Source errors",""]
for name,err in errors: lines.append(f"- **{name}:** {err}")
if not errors: lines.append("- None.")
lines += ["","---","Nothing in this report is published automatically. Review candidates against the original source before adding them to events.json."]
REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
print(f"Review queue written: {len(candidates)} candidates; {len(new)} new; {len(errors)} source errors.")
