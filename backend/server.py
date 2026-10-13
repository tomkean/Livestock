"""Livestock backend: herd register, breeding log and screen-capture intake."""
import asyncio
import difflib
import json
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

import cv2
import numpy as np
import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from sqlmodel import Session, func, or_, select

import card_reader
import constraints
import housekeeping
import offer_value
import vendor_reader
import genetics
import inference
import planner
import pools
import settings_store
from config import BUILD_DIR, CAPTURE_DIR, CARD_DIR, DATA_DIR, NAME_DIR, PORT
from database import get_session, init_db
from models import Animal, Capture, Event, Offer, Reading


async def _housekeeping_loop():
    """Prune old capture frames now and every hour, so the data folder can't grow without limit."""
    while True:
        try:
            result = await asyncio.to_thread(housekeeping.prune_captures)
            if result["removed"]:
                print(f"housekeeping: removed {result['removed']} old captures ({result['freed_mb']} MB)")
        except Exception as e:  # never let tidying up take the server down
            print(f"housekeeping failed: {e}")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app):
    init_db()
    task = asyncio.create_task(_housekeeping_loop())
    yield
    task.cancel()


app = FastAPI(title="Livestock", lifespan=lifespan)

Box = tuple[float, float, float, float]  # x, y, w, h as fractions of the frame


# ---------------------------------------------------------------- request bodies

class CaptureCrop(BaseModel):
    capture_id: Optional[int] = None
    card_box: Optional[Box] = None
    name_box: Optional[Box] = None
    age_minutes: Optional[float] = None  # read from the card; sets born_at relative to the capture time


class AnimalIn(CaptureCrop):
    name: str = ""
    species: str
    sex: str
    origin: str = "ranch"
    genes_top: str = "?????"
    genes_bottom: Optional[str] = None
    herd_top: Optional[int] = None
    herd_bottom: Optional[int] = None
    inbred: Optional[bool] = None
    pregnant: bool = False
    mother_id: Optional[int] = None
    father_id: Optional[int] = None
    notes: str = ""
    pen: str = ""  # the building it's in


class AnimalPatch(CaptureCrop):
    name: Optional[str] = None
    pen: Optional[str] = None
    species: Optional[str] = None
    sex: Optional[str] = None
    origin: Optional[str] = None
    genes_top: Optional[str] = None
    genes_bottom: Optional[str] = None
    herd_top: Optional[int] = None
    herd_bottom: Optional[int] = None
    inbred: Optional[bool] = None
    pregnant: Optional[bool] = None
    status: Optional[str] = None
    mother_id: Optional[int] = None
    father_id: Optional[int] = None
    notes: Optional[str] = None


class Observed(BaseModel):
    species: str
    sex: str
    genes_top: str = "?????"
    genes_bottom: Optional[str] = None
    herd_top: Optional[int] = None
    herd_bottom: Optional[int] = None


class MatingIn(BaseModel):
    mother_id: int
    father_id: int
    notes: str = ""


# ---------------------------------------------------------------- helpers

CHOICES = {
    "species": genetics.SPECIES,
    "sex": ("M", "F", "?"),
    "origin": ("ranch", "bred"),
    "status": ("alive", "sold", "dead", "missing"),  # missing: wandered off; the planner ignores it until restored
}


def clean(data: dict) -> dict:
    """Validate animal fields in place. The second row is admin-only in game, so it is usually unknown (None)."""
    for field, allowed in CHOICES.items():
        if field in data and data[field] not in allowed:
            raise HTTPException(422, f"{field} must be one of {allowed}")
    try:
        for field in ("genes_top", "genes_bottom"):
            if data.get(field) is not None:
                data[field] = genetics.normalise_row(data[field])
    except ValueError as e:
        raise HTTPException(422, str(e))
    if data.get("genes_bottom") == "?" * len(genetics.GENES):
        data["genes_bottom"] = None
    if data.get("origin") == "ranch":
        data.update(mother_id=None, father_id=None)
    if "name" in data:
        data["name"] = (data["name"] or "").strip()[:40]
    return data


def last_mate(session: Session, mother_id: int) -> Optional[int]:
    """The male in the mother's most recent recorded mating."""
    event = session.exec(select(Event).where(Event.kind == "mated", Event.animal_id == mother_id)
                         .order_by(Event.at.desc())).first()
    return event.other_id if event else None


def check_animal(session: Session, animal: Animal):
    """Rules that span several fields, applied after create or update."""
    if animal.sex != "F":
        animal.pregnant = False
    for field, sex in (("mother_id", "F"), ("father_id", "M")):
        parent_id = getattr(animal, field)
        if parent_id is None:
            continue
        parent = session.get(Animal, parent_id)
        if not parent or parent.id == animal.id:
            raise HTTPException(422, f"{field} {parent_id} is not a valid animal")
        if parent.sex == "?" and parent.species == animal.species:
            parent.sex = sex  # a parent's role settles its sex (a lamb sexed by having a lamb of its own)
        elif parent.sex != sex or parent.species != animal.species:
            raise HTTPException(422, f"{field} must be a {'female' if sex == 'F' else 'male'} {animal.species}")


def log(session: Session, kind: str, animal_id=None, other_id=None, notes=""):
    session.add(Event(kind=kind, animal_id=animal_id, other_id=other_id, notes=notes))


def get_animal(session: Session, animal_id: int) -> Animal:
    animal = session.get(Animal, animal_id)
    if not animal:
        raise HTTPException(404, f"animal {animal_id} not found")
    return animal


def next_code(session: Session, species: str) -> str:
    prefix = "C" if species == "cattle" else "S"
    codes = session.exec(select(Animal.code).where(Animal.code.startswith(f"{prefix}-"))).all()
    n = max((int(c.split("-")[1]) for c in codes), default=0) + 1
    return f"{prefix}-{n:02d}"


def crop_image(capture: Capture, box: Box, out_dir) -> str:
    x, y, w, h = box
    with Image.open(CAPTURE_DIR / capture.path) as img:
        W, H = img.size
        region = img.crop((round(x * W), round(y * H), round((x + w) * W), round((y + h) * H)))
        name = f"{uuid.uuid4().hex[:12]}.png"
        region.save(out_dir / name)
    return f"{out_dir.relative_to(DATA_DIR).as_posix()}/{name}"


def apply_capture(session: Session, animal: Animal, crop: dict, learn: bool = True):
    """Cut the card and name images for an animal out of a capture, and mark the capture as used. `learn` teaches the
    marker reader the digits, so only for records a person confirmed (never from its own automatic reads)."""
    capture = session.get(Capture, crop["capture_id"])
    if not capture:
        raise HTTPException(404, f"capture {crop['capture_id']} not found")
    if crop.get("card_box"):
        animal.card_image = crop_image(capture, crop["card_box"], CARD_DIR)
    if crop.get("name_box"):
        animal.name_image = crop_image(capture, crop["name_box"], NAME_DIR)
    capture.animal_id = animal.id
    # Teach the card reader this capture's marker digits, now that a person has confirmed them.
    if learn and (animal.herd_top is not None or animal.herd_bottom is not None):
        image = cv2.imread(str(CAPTURE_DIR / capture.path))
        if image is not None:
            card_reader.learn_markers(image, animal.herd_top, animal.herd_bottom)


def split_crop(data: dict) -> dict:
    return {k: data.pop(k) for k in ("capture_id", "card_box", "name_box", "age_minutes") if k in data}


def set_birth(session: Session, animal: Animal, crop: dict):
    """born_at = when the card was captured, minus the age it showed."""
    if crop.get("age_minutes") is None:
        return
    capture = session.get(Capture, crop["capture_id"]) if crop.get("capture_id") else None
    seen = capture.at if capture else datetime.now(timezone.utc)
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    animal.born_at = seen - timedelta(minutes=crop["age_minutes"])


# ---------------------------------------------------------------- animals

