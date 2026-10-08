"""Keeps the data folder from growing without limit (e.g. a Raspberry Pi running for months).

Capture frames are the only thing that grows quickly (0.5-1 MB each). Their database rows stay - animals and vendor
offers point at them - but the image files go after CAPTURE_KEEP_DAYS, and the oldest go first whenever the folder
passes CAPTURE_MAX_MB. Each animal's card and name images are separate small files and are kept.
"""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from config import CAPTURE_DIR, CAPTURE_KEEP_DAYS, CAPTURE_MAX_MB
from database import engine
from models import Capture


def _utc(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def prune_captures(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=CAPTURE_KEEP_DAYS)
    removed, freed = 0, 0

    def drop(capture: Capture):
        nonlocal removed, freed
        file = CAPTURE_DIR / capture.path
        if file.exists():
            freed += file.stat().st_size
            file.unlink()
        capture.path = ""
        capture.dismissed = True  # nothing left to review
        removed += 1

    with Session(engine) as session:
        captures = session.exec(select(Capture).where(Capture.path != "").order_by(Capture.at)).all()
        for c in captures:
            if _utc(c.at) < cutoff:
                drop(c)
        kept = [c for c in captures if c.path]
        sizes = {c.id: (CAPTURE_DIR / c.path).stat().st_size if (CAPTURE_DIR / c.path).exists() else 0 for c in kept}
        total = sum(sizes.values())
        for c in kept:  # oldest first
            if total <= CAPTURE_MAX_MB * 1_000_000:
                break
            total -= sizes[c.id]
            drop(c)
        session.commit()
    return {"removed": removed, "freed_mb": round(freed / 1e6, 1)}
