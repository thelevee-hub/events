# The Levee — Phase 2 Discovery

This layer discovers possible Mount Vernon, Ohio events for human review.

## Files

- `collect_events.py` — checks configured public event sources and compares discoveries with `events.json`.
- `candidates.json` — machine-readable review queue.
- `review-report.md` — human-readable review summary.
- `.github/workflows/discover-events.yml` — scheduled/manual GitHub Action.

## Publishing safety

**The collector never edits `events.json`.** Nothing it discovers is automatically published to the website or calendar.

A candidate should be approved only after confirming:
1. It physically takes place in Mount Vernon, Ohio.
2. Date and time are current.
3. Venue/location is current.
4. It is appropriate for a public community calendar.
5. The source URL is retained.

## Schedule

GitHub invokes the workflow daily at 10:00 UTC, but an alternating-day gate performs discovery every other day. Manual runs bypass the gate.