def _utc(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def free_again_at(session: Session, animal: Animal):
    """When a female can breed again: her last recorded birth plus her F-based cooldown. None if not known."""
    if animal.sex != "F":
        return None
    births = [_utc(c.born_at or c.created_at) for c in
              session.exec(select(Animal).where(Animal.mother_id == animal.id)).all()]
    if not births:
        return None
    return max(births) + timedelta(minutes=genetics.FEMALE_COOLDOWN_MIN / genetics.fertility_multiplier(animal))


@app.get("/api/animals")
def list_animals(include_gone: bool = False, session: Session = Depends(get_session)):
    query = select(Animal).order_by(Animal.code)
    if not include_gone:
        query = query.where(Animal.status == "alive")
    inf = inferred(session)
    target = settings_store.load().get("target_genes") or "DLYFH"
    out = []
    lg = logic(session) if inf is not None else None
    for a in session.exec(query).all():
        row = a.model_dump(mode="json")
        free = free_again_at(session, a)
        row["free_again_at"] = free.isoformat() if free else None
        row["good_good"], row["target_chance"] = target_chance(a, target, inf)
        row["hidden"] = hidden_copies(a, inf, lg)
        out.append(row)
    return out


HIDDEN_SHOWN = 0.005  # a hidden copy below this chance counts as ruled out


def hidden_copies(a, inf: dict | None, lg: dict | None = None) -> list:
    """Per gene, the hidden (second) copies still possible under the top row, most likely first: [[letter, chance]].

    The top row shows the stronger copy, so the hidden one is never stronger than it (no G under an O or B). Live mode:
    from the inference, family included. Test-server mode: the captured second row, when there is one."""
    out = []
    for i in range(len(genetics.GENES)):
        if inf is not None and a.id in inf["posterior"]:
            dist = inf["posterior"][a.id][i]
            pairs = {}
            for pair, p in dist.items():  # pairs are written strongest first: "GO" means top G, hidden O
                pairs[pair[1]] = pairs.get(pair[1], 0.0) + p
            # Exact logic overrides sampling noise: what it rules out goes, what it proves is certain - unless this
            # animal's own family records conflict, where the logic can't be trusted until they're fixed.
            if lg and a.id in lg["domains"] and a.id not in lg["in_conflict"]:
                possible = {pair[1] for pair in lg["domains"][a.id][i]}
                pairs = {k: v for k, v in pairs.items() if k in possible}
                total = sum(pairs.values())
                pairs = {k: v / total for k, v in pairs.items()} if total else {k: 1 / len(possible) for k in possible}
            out.append(sorted(([k, round(v, 3)] for k, v in pairs.items() if v >= HIDDEN_SHOWN), key=lambda x: -x[1]))
        elif a.genes_bottom and a.genes_bottom[i] != "?":
            out.append([[a.genes_bottom[i], 1.0]])
        else:
            out.append([])
    return out


def target_chance(a, target: str, inf: dict | None):
    """Chance of Good/Good on each target gene, and on all of them at once (genes are inherited independently).

    Live mode: from the inference. Test-server mode: read straight off the captured rows (0 or 1)."""
    per_gene = {}
    for i, g in enumerate(genetics.GENES):
        if g not in target:
            continue
        if inf is not None:
            per_gene[g] = round(inf["posterior"].get(a.id, [{}] * 5)[i].get("GG", 0.0), 3)
        elif a.genes_bottom:
            per_gene[g] = float(a.genes_top[i] == "G" and a.genes_bottom[i] == "G")
        else:
            per_gene[g] = None
    if any(v is None for v in per_gene.values()):
        return per_gene, None
    total = 1.0
    for v in per_gene.values():
        total *= v
    return per_gene, float(f"{total:.3g}")  # keep tiny chances tiny, not 0 (the card shows them as <1%)


def by_name(candidates: list, now: Optional[datetime] = None):
    """The one animal a name means, now that names get reused (a lamb called Clarence while an older Clarence is
    missing). Prefers grown over lambs, then alive over missing; None when that still leaves more than one."""
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    now = now or datetime.now(timezone.utc)

    def grown(a):
        born = _utc(getattr(a, "born_at", None))
        return born is None or (now - born).total_seconds() >= planner.GROWTH * 60

    for keep in (grown, lambda a: a.status == "alive"):  # a lamb is never the one sold or the parent
        narrowed = [a for a in candidates if keep(a)]
        if len(narrowed) == 1:
            return narrowed[0]
        if narrowed:
            candidates = narrowed
    return None


def _same_animal(session: Session, data: dict) -> Optional[Animal]:
    """An animal already in the herd with this name, species, top row and first marker: a second capture of it."""
    name = (data.get("name") or "").strip().lower()
    if not name:
        return None
    for a in session.exec(select(Animal).where(Animal.status.in_(["alive", "missing"]),
                                               Animal.species == data.get("species"))).all():
        if (a.name or "").strip().lower() != name:
            continue
        top = data.get("genes_top") or "?????"
        if any(x != "?" and y != "?" and x != y for x, y in zip(top, a.genes_top)):
            continue
        if data.get("herd_top") is not None and a.herd_top is not None and data["herd_top"] != a.herd_top:
            continue
        return a
    return None


@app.post("/api/animals")
def create_animal(body: AnimalIn, session: Session = Depends(get_session), auto: bool = False):
    data = body.model_dump()
    crop = split_crop(data)
    same = _same_animal(session, data)
    if same is not None:
        # The same card captured twice (names haven't repeated yet): update the animal already in the herd.
        for field in ("mother_id", "father_id"):
            if getattr(same, field, None) is None and data.get(field) is not None:
                setattr(same, field, data[field])
        if same.origin != "bred" and data.get("origin") == "bred":
            same.origin = "bred"
        if same.sex == "?" and data.get("sex") in ("M", "F"):
            same.sex = data["sex"]
        if data.get("pen") and data["pen"] != same.pen:
            log(session, "moved", same.id, notes=f"{same.pen or 'unplaced'} -> {data['pen']}")
            same.pen = data["pen"]
        if same.status == "missing":
            same.status = "alive"
            log(session, "alive", same.id, notes="found")
        if crop.get("capture_id"):
            apply_capture(session, same, crop, learn=not auto)
        if same.born_at is None:
            set_birth(session, same, crop)
        log(session, "captured", same.id, notes="captured again (not a new animal)")
        session.commit()
        session.refresh(same)
        return same
    animal = Animal(**clean(data), code=next_code(session, data["species"]))
    animal.name = animal.name or animal.code
    if animal.origin == "bred" and animal.mother_id is not None:
        # Both parents are needed to infer hidden genes, so fill the father from the breeding log.
        if animal.father_id is None:
            animal.father_id = last_mate(session, animal.mother_id)
        mother = session.get(Animal, animal.mother_id)
        if mother and mother.pregnant:
            mother.pregnant = False
    session.add(animal)
    session.flush()
    check_animal(session, animal)
    if crop.get("capture_id"):
        apply_capture(session, animal, crop, learn=not auto)
    set_birth(session, animal, crop)
    log(session, "born" if animal.origin == "bred" else "bought", animal.id, animal.mother_id)
    session.commit()
    session.refresh(animal)
    return animal


@app.patch("/api/animals/{animal_id}")
def update_animal(animal_id: int, body: AnimalPatch, session: Session = Depends(get_session)):
    animal = get_animal(session, animal_id)
    data = body.model_dump(exclude_unset=True)
    crop = split_crop(data)
    if "origin" not in data and animal.origin == "ranch":
        data["origin"] = "ranch"
    if data.get("sex", animal.sex) == "M":
        data["pregnant"] = False
    changed = []
    old_pen = animal.pen
    for field, value in clean(data).items():
        if getattr(animal, field) != value:
            setattr(animal, field, value)
            changed.append(field)
    check_animal(session, animal)
    if "pen" in changed:  # the moves log is how the parent finder knows who was where
        _log_move(session, animal, old_pen)
        changed.remove("pen")
        if animal.pen and animal.status == "missing":
            animal.status = "alive"  # put in a building: found
            log(session, "alive", animal.id, notes=f"placed in {animal.pen}")
    if "pregnant" in changed:
        log(session, "pregnant" if animal.pregnant else "not_pregnant", animal.id)
    if "status" in changed:
        log(session, animal.status, animal.id)
    if not animal.name:
        animal.name = animal.code
    edits = [f for f in changed if f not in ("pregnant", "status")]
    if edits:
        log(session, "edited", animal.id, notes=", ".join(edits))
    if crop.get("capture_id"):
        apply_capture(session, animal, crop)
        log(session, "captured", animal.id)
        if animal.status == "missing":  # seen again
            animal.status = "alive"
            log(session, "alive", animal.id, notes="found")
    set_birth(session, animal, crop)
    session.commit()
    session.refresh(animal)
    return animal


class ChildIn(Observed):
    id: Optional[int] = None  # the animal itself, when it is already in the herd
    name: str = ""  # "X Junior" / "X the 3rd" names one parent
    pen: str = ""  # the building it was found in: its parents were most likely there too


_inference_cache: dict = {}


def live_mode() -> bool:
    return not settings_store.load().get("second_row_visible", False)


def visible(a):
    """What a player sees on a live server: the card's top row and first marker, nothing underneath."""
    view = SimpleNamespace(**(a.model_dump() if hasattr(a, "model_dump") else vars(a)))
    if live_mode():
        view.genes_bottom = None
        # An inbred card (red INBRED label) says the hidden herd number is the same as the one shown.
        view.herd_bottom = view.herd_top if (getattr(view, "herd_bottom", None) == view.herd_top
                                             or getattr(view, "inbred", None)) else None
    return view


def inferred(session: Session) -> dict | None:
    """Inference over the whole recorded family tree (all species, all statuses), cached until anything changes.
    None in test-server mode, where the captured second rows are used directly."""
    if not live_mode():
        return None
    animals = [visible(a) for a in session.exec(select(Animal)).all()]
    key = tuple((a.id, a.genes_top, a.mother_id, a.father_id) for a in animals)
    if _inference_cache.get("key") != key:
        _inference_cache.update(key=key, result=inference.infer(animals), logic=constraints.closure(animals))
    return _inference_cache["result"]


def logic(session: Session) -> Optional[dict]:
    """The exact logic pass over the family tree (see constraints.py), computed with the inference."""
    inferred(session)
    return _inference_cache.get("logic")


_MOVE = re.compile(r"^(.*?) -> (.*?)(?: \(seen there\))?$")
DRAG_MERGE_SECONDS = 30  # a second drag this soon after the first is one move made in steps (drag, scroll, drag)


def _log_move(session: Session, animal: Animal, old_pen: str) -> None:
    """Log a move the player made. A drag that has to stop on the way (to scroll the page) drops the sheep in a room
    for a moment that it was never in: a follow-on drag within DRAG_MERGE_SECONDS joins the first into one move, so
    the room history never shows the stopover (it could make a ram look like a lamb's father)."""
    now = datetime.now(timezone.utc)
    last = session.exec(select(Event).where(Event.kind == "moved", Event.animal_id == animal.id)
                        .order_by(Event.at.desc())).first()
    step = _MOVE.match(last.notes) if last else None
    if (step and not last.notes.endswith("(seen there)") and step.group(2) == (old_pen or "unplaced")
            and (now - _utc(last.at)).total_seconds() <= DRAG_MERGE_SECONDS):
        start = step.group(1)
        if start == (animal.pen or "unplaced"):
            session.delete(last)  # dragged back where it started: no move at all
        else:
            last.notes, last.at = f"{start} -> {animal.pen or 'unplaced'}", now
            session.add(last)
        return
    log(session, "moved", animal.id, notes=f"{old_pen or 'unplaced'} -> {animal.pen or 'unplaced'}")


def pens_at(session: Session, when: datetime) -> dict[int, str]:
    """Which building every animal was in at a given time: its current one, with later moves undone."""
    pens = {a.id: a.pen for a in session.exec(select(Animal)).all()}
    later = session.exec(select(Event).where(Event.kind == "moved", Event.at > when).order_by(Event.at.desc())).all()
    for e in later:  # newest first, so the last one undone is the first move after `when`
        m = _MOVE.match(e.notes or "")
        if m and e.animal_id in pens:
            pens[e.animal_id] = "" if m.group(1) in ("unplaced", "not placed") else m.group(1)
    return pens


def _gone_since(session: Session) -> dict[int, datetime]:
    """When each animal left: sold or dead, or marked missing and not found since (a missing ewe's last room still says
    VIP 2, but she isn't there - Shelby the 7th's mother was left blank because Susie and Bana still 'counted')."""
    gone = {}
    for a in session.exec(select(Animal).where(Animal.status.in_(["sold", "dead", "missing"]))):
        kinds = ["missing"] if a.status == "missing" else ["sold", "dead"]
        last = session.exec(select(Event).where(Event.animal_id == a.id, Event.kind.in_(kinds))
                            .order_by(Event.at.desc())).first()
        if last is not None:
            gone[a.id] = _utc(last.at)
    return gone


def _parents(session: Session, child) -> list[dict]:
    # Conceived 10 minutes before birth. Birth time unknown: when it was first registered, or now for a fresh capture.
    born = _utc(getattr(child, "born_at", None) or getattr(child, "created_at", None) or datetime.now(timezone.utc))
    conceived = born - timedelta(minutes=planner.GESTATION)
    # Sold, dead and missing animals can be parents of lambs conceived before they went, but not after.
    gone_at = _gone_since(session)
    animals = [visible(a) for a in session.exec(select(Animal)).all()
               if a.status not in ("sold", "dead", "missing") or gone_at.get(a.id, conceived) >= conceived]
    for a in animals:  # bred here and captured as a lamb: registered within the hour it was born
        if a.born_at is None and a.origin == "bred":
            a.born_at = a.created_at
    mated = {(e.animal_id, e.other_id) for e in session.exec(select(Event).where(Event.kind == "mated"))}
    inf = inferred(session)
    # Where everyone was when it was conceived (the father was with the mother then) and when it was born (beside its
    # mother). A ewe moved between harems while pregnant still points at her old harem's ram.
    # Birth times come from the card's age, so conception is checked over a few minutes either side.
    slack = timedelta(minutes=CONCEPTION_SLACK_MINUTES)
    around = [pens_at(session, conceived + timedelta(minutes=k))
              for k in range(-CONCEPTION_SLACK_MINUTES, CONCEPTION_SLACK_MINUTES + 1)]
    now_pens = pens_at(session, born)
    pen = getattr(child, "pen", "") or ""
    # A ewe seen pregnant between conception and birth: the ram in her room when she was seen is the father's best
    # clue, and the lamb may be found anywhere (wandered or moved before its card was read). A ewe seen pregnant in
    # the 41 minutes before conception was pregnant or resting: she can't be the mother.
    sighted, busy = {}, set()
    for e in session.exec(select(Event).where(Event.kind == "pregnant")):
        at = _utc(e.at)
        if conceived - slack <= at <= born + slack:
            sighted.setdefault(e.animal_id, at)
        elif conceived - timedelta(minutes=EWE_MIN_REST_MINUTES) <= at < conceived - slack:
            busy.add(e.animal_id)
    with_her = {m_id: pens_at(session, at) for m_id, at in sighted.items()}

    def places(m, f):
        if m.id in busy:
            return False, False
        together = any(p.get(m.id) and p.get(m.id) == p.get(f.id) for p in around)
        if m.id in with_her:
            seen = with_her[m.id]
            together = together or bool(seen.get(m.id)) and seen.get(m.id) == seen.get(f.id)
        mother_there = not pen or now_pens.get(m.id) == pen or m.id in sighted
        return together, mother_there
    child_view = visible(child)
    child_view.born_at = born  # so parents too young for it are ruled out, even for a lamb just captured
    # A name like "Dianna the 3rd" says who one parent is (Dianna Junior); only the other one needs finding.
    known = None
    parent_name = genetics.named_parent(getattr(child, "name", None))
    if parent_name:
        matches = [a for a in animals if (a.name or "").lower() == parent_name.lower()
                   and a.species == child.species and a.id != getattr(child, "id", None)]
        parent = by_name(matches, born)
        if parent is not None:
            known = parent.id
    return genetics.likely_parents(child_view, animals, mated, dists=inf["posterior"] if inf else None,
                                   places=places, known_parent=known)


@app.post("/api/parents")
def find_parents(child: ChildIn, session: Session = Depends(get_session)):
    """Which pairs in the herd could have produced an animal with this card, most likely first."""
    return _parents(session, child)


@app.get("/api/animals/{animal_id}/parents")
def find_animal_parents(animal_id: int, session: Session = Depends(get_session)):
    return _parents(session, get_animal(session, animal_id))


@app.delete("/api/animals/{animal_id}")
def delete_animal(animal_id: int, session: Session = Depends(get_session)):
    """Remove a record entered by mistake (a duplicate, a wrong capture). Real departures use status sold/dead.

    Its log entries go with it; offspring keep their records but lose the link to it; its capture returns to
    the pending list so it can be used again or discarded.
    """
    animal = get_animal(session, animal_id)
    for event in session.exec(select(Event).where(or_(Event.animal_id == animal_id, Event.other_id == animal_id))):
        # A mating needs both animals; any other event belongs to its own animal (e.g. a lamb's birth) and stays.
        if event.animal_id == animal_id or event.kind == "mated":
            session.delete(event)
        else:
            event.other_id = None
    for child in session.exec(select(Animal).where(or_(Animal.mother_id == animal_id, Animal.father_id == animal_id))):
        if child.mother_id == animal_id:
            child.mother_id = None
        if child.father_id == animal_id:
            child.father_id = None
    for capture in session.exec(select(Capture).where(Capture.animal_id == animal_id)):
        capture.animal_id = None
    for reading in session.exec(select(Reading).where(Reading.animal_id == animal_id)):
        session.delete(reading)  # its conditions history goes with it
    for offer in session.exec(select(Offer).where(Offer.animal_id == animal_id)):
        offer.animal_id = None  # the vendor's offers stay as price data
    for image in (animal.card_image, animal.name_image):
        if image:
            (DATA_DIR / image).unlink(missing_ok=True)
    session.flush()
    session.delete(animal)
    session.commit()
    return {"deleted": animal.code}


@app.post("/api/animals/match")
def match_animals(observed: Observed, session: Session = Depends(get_session)):
    """Existing animals a captured card could belong to, best first."""
    # A lamb is captured as unsexed and a wandered-off animal is marked missing, so neither may rule out a match.
    sexes = ["M", "F", "?"] if observed.sex == "?" else [observed.sex, "?"]
    animals = session.exec(select(Animal).where(
        Animal.status.in_(["alive", "missing"]), Animal.species == observed.species, Animal.sex.in_(sexes))).all()
    scored = [(genetics.match_score(a, observed), a) for a in animals]
    scored = sorted(((s, a) for s, a in scored if s), key=lambda sa: -sa[0])
    return [{"score": s, "animal": a} for s, a in scored[:5]]


# ---------------------------------------------------------------- breeding log

def get_pair(session: Session, mother_id: int, father_id: int) -> tuple[Animal, Animal]:
    mother = get_animal(session, mother_id)
    father = get_animal(session, father_id)
    if mother.sex != "F" or father.sex != "M":
        raise HTTPException(422, "mother must be female and father male")
    if mother.species != father.species:
        raise HTTPException(422, "parents must be the same species")
    return mother, father


@app.get("/api/odds")
def mating_odds(mother_id: int, father_id: int, session: Session = Depends(get_session)):
    """Odds for one offspring of a possible mating."""
    mother, father = get_pair(session, mother_id, father_id)
    inf = inferred(session)
    return genetics.mating_odds(visible(mother), visible(father), inf["posterior"] if inf else None)


@app.post("/api/matings")
def record_mating(body: MatingIn, session: Session = Depends(get_session)):
    mother, father = get_pair(session, body.mother_id, body.father_id)
    p_inbred = genetics.mating_odds(visible(mother), visible(father))["p_inbred"]
    note = f" [inbred chance {p_inbred:.0%}]" if p_inbred else ""
    log(session, "mated", mother.id, father.id, body.notes + note)
    session.commit()
    return {"p_inbred": p_inbred}


@app.get("/api/plan")
def breeding_plan(species: str = "sheep", runs: int = 150, session: Session = Depends(get_session)):
    """The fastest route from the current herd to a god male, by simulation. Takes several seconds."""
    if species not in genetics.SPECIES:
        raise HTTPException(422, f"species must be one of {genetics.SPECIES}")
    animals = session.exec(select(Animal).where(Animal.status == "alive", Animal.species == species)).all()
    now = datetime.now(timezone.utc)
    herd = []
    for a in animals:
        view = visible(a)
        if a.sex not in ("M", "F"):
            continue  # a lamb not yet sexed can't be planned with
        born = a.born_at
        if born is None and a.origin == "bred":
            born = a.created_at  # the record was made around the birth
        if born is not None and born.tzinfo is None:
            born = born.replace(tzinfo=timezone.utc)
        view.age_minutes = (now - born).total_seconds() / 60 if born else None
        free = free_again_at(session, a)
        view.free_in_minutes = max(0.0, (free - now).total_seconds() / 60) if free else 0.0
        herd.append(view)
    if not any(a.sex == "F" for a in herd) or not any(a.sex == "M" for a in herd):
        return {"possible": False, "missing": [], "reason": "The herd needs at least one female and one male."}
    settings = settings_store.load()
    return planner.plan(herd, runs=max(20, min(runs, 400)), keep=settings.get("pen_capacity") or {},
                        target=settings.get("target_genes") or "DLYFH", inferred=inferred(session))


@app.get("/api/trip")
def barn_trip(species: str = "sheep", keep_ids: str = "", session: Session = Depends(get_session)):
    """What to sell and buy on the next trip to the barn, within what the truck carries.

    keep_ids: comma-separated animals the latest plan wants to mate, which are never offered for sale.
    """
    planned = {int(x) for x in keep_ids.split(",") if x.strip().isdigit()}
    settings = settings_store.load()
    now = datetime.now(timezone.utc)
    animals = []
    for a in session.exec(select(Animal).where(Animal.status == "alive", Animal.species == species)).all():
        view = visible(a)
        born = _utc(a.born_at)
        view.is_lamb = a.sex == "?" or (born is not None and (now - born).total_seconds() < planner.GROWTH * 60)
        animals.append(view)
    inf = inferred(session)
    return planner.trip_plan(animals, species, settings.get("vehicle", "small"), settings.get("pen_capacity") or {}, planned,
                             settings.get("target_genes") or "DLYFH", inf["posterior"] if inf else None)


def _pools_view(session: Session, species: str) -> tuple[list, dict]:
    settings = settings_store.load()
    cfg = settings.get("pools") or {}
    now = datetime.now(timezone.utc)
    animals = []
    for a in session.exec(select(Animal).where(Animal.status == "alive", Animal.species == species)).all():
        view = visible(a)
        born = _utc(a.born_at)
        view.is_lamb = a.sex == "?" or (born is not None and (now - born).total_seconds() < planner.GROWTH * 60)
        animals.append(view)
    inf = inferred(session)
    result = pools.arrange(animals, settings.get("target_genes") or "DLYFH", inf["posterior"] if inf else None,
                           cfg.get("harems") or ["Harem #1", "Harem #2"], cfg.get("holding") or "Death Row",
                           int(cfg.get("harem_ewes") or 5), int(cfg.get("holding_size") or 4),
                           previous=_last_plan.get(species), harem_sizes=cfg.get("harem_sizes") or {},
                           holding_by_sex=cfg.get("holding_by_sex"), reject_room=cfg.get("reject_room"),
                           goal=settings.get("goal") or "god")
    result["quiet"] = _quiet_harems(session, cfg.get("harems") or [], now)
    # Remember this plan's rams and promotions, so the next one sticks with them unless something is clearly better.
    _last_plan[species] = ({h["ram"] for h in result["harems"].values() if h["ram"]}
                           | {i for i, v in result["verdicts"].items() if v["verdict"] == "promote"})
    return animals, {**result, "config": cfg}


_last_plan: dict = {}  # species -> ids the last plan made harem rams or promoted

QUIET_MINUTES = 30


def _quiet_harems(session: Session, harems: list, now: datetime) -> dict:
    """Harems where nothing has happened for a while although a ewe is ready. Mating seems to start when animals come
    together (a ram arriving), not while a settled group stands about, so a quiet harem can need its ram moved."""
    out = {}
    grown = lambda a: a.born_at is None or (now - _utc(a.born_at)).total_seconds() >= planner.GROWTH * 60  # noqa: E731
    for h in harems:
        inside = session.exec(select(Animal).where(Animal.status == "alive", Animal.pen == h)).all()
        rams = [a for a in inside if a.sex == "M" and grown(a)]
        if not rams:
            continue
        ready = []
        for e in inside:
            if e.sex != "F" or e.pregnant or not grown(e) or (e.overall is not None and e.overall < 70):
                continue
            free = free_again_at(session, e)
            if free is None or _utc(free) <= now:
                ready.append(e.name or e.code)
        if not ready:
            continue
        ids = [a.id for a in inside]
        last = session.exec(select(func.max(Event.at)).where(Event.animal_id.in_(ids), or_(
            Event.kind == "pregnant", (Event.kind == "moved") & Event.animal_id.in_([r.id for r in rams])))).first()
        last = _utc(last) if last else None
        minutes = (now - last).total_seconds() / 60 if last else None
        if minutes is None or minutes >= QUIET_MINUTES:
            out[h] = {"minutes": round(minutes) if minutes is not None else None, "ready": ready}
    return out


@app.get("/api/pools")
def pools_plan(species: str = "sheep", session: Session = Depends(get_session)):
    """Suggested rooms for every animal (harems + holding), the moves from where they are now, and verdicts."""
    animals, result = _pools_view(session, species)
    _rams_wait_while_ewes_busy(session, animals, result)
    current = {a.id: a.pen for a in animals}
    result["moves"] = [{"id": a.id, "name": a.name or a.code, "from": current[a.id] or None, "to": result["pen"][a.id]}
                       for a in animals if current[a.id] != result["pen"][a.id]]
    result["cull_order"] = _cull_order(animals, result)
    result["reserve_status"] = _reserve_status(session, result)
    return result


RESERVE_UNSEEN_HOURS = 2


def _reserve_status(session: Session, result: dict) -> list[dict]:
    """The god reserve (production mode): where each one is, how it's doing, and how long since it was seen - the
    animals the whole line depends on, so a death or a starving one should be noticed early."""
    now = datetime.now(timezone.utc)
    out = []
    breeding = {i: h for h, x in result["harems"].items() for i in [x["ram"], *x["ewes"]] if i}
    for i in result.get("reserve", []):
        a = session.get(Animal, i)
        if a is None:
            continue
        seen = _utc(a.seen_at)
        born = _utc(a.born_at)
        hours_unseen = round((now - seen).total_seconds() / 3600, 1) if seen else None
        left = pools.hours_left(a, now)
        out.append({"id": a.id, "name": a.name or a.code, "sex": a.sex, "room": a.pen, "breeding": breeding.get(a.id),
                    "hours_left": round(left, 1) if left is not None else None, "inbred": a.inbred,
                    "age_hours": round((now - born).total_seconds() / 3600, 1) if born else None,
                    "overall": a.overall, "food": a.food, "unseen_hours": hours_unseen,
                    "warn": (hours_unseen is None or hours_unseen > RESERVE_UNSEEN_HOURS
                             or (left is not None and left < pools.RESERVE_HOURS_LEFT)
                             or (a.overall is not None and a.overall < 30))})
    return out


def _cull_order(animals: list, result: dict) -> list[dict]:
    """Who to remove first when the farm is overcrowded. Animals the plan has no use for go first - poor wool before
    good (Y is wool), least valuable first - then spares kept for breeding. Never listed: breeding pairs, lambs
    promoted for a future pair, the only carrier of a Good copy, pregnant ewes."""
    y = genetics.GENES.index("Y")
    wool_goal = (settings_store.load().get("goal") or "god") == "wool"
    breeding = {i for h in result["harems"].values() for i in [h["ram"], *h["ewes"]] if i}
    value = result.get("value", {})
    ranked = []
    for a in animals:
        v = result["verdicts"].get(a.id) or result["verdicts"].get(str(a.id)) or {}
        if (a.id in breeding or a.pregnant or v.get("verdict") == "promote" or "only carrier" in v.get("reason", "")
                or a.id in result.get("reserve", [])):
            continue
        unwanted = v.get("verdict") in ("reject", "sell", "cull")
        if not unwanted and v.get("verdict") != "keep":
            continue
        good_wool = a.genes_top[y] == "G" and not (wool_goal and getattr(a, "inbred", None))
        group = (0 if not good_wool else 1) if unwanted else 2
        if wool_goal:  # production: least wool first, whatever the verdict
            group = pools.wool_per_shear(a)
        why = ("not useful for mating" + ("" if good_wool else ", poor wool")) if unwanted else "spare for breeding"
        if wool_goal:
            why = f"{pools.wool_per_shear(a)} wool per shear" + (" (inbred)" if getattr(a, "inbred", None) else "")
        ranked.append(((group, value.get(a.id, 0)), {"id": a.id, "name": a.name or a.code, "room": a.pen, "why": why}))
    return [entry for _, entry in sorted(ranked, key=lambda r: r[0])]


def _rams_wait_while_ewes_busy(session: Session, animals: list, result: dict):
    """A harem's ram waits in the rams' room while one of its ewes is pregnant or there are lambs in the room: left
    there, he'd be with the lambs when they grow up and could breed them - an untraceable mess by the time you're back.
    A ewe merely resting after lambing is no risk, so he can go in early to wait for her."""
    now = datetime.now(timezone.utc)
    by_id = {a.id: a for a in animals}
    cfg = settings_store.load().get("pools") or {}
    wait_room = (cfg.get("holding_by_sex") or {}).get("M")
    if not wait_room:
        return
    last_pregnant = {}
    for e in session.exec(select(Event).where(Event.kind == "pregnant").order_by(Event.at)):
        last_pregnant[e.animal_id] = _utc(e.at)
    result.setdefault("ram_waits", {})
    for harem, h in result["harems"].items():
        ram = by_id.get(h["ram"])
        if ram is None:
            continue
        pregnant = [a for a in animals if a.pen == harem and a.sex == "F" and a.pregnant]
        lambs = [a for a in animals if a.pen == harem and getattr(a, "is_lamb", False)]
        if not pregnant and not lambs:
            continue
        result["pen"][ram.id] = wait_room
        due = [last_pregnant[e.id] + timedelta(minutes=planner.GESTATION) for e in pregnant if e.id in last_pregnant]
        why = (f"{pregnant[0].name or pregnant[0].code} is pregnant" if pregnant else
               f"lamb{'s' if len(lambs) > 1 else ''} in the room ({', '.join(l.name or l.code for l in lambs)})")
        result["ram_waits"][harem] = {"ram": ram.id, "room": wait_room, "why": why,
                                      "until": max(due).isoformat() if due and not lambs else None}
        result.setdefault("verdicts", {})[ram.id] = {
            "verdict": "keep",
            "reason": f"waits in {wait_room} until " + (
                f"{pregnant[0].name or pregnant[0].code} has lambed" if pregnant else
                f"{', '.join(l.name or l.code for l in lambs)} {'are' if len(lambs) > 1 else 'is'} out of {harem}")}


@app.get("/api/animals/{animal_id}/readings")
def animal_readings(animal_id: int, limit: int = 200, session: Session = Depends(get_session)):
    """Conditions history from automatic capture, newest first."""
    return session.exec(select(Reading).where(Reading.animal_id == animal_id)
                        .order_by(Reading.at.desc()).limit(limit)).all()


@app.get("/api/records/conflicts")
def record_conflicts(session: Session = Depends(get_session)):
    """Lambs whose recorded parents can't all be right: no hidden copies could explain the lamb's card from theirs."""
    lg = logic(session)
    if not lg:
        return []
    names = {a.id: a for a in session.exec(select(Animal)).all()}
    seen, out = set(), []
    for child, g, mother, father in lg["conflicts"]:
        if child in seen:
            continue
        seen.add(child)
        c, m, f = names.get(child), names.get(mother), names.get(father)
        out.append({"id": child, "name": c.name if c else "?", "gene": genetics.GENES[g], "top": c.genes_top if c else "",
                    "mother": {"id": m.id, "name": m.name, "top": m.genes_top} if m else None,
                    "father": {"id": f.id, "name": f.name, "top": f.genes_top} if f else None})
    return out


RAM_REST_MINUTES = {"G": 6.25, "O": 10.0, "B": 15.4}  # after mating, by the ram's shown F (published)
UPCOMING_OVERDUE_MINUTES = 30  # keep showing an event this long after it was due


@app.get("/api/upcoming")
def upcoming(session: Session = Depends(get_session)):
    """What happens next on the farm, soonest first: lambs due, lambs growing up, ewes and rams ready to breed again."""
    now = datetime.now(timezone.utc)
    oldest = now - timedelta(minutes=UPCOMING_OVERDUE_MINUTES)
    alive = session.exec(select(Animal).where(Animal.status == "alive")).all()
    events = []

    def add(at, kind, animal, text):
        if at is not None and _utc(at) >= oldest:
            events.append({"at": _utc(at).isoformat(), "kind": kind, "id": animal.id,
                           "name": animal.name or animal.code, "room": animal.pen, "text": text})

    last_pregnant = {}
    for e in session.exec(select(Event).where(Event.kind == "pregnant").order_by(Event.at)):
        last_pregnant[e.animal_id] = _utc(e.at)
    for a in alive:
        name = a.name or a.code
        if a.sex == "F" and a.pregnant and a.id in last_pregnant:
            add(last_pregnant[a.id] + timedelta(minutes=planner.GESTATION), "lamb", a, f"{name}'s lamb due")
        born = _utc(a.born_at)
        if born is not None and now - born < timedelta(minutes=planner.GROWTH):
            grown = born + timedelta(minutes=planner.GROWTH)
            if a.sex == "M":
                add(grown, "grown", a, f"{name} grows up - out of the ewes' rooms before then")
            else:
                add(grown, "grown", a, f"{name} grows up" + (" - can breed after this" if a.sex == "F" else " - check horns"))
        if a.sex == "F" and not a.pregnant:
            free = free_again_at(session, a)
            if free is not None and _utc(free) > now:
                add(free, "free", a, f"{name} can breed again")
    # A ram rests after each mating: his last is the latest pregnancy of a ewe he was with at the time.
    rams = [a for a in alive if a.sex == "M"]
    for ewe_id, at in last_pregnant.items():
        if at < now - timedelta(minutes=30):
            continue
        pens = pens_at(session, at)
        with_her = [r for r in rams if pens.get(r.id) and pens.get(r.id) == pens.get(ewe_id)]
        if len(with_her) == 1:
            r = with_her[0]
            rest = RAM_REST_MINUTES.get(r.genes_top[genetics.GENES.index("F")], 10.0)
            if at + timedelta(minutes=rest) > now:
                add(at + timedelta(minutes=rest), "ram", r, f"{r.name or r.code} ready again")
    events.sort(key=lambda e: e["at"])
    return events


@app.get("/api/events")
def list_events(animal_id: Optional[int] = None, limit: int = 500, session: Session = Depends(get_session)):
    query = select(Event).order_by(Event.at.desc()).limit(limit)
    if animal_id is not None:
        query = query.where(or_(Event.animal_id == animal_id, Event.other_id == animal_id))
    return session.exec(query).all()


# ---------------------------------------------------------------- settings

@app.get("/api/settings")
def get_settings():
    return settings_store.load()


@app.put("/api/settings")
async def put_settings(changes: dict):
    saved = settings_store.save(changes)
    if "location" in changes:  # every open app shows where the player is
        await hub.broadcast({"type": "location", "location": saved.get("location") or ""})
    return saved


# ---------------------------------------------------------------- captures

@app.get("/api/captures")
def pending_captures(session: Session = Depends(get_session)):
    return session.exec(select(Capture).where(
        Capture.animal_id.is_(None), Capture.dismissed == False).order_by(Capture.at.desc())).all()  # noqa: E712


@app.post("/api/captures")
async def upload_capture(file: UploadFile = File(...), session: Session = Depends(get_session)):
    name = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.jpg"
    path = CAPTURE_DIR / name
    path.write_bytes(await file.read())
    try:
        with Image.open(path) as img:
            width, height = img.size
    except Exception:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "upload is not an image")
    capture = Capture(path=name, width=width, height=height, location=settings_store.load().get("location") or "")
    session.add(capture)
    session.commit()
    session.refresh(capture)
    await hub.broadcast({"type": "capture_ready", "capture": capture.model_dump(mode="json")})
    return capture


