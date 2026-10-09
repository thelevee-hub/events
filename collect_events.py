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
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

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
    old_map = {(x.get("source"), x.get("source_url"), x.get("date_raw")): x for x in old}
    errors, candidates = [], []
    for source in SOURCES:
        found, error = discover(source)
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
            candidates.append(item)
    unique = {(x["source_url"], x["date_raw"]): x for x in candidates}
    candidates = sorted(unique.values(), key=lambda x: (x["date_raw"], x["title_raw"].lower()))
    CANDIDATES.write_text(json.dumps(candidates, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    groups = [
        ("New candidates — verify location and details", "new-needs-location-verification"),
        ("Possible existing events or changes", "possible-existing-or-change"),
        ("Likely duplicates — do not republish", "likely-duplicate"),
    ]
    lines = ["# The Levee Event Review — Phase 2.1", "", f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", "",
             f"- Total candidates: **{len(candidates)}**", f"- New leads requiring verification: **{sum(x['classification'] == groups[0][1] for x in candidates)}**",
             f"- Possible changes: **{sum(x['classification'] == groups[1][1] for x in candidates)}**",
             f"- Likely duplicates: **{sum(x['classification'] == groups[2][1] for x in candidates)}**", f"- Source errors: **{len(errors)}**", ""]
    for heading, classification in groups:
        lines += [f"## {heading}", ""]
        entries = [x for x in candidates if x["classification"] == classification]
        for x in entries[:150]:
            lines += [f"- **{x['date_raw']} — {x['title_raw']}**", f"  - Source: {x['source']}", f"  - Event: {x['source_url']}"]
            if x.get("possible_existing_title"):
                lines.append(f"  - Possible match: {x['possible_existing_title']} (score {x['possible_existing_match']})")
            if classification == groups[0][1]:
                lines.append("  - **Location not yet verified; do not publish without checking the source.**")
        if not entries:
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
