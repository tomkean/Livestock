"""The moves log: a drag made in steps (drag, scroll, drag) is one move."""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, SQLModel, create_engine, select

import server
from models import Animal, Event


def _session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _drag(session, animal, room):
    old = animal.pen
    animal.pen = room
    server._log_move(session, animal, old)
    session.commit()


def _moves(session):
    return [e.notes for e in session.exec(select(Event).where(Event.kind == "moved").order_by(Event.at))]


def test_drag_in_steps_is_one_move():
    s = _session()
    ewe = Animal(code="S1", species="sheep", sex="F", genes_top="GGGGG", pen="Ladies")
    s.add(ewe)
    s.commit()
    _drag(s, ewe, "Gentlemen")
    _drag(s, ewe, "VIP Suite")
    assert _moves(s) == ["Ladies -> VIP Suite"]


def test_dragged_back_is_no_move():
    s = _session()
    ewe = Animal(code="S1", species="sheep", sex="F", genes_top="GGGGG", pen="Ladies")
    s.add(ewe)
    s.commit()
    _drag(s, ewe, "Gentlemen")
    _drag(s, ewe, "Ladies")
    assert _moves(s) == []


def test_later_drag_and_sightings_are_separate_moves():
    s = _session()
    ewe = Animal(code="S1", species="sheep", sex="F", genes_top="GGGGG", pen="Ladies")
    s.add(ewe)
    s.commit()
    _drag(s, ewe, "Gentlemen")
    first = s.exec(select(Event)).one()
    first.at = datetime.now(timezone.utc) - timedelta(minutes=5)
    s.add(Event(kind="moved", animal_id=ewe.id, notes="Gentlemen -> VIP Suite (seen there)"))
    ewe.pen = "VIP Suite"
    s.commit()
    _drag(s, ewe, "VIP 2")
    assert _moves(s) == ["Ladies -> Gentlemen", "Gentlemen -> VIP Suite (seen there)", "VIP Suite -> VIP 2"]