@app.get("/api/captures/{capture_id}/read")
def read_capture(capture_id: int, session: Session = Depends(get_session)):
    """What the card in a capture shows, read automatically. Values that couldn't be read come back as ? or null."""
    capture = session.get(Capture, capture_id)
    if not capture:
        raise HTTPException(404, f"capture {capture_id} not found")
    image = cv2.imread(str(CAPTURE_DIR / capture.path))
    if image is None:
        raise HTTPException(404, "capture image is missing")
    return card_reader.read_card(image)


PREGNANCY_ECHO_SECONDS = 40 * 60  # after a lamb, a "Pregnant" on the mother's card is the label lingering
READING_EVERY_SECONDS = 600  # history keeps every change, plus one reading per 10 minutes when nothing changes
_auto_seen: dict = {}  # card signature -> (time, conditions): skip repeats of the same view
AUTO_REPEAT_SECONDS = 30
AUTO_NEW_COOLDOWN_SECONDS = 600  # a new, unmatched animal is filed as a capture at most this often


def _signature(reading: dict) -> str:
    return f"{reading.get('name') or ''}|{reading['genes_top']}|{reading.get('herd_top')}"


def _match_reading(session: Session, reading: dict) -> Optional[Animal]:
    """The herd animal a card belongs to: same name (when read) and same top row and first marker."""
    candidates = session.exec(select(Animal).where(Animal.status.in_(["alive", "missing"]))).all()
    name = (reading.get("name") or "").lower()
    top, herd = reading["genes_top"], reading.get("herd_top")

    def fits(a):
        same_genes = all(r == "?" or r == g for r, g in zip(top, a.genes_top))
        return same_genes and (herd is None or a.herd_top is None or a.herd_top == herd)
    named = [a for a in candidates if name and name in ((a.name or "").lower(), (a.card_name or "").lower()) and fits(a)]
    if len(named) == 1:
        return named[0]
    unnamed = [a for a in candidates if fits(a) and "?" not in top and herd is not None and a.herd_top == herd]
    return unnamed[0] if len(unnamed) == 1 and not name else None


