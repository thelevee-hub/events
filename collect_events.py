#!/usr/bin/env python3
"""The Levee Events discovery, Phase 2.1.

Reads events.json; writes only candidates.json and review-report.md.
No candidate is ever published automatically. Python standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta, date
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote, quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "events.json"
CANDIDATES = ROOT / "candidates.json"
REPORT = ROOT / "review-report.md"

SOURCES = [
    {"name": "Experience Mount Vernon", "url": "https://www.experiencemv.org/events"},
    {"name": "Visit Knox County", "url": "https://visitknoxohio.org/events"},
    {"name": "City of Mount Vernon", "url": "https://www.mtvernonoh.gov/calendar.aspx"},
    {"name": "Public Library", "url": "https://www.knox.net/calendar.html"},
    {"name": "MVNU", "url": "https://mvnu.edu/cmcal-calendar/calendar-new/"},
    {"name": "Mount Vernon City Schools", "url": "https://www.mt-vernon.k12.oh.us/our-district/district-calendar"},
    {"name": "The Woodward Opera House", "url": "https://www.thewoodward.org/"},
    {"name": "Knox County Chamber", "url": "https://business.knoxchamber.com/events/"},
    {"name": "Paragraphs Bookstore", "url": "https://paragraphsbookstore.com/upcoming-events"},
    {"name": "Nellie Six Productions", "url": "https://www.nelliesix.com/event-calendar"},
]
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
DATE_RX = re.compile(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b", re.I)
ISO_RX = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
CITY_RX = re.compile(r"\bmount\s+vernon\b", re.I)
OUTSIDE_RX = re.compile(r"\b(gambier|fredericktown|centerburg|danville|howard|utica|martinsburg)\b", re.I)

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.active = None
        self.depth = 0
    def handle_starttag(self, tag, attrs):
        if tag == "a" and self.active is None:
            self.active = {"href": dict(attrs).get("href", ""), "text": []}
            self.depth = 1
        elif self.active is not None:
            self.depth += 1
    def handle_data(self, data):
        if self.active is not None:
            self.active["text"].append(data)
    def handle_endtag(self, tag):
        if self.active is not None:
            self.depth -= 1
            if self.depth <= 0 or tag == "a":
                self.links.append((" ".join(" ".join(self.active["text"]).split()), self.active["href"]))
                self.active = None
                self.depth = 0

def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; TheLeveeEvents/2.1; community event index)", "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read(2_500_000).decode("utf-8", "replace")

def normalize(text):
    text = str(text or "").lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()

def title_from_url(url):
    """Chamber detail URLs contain the real title in their slug."""
    path = unquote(urlparse(url).path).rstrip("/")
    if "/events/details/" not in path:
        return ""
    slug = path.split("/events/details/", 1)[1].split("/", 1)[0]
    slug = re.sub(r"-\d{4,6}$", "", slug)  # Chamber event record ID
    slug = re.sub(r"-(?:\d{2}-\d{2}-20\d{2}|20\d{2}-\d{2}-\d{2})$", "", slug)
    return slug.replace("-", " ").strip().title()

def extract_date(text, url):
    match = DATE_RX.search(text)
    if match:
        month = MONTHS[match.group(1)[:3].lower()]
        year = int(match.group(3) or datetime.now(timezone.utc).year)
        day = int(match.group(2))
        try:
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return ""
    match = ISO_RX.search(url)
    if match:
        return match.group(0)
    # Chamber recurring event URLs often carry an MM-DD-YYYY occurrence suffix.
    match = re.search(r"(?:^|/|-)(\d{2})-(\d{2})-(20\d{2})(?:-|$)", url)
    if match:
        return f"{match.group(3)}-{match.group(1)}-{match.group(2)}"
    return ""

def discover(source):
    try:
        page = fetch(source["url"])
        parser = LinkParser()
        parser.feed(page)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"
    found = []
    chamber = source["name"] == "Knox County Chamber"
    for label, href in parser.links:
        url = urljoin(source["url"], href)
        if urlparse(url).scheme not in ("http", "https"):
            continue
        date = extract_date(label, url)
        if not date:
            continue
        if date < datetime.now(timezone.utc).strftime("%Y-%m-%d"):
            continue
        title = title_from_url(url) if chamber else re.sub(DATE_RX, "", label).strip(" -—|,:")
        if not title or normalize(title) in ("details", "view event", "read more"):
            continue
        # Avoid non-event links that merely happen to mention a date.
        if chamber and "/events/details/" not in urlparse(url).path:
            continue
        identity = hashlib.sha1((source["name"] + "|" + url + "|" + date).encode()).hexdigest()[:14]
        found.append({
            "id": identity, "title_raw": title, "date_raw": date,
            "source": source["name"], "source_url": url,
            "status": "needs-review", "discovered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "location_status": "unverified", "notes": "Confirm exact Mount Vernon venue, time, public access, and date on the event detail page before approval."
        })
    return found, None


LIBRARY_ICS = "https://calendar.google.com/calendar/ical/plmvkcohio%40gmail.com/public/basic.ics"
LOCAL_TZ = ZoneInfo("America/New_York")

def ics_unescape(value):
    return value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")

def parse_ics_events(raw):
    # RFC 5545 line unfolding; retain field parameters (TZID, VALUE=DATE).
    lines = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    events, current = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            base = key.split(";", 1)[0]
            if base in ("EXDATE", "RDATE"):
                current.setdefault(base, []).append((key, value))
            else:
                current[base] = (key, ics_unescape(value))
    return events

def event_datetime(field):
    if not field:
        return None
    key, value = field
    try:
        if "VALUE=DATE" in key or len(value) == 8:
            return datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=LOCAL_TZ)
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
        tz = LOCAL_TZ  # Library feed uses America/New_York for local timestamps.
        return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=tz)
    except ValueError:
        return None

def occurrences(event, today, horizon):
    start = event_datetime(event.get("DTSTART"))
    if start is None:
        return []
    rule = event.get("RRULE", ("", ""))[1]
    if not rule:
        return [start] if today <= start.date() <= horizon else []
    parts = dict(x.split("=", 1) for x in rule.split(";") if "=" in x)
    freq = parts.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        return []  # Unsupported recurrence is not guessed.
    interval = max(1, int(parts.get("INTERVAL", "1")))
    count = int(parts.get("COUNT", "999999"))
    until = event_datetime(("", parts["UNTIL"])) if "UNTIL" in parts else None
    excluded = set()
    for key, value in event.get("EXDATE", []):
        for item in value.split(","):
            parsed = event_datetime((key, item))
            if parsed:
                excluded.add(parsed.strftime("%Y-%m-%dT%H:%M"))
    days = {"MO":0,"TU":1,"WE":2,"TH":3,"FR":4,"SA":5,"SU":6}
    weekdays = {days[x] for x in parts.get("BYDAY", "").split(",") if x in days}
    if not weekdays:
        weekdays = {start.weekday()}
    results = []
    cursor = start
    emitted = 0
    max_days = min((horizon - start.date()).days + 1, 3660)
    for i in range(max(0, max_days)):
        cursor = start + timedelta(days=i)
        if until and cursor.astimezone(timezone.utc) > until.astimezone(timezone.utc):
            break
        if freq == "DAILY":
            eligible = i % interval == 0
        else:
            eligible = (i // 7) % interval == 0 and cursor.weekday() in weekdays
        if not eligible:
            continue
        emitted += 1
        if emitted > count:
            break
        if today <= cursor.date() <= horizon and cursor.strftime("%Y-%m-%dT%H:%M") not in excluded:
            results.append(cursor)
    return results

def library_location_status(location):
    value = normalize(location)
    if any(x in value for x in ("gambier", "fredericktown", "danville", "centerburg", "howard")):
        return "outside-mount-vernon"
    if any(x in value for x in ("online", "virtual", "zoom", "facebook", "youtube")):
        return "online-only"
    if "201 n mulberry" in value or "mount vernon" in value or "mt vernon" in value:
        return "mount-vernon-indicated"
    return "unverified"

def discover_library_ics(today=None, horizon_days=90, raw=None):
    today = today or datetime.now(LOCAL_TZ).date()
    horizon = today + timedelta(days=horizon_days)
    try:
        content = raw if raw is not None else fetch(LIBRARY_ICS)
        events = parse_ics_events(content)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"
    found = []
    for event in events:
        if event.get("STATUS", ("", ""))[1].upper() == "CANCELLED":
            continue
        title = event.get("SUMMARY", ("", ""))[1].strip()
        location = event.get("LOCATION", ("", ""))[1].strip()
        if not title or re.search(r"\b(closed|board meeting|radio show|podcast)\b", title, re.I):
            continue
        status = library_location_status(location)
        if status in ("outside-mount-vernon", "online-only"):
            continue
        for when in occurrences(event, today, horizon):
            uid = event.get("UID", ("", ""))[1]
            event_url = "https://www.knox.net/calendar.html"
            identity = hashlib.sha1(("Public Library Adults|" + uid + "|" + when.isoformat()).encode()).hexdigest()[:14]
            found.append({
                "id": identity, "title_raw": title, "date_raw": when.strftime("%Y-%m-%d"),
                "time_raw": "All day" if "VALUE=DATE" in event.get("DTSTART", ("", ""))[0] else when.strftime("%-I:%M %p"),
                "venue_raw": location, "source": "Public Library Adults Calendar",
                "source_url": event_url, "calendar_uid": uid,
                "status": "needs-review", "discovered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "location_status": status,
                "notes": "Confirm date, time, public access, registration, and Mount Vernon location before approval."
            })
    return found, None

def compare(candidate, master):
    best_score, best = 0.0, None
    for event in master:
        score = SequenceMatcher(None, normalize(candidate["title_raw"]), normalize(event.get("title", ""))).ratio()
        event_date = event.get("date_display", "")
        date_match = False
        match = DATE_RX.search(event_date)
        if match:
            date_match = int(match.group(2)) == int(candidate["date_raw"][-2:]) and MONTHS[match.group(1)[:3].lower()] == int(candidate["date_raw"][5:7])
        if date_match:
            score += 0.14
        if score > best_score:
            best_score, best = score, event
    return round(min(best_score, 1.0), 3), best

def main():
    master = json.loads(MASTER.read_text(encoding="utf-8")) if MASTER.exists() else []
    old = json.loads(CANDIDATES.read_text(encoding="utf-8")) if CANDIDATES.exists() else []
    
    decisions_path = ROOT / "review-decisions.json"
    decisions = (
        json.loads(decisions_path.read_text(encoding="utf-8"))
        if decisions_path.exists() else {}
    )

    old_map = {(x.get("source"), x.get("source_url"), x.get("date_raw")): x for x in old}
    errors, candidates = [], []
    for source in SOURCES + [{"name": "Public Library Adults ICS", "url": LIBRARY_ICS}]:
        found, error = discover_library_ics() if source["name"] == "Public Library Adults ICS" else discover(source)
        if error:
            errors.append((source["name"], error))
            continue
        for item in found:
            score, matched = compare(item, master)
            item["possible_existing_match"] = score
            if score >= 0.90:
                item["classification"] = "likely-duplicate"
            elif score >= 0.70:
                item["classification"] = "possible-existing-or-change"
            else:
                item["classification"] = "new-needs-location-verification"
            if matched and score >= 0.70:
                item["possible_existing_title"] = matched.get("title", "")
            previous = old_map.get((item["source"], item["source_url"], item["date_raw"]), {})
            item["first_seen"] = previous.get("first_seen", previous.get("discovered_at", item["discovered_at"]))
            if previous.get("review_decision") in ("approved", "rejected", "deferred"):
                item["review_decision"] = previous["review_decision"]
            saved = decisions.get(item["id"])
            if saved:
                item["review_decision"] = saved["decision"]
                item["review_recorded_at"] = saved.get("recorded_at", "")
            candidates.append(item)

    unique = {x["id"]: x for x in candidates}
    candidates = sorted(unique.values(), key=lambda x: (x["date_raw"], x["title_raw"].lower()))
    CANDIDATES.write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    groups = [
        ("New candidates — verify location and details", "new-needs-location-verification"),
        ("Possible existing events or changes", "possible-existing-or-change"),
        ("Likely duplicates — do not republish", "likely-duplicate"),
    ]
    lines = ["# The Levee Event Review — Phase 2.2", "", f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", "",
             f"- Total candidates: **{len(candidates)}**", f"- New leads requiring verification: **{sum(x['classification'] == groups[0][1] for x in candidates)}**",
             f"- Possible changes: **{sum(x['classification'] == groups[1][1] for x in candidates)}**",
             f"- Likely duplicates: **{sum(x['classification'] == groups[2][1] for x in candidates)}**", f"- Source errors: **{len(errors)}**", ""]
    for heading, classification in groups:
        lines += [f"## {heading}", ""]
    
        entries = [x for x in candidates if x["classification"] == classification and x.get("review_decision") not in ("hold", "reject", "approve")]
   
    for x in entries[:150]:
            lines += [f"- **{x['date_raw']} — {x['title_raw']}**", f"  - Source: {x['source']}", f"  - Event: {x['source_url']}"]
            if x.get("possible_existing_title"):
                lines.append(f"  - Possible match: {x['possible_existing_title']} (score {x['possible_existing_match']})")
            if x.get("venue_raw"):
                lines.append(f"  - Venue: {x['venue_raw']}")
            if x.get("time_raw"):
                lines.append(f"  - Time: {x['time_raw']}")
            if classification == groups[0][1]:
                lines.append("  - **Location not yet verified; do not publish without checking the source.**")
        if not entries:
            lines.append("- None.")
        lines.append("")
        
    lines += ["## Held events — awaiting further review", ""]
    held = [
        x for x in candidates
        if x.get("review_decision") == "hold"
    ]
    for x in held:
        lines += [
            f"- **{x['date_raw']} — {x['title_raw']}**",
            f"  - Candidate ID: `{x['id']}`",
            f"  - Source: {x['source']}",
            f"  - Event: {x['source_url']}",
        ]
        if x.get("venue_raw"):
            lines.append(f"  - Venue: {x['venue_raw']}")
        lines.append("")
    if not held:
        lines.append("- None.")
    lines.append("")

    lines += ["## Source errors", ""]
    for name, error in errors:
        lines.append(f"- **{name}:** {error}")
    if not errors:
        lines.append("- None.")
    lines += ["", "---", "This is a review queue only. The collector never edits events.json or publishes events."]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Phase 2.1: {len(candidates)} candidates, {len(errors)} source errors; review report written.")

if __name__ == "__main__":
    main()
