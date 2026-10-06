#!/usr/bin/env python3
import json,html,re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
R=Path(__file__).parent
E=[e for e in json.loads((R/"events.json").read_text()) if e.get("status")=="published"]
M={"Oct.":10,"Nov.":11,"Dec.":12}
def day(e):
 m=re.match(r"(Oct\.|Nov\.|Dec\.)\s+(\d+)",e["date_display"]); return (M[m.group(1)],int(m.group(2))) if m else None
def tm(s):
 s=s.strip()
 if s.lower().startswith("noon"): return (12,0)
 if s.lower().startswith("midnight"): return (0,0)
 # Prefer the first clock value. If its a.m./p.m. is omitted in a range, inherit from the later value.
 m=re.match(r"(\d{1,2})(?::(\d{2}))?",s)
 if not m:return None
 h=int(m.group(1)); n=int(m.group(2) or 0)
 rest=s[m.end():]
 ap=re.search(r"(a\.m\.|p\.m\.)",rest)
 if not ap:return None
 if ap.group(1)=="p.m." and h!=12:h+=12
 if ap.group(1)=="a.m." and h==12:h=0
 return h,n
def esc(s):return str(s).replace("\\\\","\\\\\\\\").replace("\\n","\\\\n").replace(",","\\\\,").replace(";","\\\\;")
cards=[]
for e in E:
 cards.append(f"""<article class="event"><div class="date">{html.escape(e['date_display'])}</div><h2>{html.escape(e['title'])}</h2><p>{html.escape(e['time_display'])} · {html.escape(e['venue'])}</p><p class="source">Source: {html.escape(e['source'])}</p><p><a href="{html.escape(e['source_url'],quote=True)}">Event details →</a></p></article>""")
css='body{margin:0;color:#242424;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:680px;margin:auto;padding:24px}header{border-bottom:1px solid #e6e6e6}h1,h2,.intro,.event p{font-family:Georgia,Cambria,serif}h1{font-size:48px}h2{font-size:25px}.event{padding:24px 0;border-bottom:1px solid #e6e6e6}.date,.source{color:#6b6b6b;font-size:13px}.calendar{padding:20px 0;border-bottom:1px solid #e6e6e6}a{color:#242424}'
page=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Mount Vernon Events | The Levee</title><style>{css}</style></head><body><header><div class="wrap"><small>The Levee</small><h1>Mount Vernon Events</h1><p>What’s happening in Mount Vernon, Ohio.</p></div></header><main class="wrap"><p class="intro"><b>Mount Vernon events, all in one place.</b> Events listed here must physically take place in Mount Vernon, Ohio.</p><div class="calendar"><a href="calendar.ics">Download / Subscribe to Calendar</a></div>{''.join(cards)}</main></body></html>"""
(R/"index.html").write_text(page)
L=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//The Levee//Mount Vernon Events//EN","CALSCALE:GREGORIAN","METHOD:PUBLISH","X-WR-CALNAME:The Levee - Mount Vernon Events","X-WR-TIMEZONE:America/New_York"]
stamp=datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
for e in E:
 d=day(e)
 if not d:continue
 L+=["BEGIN:VEVENT",f"UID:{e['uid']}",f"DTSTAMP:{stamp}",f"SUMMARY:{esc(e['title'])}"]
 t=tm(e["time_display"])
 if t:L.append(f"DTSTART;TZID=America/New_York:2026{d[0]:02d}{d[1]:02d}T{t[0]:02d}{t[1]:02d}00")
 else:L.append(f"DTSTART;VALUE=DATE:2026{d[0]:02d}{d[1]:02d}")
 L += [f"LOCATION:{esc(e['venue']+', Mount Vernon, OH')}",f"URL:{e['source_url']}",f"DESCRIPTION:{esc('Source: '+e['source'])}","END:VEVENT"]
L.append("END:VCALENDAR");(R/"calendar.ics").write_text("\r\n".join(L)+"\r\n")
print(f"Generated from {len(E)} records")