FARM = "Farm"  # "Where am I?": somewhere on the farm, room unknown - watch, but never move anyone between rooms


def _buildings() -> list[str]:
    cfg = settings_store.load().get("pools") or {}
    holding = cfg.get("holding") or []
    return list(cfg.get("harems") or []) + ([holding] if isinstance(holding, str) else list(holding))


CONCEPTION_SLACK_MINUTES = 5  # birth times come from the card's age in whole minutes, so conception is +/- a few


def _other_parent(session: Session, known: Animal, conceived: datetime) -> Optional[Animal]:
    """The one adult of the other sex that was with the known parent around the time the lamb was conceived, if there
    was exactly one (a harem's ram, say). Checked across a few minutes either side, since the birth time is only as
    good as the card's age. None when it's ambiguous: better a blank than a wrong parent."""
    gone = _gone_since(session)
    want = "M" if known.sex == "F" else "F"
    candidates = session.exec(select(Animal).where(Animal.species == known.species, Animal.sex == want)).all()
    found = set()
    for minutes in range(-CONCEPTION_SLACK_MINUTES, CONCEPTION_SLACK_MINUTES + 1):
        when = conceived + timedelta(minutes=minutes)
        pens = pens_at(session, when)
        where = pens.get(known.id)
        if not where:
            continue
        for a in candidates:
            if pens.get(a.id) != where or (a.id in gone and gone[a.id] < when):
                continue
            born = _utc(a.born_at)
            if born is not None and (when - born).total_seconds() < planner.GROWTH * 60:
                continue  # still a lamb then
            found.add(a.id)
    return session.get(Animal, found.pop()) if len(found) == 1 else None


