#!/usr/bin/env python3
"""Explicit, verified publication of one approved The Levee Events candidate."""
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent


def load_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    if os.environ.get("CONFIRM", "").strip() != "PUBLISH":
        raise SystemExit("Publication stopped: type exactly PUBLISH in final confirmation.")
    candidate_id = os.environ.get("CANDIDATE_ID", "").strip()
    candidates = load_json("candidates.json")
    matches = [x for x in candidates if str(x.get("id")) == candidate_id]
    if len(matches) != 1:
        raise SystemExit("Publication stopped: candidate not uniquely found.")
    candidate = matches[0]
    decision = load_json("review-decisions.json").get(candidate_id, {})
    if decision.get("decision") != "approve":
        raise SystemExit("Publication stopped: candidate must have an APPROVE decision.")
    if candidate.get("location_status") in ("outside-mount-vernon", "online-only"):
        raise SystemExit("Publication stopped: candidate is outside Mount Vernon or online-only.")

    title = os.environ.get("EVENT_TITLE", "").strip()
    venue = os.environ.get("EVENT_VENUE", "").strip()
    time_display = os.environ.get("EVENT_TIME", "").strip()
    event_date = os.environ.get("EVENT_DATE", "").strip()
    source_url = os.environ.get("EVENT_URL", "").strip()
    source = candidate.get("source", "").strip()
    verified_location = os.environ.get("VERIFIED_LOCATION", "").strip()
    verified_details = os.environ.get("VERIFIED_DETAILS", "").strip()

    if verified_location != "yes" or verified_details != "yes":
        raise SystemExit("Publication stopped: both verification confirmations must be yes.")
    if not all((candidate_id, title, venue, time_display, event_date, source_url, source)):
        raise SystemExit("Publication stopped: title, date, time, venue, URL, and source are required.")
    try:
        d = date.fromisoformat(event_date)
    except ValueError as exc:
        raise SystemExit("Publication stopped: date must be YYYY-MM-DD.") from exc
    if d.year != 2026 or d.month not in (10, 11, 12):
        raise SystemExit("Publication stopped: generator currently supports Oct–Dec 2026 only.")
    if d.isoformat() != str(candidate.get("date_raw", "")):
        raise SystemExit("Publication stopped: entered date differs from candidate. Re-review the candidate first.")
    url = urlparse(source_url)
    if url.scheme not in ("http", "https") or not url.netloc:
        raise SystemExit("Publication stopped: a valid HTTP(S) event source URL is required.")

    published = load_json("events.json")
    uid = f"{hashlib.sha256(('candidate|' + candidate_id).encode()).hexdigest()[:16]}@thelevee-events"
    if any(e.get("uid") == uid or e.get("candidate_id") == candidate_id for e in published):
        raise SystemExit("Publication stopped: this candidate has already been published.")
    # Conservative duplicate check: same date and normalized title, regardless of source URL.
    def norm(s):
        return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()
    display_date = d.strftime("%b.") + f" {d.day}"
    if any(norm(e.get("title")) == norm(title) and e.get("date_display") == display_date for e in published):
        raise SystemExit("Publication stopped: an event with the same title and date is already published.")

    record = {
        "uid": uid,
        "candidate_id": candidate_id,
        "date_display": display_date,
        "title": title,
        "time_display": time_display,
        "venue": venue,
        "city": "Mount Vernon",
        "state": "OH",
        "source": source,
        "source_url": source_url,
        "status": "published",
        "verification": "verified-" + datetime.now(timezone.utc).date().isoformat(),
    }
    published.append(record)
    (ROOT / "events.json").write_text(json.dumps(published, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Published candidate {candidate_id}: {title} ({event_date})")


if __name__ == "__main__":
    main()