EWE_MIN_REST_MINUTES = 41  # the shortest rest after lambing (Good F): a ewe seen pregnant this recently can't conceive
AUTO_PARENTS_CHANCE = 0.8  # a lamb whose name names no parent gets the top pair only when it is this sure...
AUTO_PARENTS_LEAD = 5.0  # ...and this many times likelier than the next pair


def _auto_register(session: Session, reading: dict, frame, now: datetime) -> Optional[Animal]:
    """Register an animal seen for the first time from a clean read of its card, so the player doesn't have to.

    Needs a confident name, every top gene and the marker. Species from the portrait; a lamb is bred here, an adult
    arriving is bought or tamed. Sex from the parent its name points to, else from an English first name, else
    unknown. One parent from the name, the other only when the building records leave no doubt. Anything less clean
    is filed as a pending capture for a person instead."""
    name = (reading.get("name") or "").strip()
    if not name or "?" in reading["genes_top"] or reading.get("herd_top") is None:
        return None
    lamb = bool(reading.get("lamb"))
    parent = None
    parent_name = genetics.named_parent(name)
    if parent_name and (settings_store.load().get("location") or FARM) != "Vendor":  # a bought lamb's namesake isn't ours
        named = session.exec(select(Animal).where(func.lower(Animal.name) == parent_name.lower())).all()
        parent = by_name(list(named), now)
    species = reading.get("species") or (parent.species if parent else "sheep")
    if parent is not None and parent.species != species:
        parent = None
    sex = parent.sex if parent is not None and parent.sex in ("M", "F") else (reading.get("sex_guess") or "?")
    here = settings_store.load().get("location") or FARM
    file = f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.jpg"
    cv2.imwrite(str(CAPTURE_DIR / file), frame)
    capture = Capture(path=file, width=frame.shape[1], height=frame.shape[0], location=here)
    session.add(capture)
    session.flush()
    bought = here == "Vendor"  # first seen at the barn: just bought, on its way to the room for its sex
    data = {"name": name, "species": species, "sex": sex,
            "origin": "ranch" if bought else ("bred" if (lamb or parent) else "ranch"),
            "genes_top": reading["genes_top"], "genes_bottom": reading.get("genes_bottom"),
            "herd_top": reading.get("herd_top"), "herd_bottom": reading.get("herd_bottom"),
            "inbred": reading.get("inbred"),
            "pen": here if here in _buildings() else ""}  # room unknown until seen in one or placed by the player
    if parent is not None and not bought:
        data["mother_id" if parent.sex == "F" else "father_id"] = parent.id
        born = now - timedelta(minutes=reading.get("age_minutes") or 0)
        other = _other_parent(session, parent, born - timedelta(minutes=planner.GESTATION)) if parent.sex in ("M", "F") else None
        if other is not None:
            data["father_id" if parent.sex == "F" else "mother_id"] = other.id
    body = AnimalIn(**data, capture_id=capture.id, card_box=reading.get("card_box"), name_box=reading.get("name_box"),
                    age_minutes=reading.get("age_minutes") if lamb else None)
    animal = create_animal(body, session, auto=True)
    animal.card_name = name
    found_by = ""
    if parent is None and lamb and not bought:
        # No parent in its name ("Shelby", "Lucia"): the parent finder's top pair, but only when it's clear-cut.
        session.flush()
        ranked = _parents(session, animal)
        if ranked and ranked[0]["chance"] >= AUTO_PARENTS_CHANCE and (
                len(ranked) == 1 or ranked[0]["chance"] >= AUTO_PARENTS_LEAD * ranked[1]["chance"]):
            animal.mother_id, animal.father_id = ranked[0]["mother_id"], ranked[0]["father_id"]
            found_by = f"parents from the room and pregnancy records ({ranked[0]['chance']:.0%} sure)"
    log(session, "captured", animal.id, notes="registered automatically from its card"
        + (f"; {'mother' if parent.sex == 'F' else 'father'} from its name" if parent is not None else "")
        + (f"; {found_by}" if found_by else "")
        + ("; sex from its name" if parent is None and sex != "?" else ""))
    session.commit()
    return animal


# ---------------------------------------------------------------- vendor

ITEM_LABELS = {"metal_fragments": "metal fragments", "hqm_ore": "HQM ore", "low_grade_fuel": "low grade fuel", "rifle_ammo_556": "5.56 rifle ammo",
               "cctv_camera": "CCTV camera", "smg_body": "SMG body", "high_caliber_revolver": "High Caliber Revolver",
               "python_revolver": "Python revolver", "rifle_body": "rifle body",
               "semi_automatic_rifle": "semi-automatic rifle", "thompson": "Thompson",
               "custom_smg": "Custom SMG",
               "armored_double_door": "armoured double door",
               "armored_ladder_hatch": "armoured ladder hatch"}
VENDOR_GAP_SECONDS = 45  # no Sale panel for this long: the visit is over
_vendor: dict = {}  # the visit in progress: sale key, name, animal, last seen, last offer's signature


def _item_text(items: list) -> str:
    parts = []
    for i in items:
        label = ITEM_LABELS.get(i.get("item") or "", (i.get("item") or "unknown item").replace("_", " "))
        if i.get("length_ft"):
            parts.append(f"{label} ({i['length_ft']}ft)")
        else:
            parts.append(f"{i['amount']} {label}" if i["amount"] != 1 or label == "scrap" else label)
    return " + ".join(parts)


def _vendor_animal(session: Session, name: str) -> Optional[Animal]:
    """The herd animal the Sale panel names (OCR can slip a letter: "Daryi")."""
    alive = session.exec(select(Animal).where(Animal.status.in_(["alive", "missing"]))).all()
    names = sorted({(a.name or "").lower() for a in alive})
    hit = difflib.get_close_matches(name.lower(), names, n=1, cutoff=0.75)
    return by_name([a for a in alive if (a.name or "").lower() == hit[0]]) if hit else None


def _too_valuable_to_assume(animal: Animal) -> bool:
    """A harem ram or promoted animal in the current plan, or one showing green on every target gene."""
    target = settings_store.load().get("target_genes") or "DLYFH"
    all_green = all(animal.genes_top[genetics.GENES.index(g)] == "G" for g in target)
    return all_green or animal.id in _last_plan.get(animal.species, set())


async def _close_visit(session: Session):
    """The visit ended: the last offer shown is taken (you nearly always end on a deal), the animal marked sold."""
    visit = _vendor.copy()
    _vendor.clear()
    offers = session.exec(select(Offer).where(Offer.sale == visit["sale"]).order_by(Offer.number)).all()
    if not offers:
        return
    last = offers[-1]
    if visit.get("declined"):  # the Stablehand said he wouldn't offer on it today: nothing was sold
        text = "; ".join(f"{o.number} = {_item_text(json.loads(o.items))}" for o in offers)
        caps = ", ".join(str(o.capture_id) for o in offers if o.capture_id)
        if last.animal_id:
            log(session, "offers_declined", last.animal_id, notes=f"auto: all offers turned down: {text} [captures {caps}]")
        session.commit()
        return
    last.outcome = "taken"
    text = "; ".join(f"{o.number} = {_item_text(json.loads(o.items))}" + (" (rare mood)" if o.rare else "")
                     for o in offers)
    caps = ", ".join(str(o.capture_id) for o in offers if o.capture_id)
    animal = session.get(Animal, last.animal_id) if last.animal_id else None
    if animal is not None and animal.pregnant:
        last.outcome = ""
        log(session, "offers_declined", animal.id,
            notes=f"auto: the vendor won't buy a pregnant ewe; offers seen: {text} [captures {caps}]")
        session.commit()
        return
    if animal is not None and animal.status in ("alive", "missing") and _too_valuable_to_assume(animal):
        # Ending on offer 3 looks the same whether it was taken or all three were turned down (Louis, the god ram, was
        # declined). For an animal this valuable, record the offers and ask rather than assume a sale.
        log(session, "offers_declined", animal.id,
            notes=f"auto: offers seen, sale not assumed (valuable animal) - mark it sold if you did sell: {text} [captures {caps}]")
        session.commit()
        await hub.broadcast({"type": "vendor_unsure", "id": animal.id, "name": animal.name})
        return
    if animal is not None and animal.status in ("alive", "missing"):
        animal.status = "sold"
        log(session, "sold", animal.id, notes=f"auto: offers (offer {last.number} taken): {text} [captures {caps}]")
        await hub.broadcast({"type": "vendor_sold", "id": animal.id, "name": animal.name, "number": last.number,
                             "items": _item_text(json.loads(last.items)), "sale": visit["sale"]})
    elif last.wool:
        log(session, "wool_sold", None,
            notes=f"auto: {last.wool} wool, offer {last.number} taken: {text} [captures {caps}]")
        await hub.broadcast({"type": "vendor_sold", "name": f"{last.wool} wool", "number": last.number,
                             "items": _item_text(json.loads(last.items)), "sale": visit["sale"]})
    session.commit()


async def _vendor_frame(session: Session, frame, now: datetime) -> Optional[dict]:
    """A frame from automatic capture that shows no animal card: is it the vendor's Sale panel?"""
    if _vendor and (now - _vendor["seen"]).total_seconds() > VENDOR_GAP_SECONDS:
        await _close_visit(session)
    reading = vendor_reader.read_sale(frame)
    if not reading["found"]:
        if _vendor and not _vendor.get("declined"):
            # No Sale panel, but mid-visit: is this the Stablehand turning the animal down after the third offer?
            said = vendor_reader.read_dialogue(frame)
            if vendor_reader.is_refusal(said):
                _vendor["declined"] = True
                _vendor["seen"] = now
                file = f"{now:%Y%m%d-%H%M%S}-refusal-{uuid.uuid4().hex[:6]}.jpg"
                cv2.imwrite(str(CAPTURE_DIR / file), frame)  # kept so the wording can be checked
                session.add(Capture(path=file, width=frame.shape[1], height=frame.shape[0], location="Vendor",
                                    dismissed=True, animal_id=_vendor.get("animal_id")))
                session.commit()
                await hub.broadcast({"type": "vendor_refused", "name": _vendor.get("name", "")})
                return {"vendor": True, "refused": True, "said": said}
        return None
    items = [{k: i[k] for k in ("item", "amount", "length_ft")} for i in reading["items"]]
    animal = None if reading["wool"] else _vendor_animal(session, reading["name"])
    # Keyed by the animal once the name is matched, so an OCR slip ("Randy r") doesn't look like a new visit.
    who = f"#{animal.id}" if animal is not None else reading["name"].lower()
    signature = (who, json.dumps(items))
    if _vendor and (signature == _vendor.get("signature") or signature in _vendor.get("offers", [])):
        _vendor["seen"] = now  # the same screen again, or an earlier offer re-read
        return {"vendor": True, "repeat": True}
    same_animal = animal is not None and animal.id == _vendor.get("animal_id")
    same_visit = bool(_vendor) and (same_animal or (reading["kind"] != "first" and difflib.SequenceMatcher(
        None, reading["name"].lower(), _vendor.get("name", "")).ratio() > 0.75))
    if _vendor and not same_visit:
        await _close_visit(session)
    elif same_visit and animal is not None and not _vendor.get("animal_id"):
        _vendor["animal_id"] = animal.id  # the name only matched on a later frame: the whole visit is this animal's
        for o in session.exec(select(Offer).where(Offer.sale == _vendor["sale"])):
            o.animal_id = animal.id
    if not _vendor:
        _vendor.update(sale=f"{now:%Y%m%d-%H%M%S}", name=reading["name"].lower(), number=0,
                       animal_id=animal.id if animal else None)
    _vendor.update(seen=now, signature=signature, number=_vendor["number"] + 1,
                   offers=_vendor.get("offers", []) + [signature])
    file = f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.jpg"
    cv2.imwrite(str(CAPTURE_DIR / file), frame)
    capture = Capture(path=file, width=frame.shape[1], height=frame.shape[0], location="Vendor", dismissed=True,
                      animal_id=animal.id if animal else None)
    session.add(capture)
    session.flush()
    offer = Offer(at=now, sale=_vendor["sale"], name=reading["name"], animal_id=animal.id if animal else None,
                  wool=reading["wool"], number=_vendor["number"], rare=reading["kind"] == "rare",
                  items=json.dumps(items), scrap=reading["scrap"], capture_id=capture.id)
    session.add(offer)
    session.commit()
    for k, item in enumerate(reading["items"]):  # keep icons it doesn't know, to be named and added to the library
        if item["item"] is None:
            unknown = vendor_reader.LIBRARY_DIR / "_unknown"
            unknown.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(unknown / f"{capture.id}_{k}.png"), item["icon"])
    past = [json.loads(o.items) for o in session.exec(select(Offer).where(Offer.rare == False, Offer.id != offer.id))]  # noqa: E712
    advice = offer_value.advise(items, offer.number, offer.rare, past, settings_store.load().get("item_worth"))
    await hub.broadcast({"type": "vendor_offer", "name": animal.name if animal else reading["name"],
                         "number": offer.number, "rare": offer.rare, "items": _item_text(items), **advice})
    return {"vendor": True, "offer": offer.number, "name": reading["name"]}


def _resold_check(session: Session, animal_name: str, reading: dict) -> Optional[Animal]:
    """A card of an animal the vendor reader marked sold: the offers were turned down after all. Put it back."""
    for a in session.exec(select(Animal).where(Animal.status == "sold",
                                               func.lower(Animal.name) == animal_name.lower())):
        if a.genes_top != reading["genes_top"]:
            continue
        sold = session.exec(select(Event).where(Event.animal_id == a.id, Event.kind == "sold")
                            .order_by(Event.at.desc())).first()
        if sold and sold.notes.startswith("auto:"):
            a.status = "alive"
            sold.kind = "offers_declined"
            sold.notes = sold.notes.replace("auto: offers (offer", "auto: declined (last was offer", 1)
            for o in session.exec(select(Offer).where(Offer.animal_id == a.id, Offer.outcome == "taken")):
                o.outcome = ""
            log(session, "alive", a.id, notes="seen again after the vendor visit: not sold")
            session.commit()
            return a
    return None


@app.post("/api/vendor/undo/{sale}")
def vendor_undo(sale: str, session: Session = Depends(get_session)):
    """The automatic 'sold' was wrong (offers declined): put the animal back."""
    offers = session.exec(select(Offer).where(Offer.sale == sale)).all()
    for o in offers:
        o.outcome = ""
    for aid in {o.animal_id for o in offers if o.animal_id}:
        a = session.get(Animal, aid)
        if a and a.status == "sold":
            a.status = "alive"
            log(session, "alive", a.id, notes="vendor sale undone: offers declined")
            for e in session.exec(select(Event).where(Event.animal_id == aid, Event.kind == "sold")):
                if e.notes.startswith("auto:"):
                    e.kind = "offers_declined"
    session.commit()
    return {"ok": True}


@app.post("/api/vendor/not-sold/{animal_id}")
def vendor_not_sold(animal_id: int, session: Session = Depends(get_session)):
    """An animal the vendor reader marked sold wasn't (the offers were turned down): put it back in the herd."""
    a = get_animal(session, animal_id)
    for e in session.exec(select(Event).where(Event.animal_id == animal_id, Event.kind == "sold")):
        if e.notes.startswith("auto:"):
            e.kind = "offers_declined"
            e.notes = e.notes.replace("auto: offers (offer", "auto: declined (last was offer", 1)
    for o in session.exec(select(Offer).where(Offer.animal_id == animal_id, Offer.outcome == "taken")):
        o.outcome = ""
    if a.status == "sold":
        a.status = "alive"
        log(session, "alive", a.id, notes="vendor sale undone: offers declined")
    session.commit()
    return {"ok": True}


@app.get("/api/vendor/offers")
def vendor_offers(limit: int = 300, session: Session = Depends(get_session)):
    return session.exec(select(Offer).order_by(Offer.at.desc()).limit(limit)).all()


# ---------------------------------------------------------------- roll call

MIA_WINDOW_SECONDS = 30 * 60
MIA_LOOKS = 3  # separate looks at the building in that window, at least a minute apart
MIA_LOOK_GAP_SECONDS = 60
MIA_DISTINCT = 3  # different animals seen there in the window
UNPLACED_STALE_SECONDS = 6 * 3600
_sightings: dict = {}  # building -> [(time, animal id, was it recorded there already)]
_mia_checked: dict = {}  # building -> last check time


async def _roll_call(session: Session, building: str, now: datetime):
    """Mark missing the animals recorded in this building that the last 30 minutes of looking there never saw.

    A look counts when the cards seen were mostly of animals already recorded there (so a stale "Where am I?" can't
    empty the wrong building). An animal seen anywhere else would already have been moved out of the room."""
    if (now - _mia_checked.get(building, now - timedelta(hours=1))).total_seconds() < 60:
        return
    _mia_checked[building] = now
    start = now - timedelta(seconds=MIA_WINDOW_SECONDS)
    recent = [x for x in _sightings.get(building, []) if x[0] >= start]
    _sightings[building] = recent
    if not recent or sum(1 for _, _, home in recent if home) * 2 < len(recent):
        return
    looks, last = 0, None
    for t, _, _ in sorted(recent):
        if last is None or (t - last).total_seconds() >= MIA_LOOK_GAP_SECONDS:
            looks += 1
            last = t
    if looks < MIA_LOOKS or len({aid for _, aid, _ in recent}) < MIA_DISTINCT:
        return  # staring at one sheep isn't looking round the building
    then = pens_at(session, start)
    rooms = _buildings() if building == FARM else [building]  # the whole farm: every room
    missing = []
    for a in session.exec(select(Animal).where(Animal.status == "alive", Animal.pen.in_(rooms))).all():
        seen = _utc(a.seen_at)
        if then.get(a.id) not in rooms or _utc(a.created_at) >= start or (seen is not None and seen >= start):
            continue
        a.status = "missing"
        log(session, "missing", a.id, notes=f"not seen in {building} in {looks} looks over 30 minutes (roll call)")
        missing.append(a.name or a.code)
    # Animals with no building belong to no roll call: while you're out looking, one unseen for hours is gone too.
    stale = now - timedelta(seconds=UNPLACED_STALE_SECONDS)
    for a in session.exec(select(Animal).where(Animal.status == "alive", or_(Animal.pen == "", Animal.pen.is_(None)))).all():
        last = _utc(a.seen_at) or _utc(a.created_at)
        if last is not None and last < stale:
            a.status = "missing"
            log(session, "missing", a.id, notes="no building and not seen for 6 hours (roll call)")
            missing.append(a.name or a.code)
    if missing:
        session.commit()
        await hub.broadcast({"type": "auto_missing", "building": building, "names": missing})


@app.post("/api/autocapture")
async def autocapture(file: UploadFile = File(...), full_width: int = 0, full_height: int = 0, crop_x: int = 0,
                      crop_y: int = 0, session: Session = Depends(get_session)):
    """A strip of screen sent every few seconds by the browser sharing the gaming PC's screen.

    No card: ignored. A known animal: its conditions (and pregnancy, lamb age) are updated quietly. A new animal: the
    frame is filed as a pending capture for the player to confirm, at most once every few minutes."""
    if settings_store.load().get("location") == "Away":  # the player said they're away from the livestock
        return {"away": True}
    data = np.frombuffer(await file.read(), np.uint8)
    strip = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if strip is None:
        raise HTTPException(422, "not an image")
    h, w = strip.shape[:2]
    full_width, full_height = max(full_width, crop_x + w), max(full_height, crop_y + h)
    frame = np.zeros((full_height, full_width, 3), np.uint8)
    frame[crop_y:crop_y + h, crop_x:crop_x + w] = strip
    reading = card_reader.read_card(frame)
    cv2.imwrite(str(DATA_DIR / "last_autocapture.jpg"), strip)  # the latest frame, overwritten: for checking what Auto sees
    if not reading.get("found"):
        return await _vendor_frame(session, frame, datetime.now(timezone.utc)) or {"card": False}
    now = datetime.now(timezone.utc)
    sig = _signature(reading)
    last = _auto_seen.get(sig)
    if last and (now - last[0]).total_seconds() < AUTO_REPEAT_SECONDS and last[1] == reading.get("conditions"):
        return {"card": True, "repeat": True}
    _auto_seen[sig] = (now, reading.get("conditions"))

    animal = _match_reading(session, reading)
    if animal is None and reading.get("name"):
        animal = _resold_check(session, reading["name"], reading)
    if animal is None and reading.get("name") and "?" not in reading["genes_top"]:
        for a in session.exec(select(Animal).where(Animal.status == "dead",
                                                   func.lower(Animal.name) == reading["name"].lower())):
            if a.genes_top == reading["genes_top"] and (reading.get("herd_top") is None or a.herd_top in (None, reading["herd_top"])):
                a.status = "missing"  # back as alive below if this is one of the buildings
                log(session, "missing", a.id, notes="marked dead, but its card was seen again")
                animal = a
                break
    if animal is None:
        # A card caught while opening, blurred or half off-screen reads as unknown genes: wait for a clean look rather
        # than filing a "new" animal that is really a bad read of one already seen.
        if "?" in reading["genes_top"] or reading.get("herd_top") is None or not reading.get("conditions"):
            return {"card": True, "unclear": True}
        filed = _auto_seen.get("new:" + sig)
        if filed and (now - filed[0]).total_seconds() < AUTO_NEW_COOLDOWN_SECONDS:
            return {"card": True, "new": True, "filed": False}
        new = _auto_register(session, reading, frame, now)
        if new is not None:
            _auto_seen["new:" + sig] = (now, None)
            await hub.broadcast({"type": "auto_new", "id": new.id, "name": new.name, "sex": new.sex,
                                 "pen": new.pen, "lamb": bool(reading.get("lamb"))})
            return {"card": True, "new": True, "registered": new.id, "name": new.name}
        _auto_seen["new:" + sig] = (now, None)
        name = f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.jpg"
        cv2.imwrite(str(CAPTURE_DIR / name), frame)
        capture = Capture(path=name, width=full_width, height=full_height, location=settings_store.load().get("location") or "")
        session.add(capture)
        session.commit()
        session.refresh(capture)
        await hub.broadcast({"type": "capture_ready", "capture": capture.model_dump(mode="json"), "auto": True})
        return {"card": True, "new": True, "filed": True, "name": reading.get("name")}

    if reading.get("inbred") is not None and animal.inbred != reading["inbred"]:
        animal.inbred = reading["inbred"]  # the card's INBRED label (fixed for life; read again on every sighting)
    cond = reading.get("conditions") or {}
    keys = ("food", "water", "personal_space", "overall")
    # The bars read a point either way from frame to frame: only a real change counts.
    changed = any(cond.get(k) is not None and abs(cond[k] - (getattr(animal, k) or 0)) >= 3 for k in keys)
    last_seen = _utc(animal.seen_at)
    if cond and (changed or last_seen is None or (now - last_seen).total_seconds() > READING_EVERY_SECONDS):
        session.add(Reading(animal_id=animal.id, at=now, **{k: cond.get(k) for k in keys}))
    for key in keys:
        if cond.get(key) is not None:
            setattr(animal, key, cond[key])
    animal.seen_at = now
    if (reading.get("yield") or {}).get("per_hour") and reading["yield"].get("product", "wool") == "wool":
        animal.wool_per_hour = reading["yield"]["per_hour"]
        animal.wool_per_shear, animal.wool_regrow_min = reading["yield"]["amount"], reading["yield"]["minutes"]
    if animal.status == "missing" and (settings_store.load().get("location") or FARM) in _buildings() + [FARM]:
        animal.status = "alive"  # back in a building; seen outside one (grazing by the vendor, say) it stays missing
        log(session, "alive", animal.id, notes="found (automatic capture)")
    if reading.get("name") and animal.card_name != reading["name"]:
        animal.card_name = reading["name"]  # the name as the card shows it, whatever the player renamed it to
    if reading.get("name"):
        # "Pregnant" after the name. It lingers a few seconds after the lamb appears, and no ewe can be pregnant again
        # within 40 minutes of lambing (the shortest cooldown is 41), so a recent lamb means it's that echo.
        last_lamb = session.exec(select(Animal).where(Animal.mother_id == animal.id)
                                 .order_by(Animal.created_at.desc())).first()
        lamb_at = _utc(last_lamb.born_at or last_lamb.created_at) if last_lamb else None
        just_lambed = lamb_at is not None and (now - lamb_at).total_seconds() < PREGNANCY_ECHO_SECONDS
        if reading.get("pregnant") and not animal.pregnant and not just_lambed:
            animal.pregnant = True
            if animal.sex != "F":  # only a ewe can be pregnant, whatever the name suggested
                log(session, "edited", animal.id, notes=f"sex {animal.sex} -> F: the card says Pregnant")
                animal.sex = "F"
            log(session, "pregnant", animal.id, notes="the card says Pregnant (automatic capture)")
        elif not reading.get("pregnant") and animal.pregnant:
            animal.pregnant = False  # the name read cleanly without it: she's had the lamb (or never was)
            log(session, "not_pregnant", animal.id, notes="the card no longer says Pregnant (automatic capture)")
    if reading.get("lamb") and reading.get("age_minutes") is not None and animal.born_at is None:
        animal.born_at = now - timedelta(minutes=reading["age_minutes"])
    # Seen while the player says they're in a building: that's where it is.
    settings = settings_store.load()
    pools_cfg = settings.get("pools") or {}
    holding = pools_cfg.get("holding") or []
    buildings = list(pools_cfg.get("harems") or []) + ([holding] if isinstance(holding, str) else list(holding))
    here = settings.get("location") or FARM  # unset means somewhere on the farm
    if here in buildings:
        _sightings.setdefault(here, []).append((now, animal.id, animal.pen == here))
    elif here == FARM:  # room unknown: counts towards the whole farm's roll call, moves nobody
        _sightings.setdefault(FARM, []).append((now, animal.id, animal.pen in buildings))
    if here in buildings and animal.pen != here:
        log(session, "moved", animal.id, notes=f"{animal.pen or 'not placed'} -> {here} (seen there)")
        animal.pen = here
    session.commit()
    # No roll call: not being seen for a while never changes an animal's room or status (it pulled sheep out of their
    # rooms while the player was watching one pen). Cards show "Not seen for ..." instead; the player decides.
    await hub.broadcast({"type": "auto_seen", "id": animal.id, "name": animal.name or animal.code, **cond})
    return {"card": True, "id": animal.id, "name": animal.name or animal.code, "conditions": cond}


@app.delete("/api/captures/{capture_id}")
def dismiss_capture(capture_id: int, session: Session = Depends(get_session)):
    capture = session.get(Capture, capture_id)
    if not capture:
        raise HTTPException(404, f"capture {capture_id} not found")
    if capture.animal_id is None:
        (CAPTURE_DIR / capture.path).unlink(missing_ok=True)
    capture.dismissed = True
    session.commit()
    return {"ok": True}


@app.post("/api/capture/trigger")
async def trigger_capture():
    """Ask the gaming-PC browser for a frame. Same as the WebSocket 'request_capture' message."""
    sent = await hub.request_capture()
    if not sent:
        raise HTTPException(409, "no browser is sharing its screen")
    return {"capturers": sent}


@app.get("/api/autocapture/last.jpg")
def last_autocapture():
    """The latest frame Auto sent (the strip it reads), so a wrong shared window (Steam, Discord) is easy to spot."""
    path = DATA_DIR / "last_autocapture.jpg"
    if not path.exists():
        raise HTTPException(404, "no frame yet")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- websocket

class Hub:
    """Connected browsers. A 'capturer' is one sharing the gaming PC's screen."""

    def __init__(self):
        self.clients: dict[WebSocket, bool] = {}
        self.source = ""  # what the sharing browser says it shares (a window title, or "screen:0:0"), for every device

    async def broadcast(self, msg: dict, capturers_only=False):
        for ws, capturer in list(self.clients.items()):
            if capturers_only and not capturer:
                continue
            try:
                await ws.send_json(msg)
            except Exception:
                self.clients.pop(ws, None)

    async def broadcast_status(self):
        await self.broadcast({"type": "status", "capturers": sum(self.clients.values()), "source": self.source})

    async def request_capture(self) -> int:
        await self.broadcast({"type": "capture_request"}, capturers_only=True)
        return sum(self.clients.values())


hub = Hub()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients[ws] = False
    await hub.broadcast_status()
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "hello":
                hub.clients[ws] = bool(msg.get("capturer"))
                await hub.broadcast_status()
            elif msg.get("type") == "auto_capture":
                # Turn automatic capture on or off on the browser sharing the screen, from any device.
                await hub.broadcast({"type": "auto_capture", "enabled": bool(msg.get("enabled"))}, capturers_only=True)
            elif msg.get("type") == "auto_status":
                hub.source = str(msg.get("source") or "")[:200]
                await hub.broadcast({"type": "auto_status", "enabled": bool(msg.get("enabled")), "source": hub.source})
            elif msg.get("type") == "request_capture":
                if not await hub.request_capture():
                    await ws.send_json({"type": "capture_warning",
                                        "message": "No browser is sharing the gaming PC's screen."})
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        hub.clients.pop(ws, None)
        await hub.broadcast_status()


# ---------------------------------------------------------------- static files

app.mount("/media/captures", StaticFiles(directory=CAPTURE_DIR), name="captures")
app.mount("/media/cards", StaticFiles(directory=CARD_DIR), name="cards")
app.mount("/media/names", StaticFiles(directory=NAME_DIR), name="names")
if BUILD_DIR.exists():
    app.mount("/", StaticFiles(directory=BUILD_DIR, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=PORT)
