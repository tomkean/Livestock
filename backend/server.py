"""Livestock backend: herd register, breeding log and screen-capture intake."""
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
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from sqlmodel import Session, or_, select

import card_reader
import genetics
import inference
import planner
import pools
import settings_store
from config import BUILD_DIR, CAPTURE_DIR, CARD_DIR, DATA_DIR, NAME_DIR, PORT
from database import get_session, init_db
from models import Animal, Capture, Event


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


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
    prefix = "C" if species == "cow" else "S"
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


def apply_capture(session: Session, animal: Animal, crop: dict):
    """Cut the card and name images for an animal out of a capture, and mark the capture as used."""
    capture = session.get(Capture, crop["capture_id"])
    if not capture:
        raise HTTPException(404, f"capture {crop['capture_id']} not found")
    if crop.get("card_box"):
        animal.card_image = crop_image(capture, crop["card_box"], CARD_DIR)
    if crop.get("name_box"):
        animal.name_image = crop_image(capture, crop["name_box"], NAME_DIR)
    capture.animal_id = animal.id
    # Teach the card reader this capture's marker digits, now that a person has confirmed them.
    if animal.herd_top is not None or animal.herd_bottom is not None:
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
    for a in session.exec(query).all():
        row = a.model_dump(mode="json")
        free = free_again_at(session, a)
        row["free_again_at"] = free.isoformat() if free else None
        row["good_good"], row["target_chance"] = target_chance(a, target, inf)
        out.append(row)
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
    return per_gene, round(total, 4)


@app.post("/api/animals")
def create_animal(body: AnimalIn, session: Session = Depends(get_session)):
    data = body.model_dump()
    crop = split_crop(data)
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
        apply_capture(session, animal, crop)
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
        log(session, "moved", animal.id, notes=f"{old_pen or 'unplaced'} -> {animal.pen or 'unplaced'}")
        changed.remove("pen")
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
    pen: str = ""  # the building it was found in: its parents were most likely there too


_inference_cache: dict = {}


def live_mode() -> bool:
    return not settings_store.load().get("second_row_visible", False)


def visible(a):
    """What a player sees on a live server: the card's top row and first marker, nothing underneath."""
    view = SimpleNamespace(**(a.model_dump() if hasattr(a, "model_dump") else vars(a)))
    if live_mode():
        view.genes_bottom = None
        view.herd_bottom = view.herd_top if getattr(view, "herd_bottom", None) == view.herd_top else None
    return view


def inferred(session: Session) -> dict | None:
    """Inference over the whole recorded family tree (all species, all statuses), cached until anything changes.
    None in test-server mode, where the captured second rows are used directly."""
    if not live_mode():
        return None
    animals = [visible(a) for a in session.exec(select(Animal)).all()]
    key = tuple((a.id, a.genes_top, a.mother_id, a.father_id) for a in animals)
    if _inference_cache.get("key") != key:
        _inference_cache.update(key=key, result=inference.infer(animals))
    return _inference_cache["result"]


_MOVE = re.compile(r"^(.*?) -> (.*?)(?: \(seen there\))?$")


def pens_at(session: Session, when: datetime) -> dict[int, str]:
    """Which building every animal was in at a given time: its current one, with later moves undone."""
    pens = {a.id: a.pen for a in session.exec(select(Animal)).all()}
    later = session.exec(select(Event).where(Event.kind == "moved", Event.at > when).order_by(Event.at.desc())).all()
    for e in later:  # newest first, so the last one undone is the first move after `when`
        m = _MOVE.match(e.notes or "")
        if m and e.animal_id in pens:
            pens[e.animal_id] = "" if m.group(1) in ("unplaced", "not placed") else m.group(1)
    return pens


def _parents(session: Session, child) -> list[dict]:
    # Conceived 10 minutes before birth. Birth time unknown: when it was first registered, or now for a fresh capture.
    born = _utc(getattr(child, "born_at", None) or getattr(child, "created_at", None) or datetime.now(timezone.utc))
    conceived = born - timedelta(minutes=planner.GESTATION)
    # Sold and dead animals can be parents of lambs conceived before they went, but not after.
    gone_at = {}
    for e in session.exec(select(Event).where(Event.kind.in_(["sold", "dead"]))):
        gone_at[e.animal_id] = max(gone_at.get(e.animal_id, _utc(e.at)), _utc(e.at))
    animals = [visible(a) for a in session.exec(select(Animal)).all()
               if a.status not in ("sold", "dead") or gone_at.get(a.id, conceived) >= conceived]
    for a in animals:  # bred here and captured as a lamb: registered within the hour it was born
        if a.born_at is None and a.origin == "bred":
            a.born_at = a.created_at
    mated = {(e.animal_id, e.other_id) for e in session.exec(select(Event).where(Event.kind == "mated"))}
    inf = inferred(session)
    # Where everyone was when it was conceived (the father was with the mother then) and when it was born (beside its
    # mother). A ewe moved between harems while pregnant still points at her old harem's ram.
    then, now_pens = pens_at(session, conceived), pens_at(session, born)
    pen = getattr(child, "pen", "") or ""

    def places(m, f):
        together = bool(then.get(m.id)) and then.get(m.id) == then.get(f.id)
        mother_there = not pen or now_pens.get(m.id) == pen
        return together, mother_there
    child_view = visible(child)
    child_view.born_at = born  # so parents too young for it are ruled out, even for a lamb just captured
    return genetics.likely_parents(child_view, animals, mated, dists=inf["posterior"] if inf else None,
                                   places=places)


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
    return planner.trip_plan(animals, species, settings.get("vehicle", "single"), settings.get("pen_capacity") or {}, planned,
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
                           int(cfg.get("harem_ewes") or 5), int(cfg.get("holding_size") or 4))
    return animals, {**result, "config": cfg}


@app.get("/api/pools")
def pools_plan(species: str = "sheep", session: Session = Depends(get_session)):
    """Suggested rooms for every animal (harems + holding), the moves from where they are now, and verdicts."""
    animals, result = _pools_view(session, species)
    current = {a.id: a.pen for a in animals}
    result["moves"] = [{"id": a.id, "name": a.name or a.code, "from": current[a.id] or None, "to": result["pen"][a.id]}
                       for a in animals if current[a.id] != result["pen"][a.id]]
    return result


class ApplyIn(BaseModel):
    ids: Optional[list[int]] = None  # only these animals' moves (the ones the player made); None = all


@app.post("/api/pools/apply")
def pools_apply(species: str = "sheep", body: Optional[ApplyIn] = None, session: Session = Depends(get_session)):
    """Record the suggested rooms as where the moved animals now are (do the moves in game first)."""
    _, result = _pools_view(session, species)
    only = set(body.ids) if body and body.ids is not None else None
    for animal_id, pen in result["pen"].items():
        if only is not None and animal_id not in only:
            continue
        a = session.get(Animal, animal_id)
        if a.pen != pen:
            log(session, "moved", a.id, notes=f"{a.pen or 'unplaced'} -> {pen}")
            a.pen = pen
    session.commit()
    return {"ok": True}


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
def put_settings(changes: dict):
    return settings_store.save(changes)


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
    named = [a for a in candidates if name and (a.name or "").lower() == name and fits(a)]
    if len(named) == 1:
        return named[0]
    unnamed = [a for a in candidates if fits(a) and "?" not in top and herd is not None and a.herd_top == herd]
    return unnamed[0] if len(unnamed) == 1 and not name else None


@app.post("/api/autocapture")
async def autocapture(file: UploadFile = File(...), full_width: int = 0, full_height: int = 0, crop_x: int = 0,
                      crop_y: int = 0, session: Session = Depends(get_session)):
    """A strip of screen sent every few seconds by the browser sharing the gaming PC's screen.

    No card: ignored. A known animal: its conditions (and pregnancy, lamb age) are updated quietly. A new animal: the
    frame is filed as a pending capture for the player to confirm, at most once every few minutes."""
    data = np.frombuffer(await file.read(), np.uint8)
    strip = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if strip is None:
        raise HTTPException(422, "not an image")
    h, w = strip.shape[:2]
    full_width, full_height = max(full_width, crop_x + w), max(full_height, crop_y + h)
    frame = np.zeros((full_height, full_width, 3), np.uint8)
    frame[crop_y:crop_y + h, crop_x:crop_x + w] = strip
    reading = card_reader.read_card(frame)
    if not reading.get("found"):
        return {"card": False}
    now = datetime.now(timezone.utc)
    sig = _signature(reading)
    last = _auto_seen.get(sig)
    if last and (now - last[0]).total_seconds() < AUTO_REPEAT_SECONDS and last[1] == reading.get("conditions"):
        return {"card": True, "repeat": True}
    _auto_seen[sig] = (now, reading.get("conditions"))

    animal = _match_reading(session, reading)
    if animal is None:
        # A card caught while opening, blurred or half off-screen reads as unknown genes: wait for a clean look rather
        # than filing a "new" animal that is really a bad read of one already seen.
        if "?" in reading["genes_top"] or reading.get("herd_top") is None or not reading.get("conditions"):
            return {"card": True, "unclear": True}
        filed = _auto_seen.get("new:" + sig)
        if filed and (now - filed[0]).total_seconds() < AUTO_NEW_COOLDOWN_SECONDS:
            return {"card": True, "new": True, "filed": False}
        _auto_seen["new:" + sig] = (now, None)
        name = f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.jpg"
        cv2.imwrite(str(CAPTURE_DIR / name), frame)
        capture = Capture(path=name, width=full_width, height=full_height, location=settings_store.load().get("location") or "")
        session.add(capture)
        session.commit()
        session.refresh(capture)
        await hub.broadcast({"type": "capture_ready", "capture": capture.model_dump(mode="json"), "auto": True})
        return {"card": True, "new": True, "filed": True, "name": reading.get("name")}

    cond = reading.get("conditions") or {}
    for key in ("food", "water", "personal_space", "overall"):
        if cond.get(key) is not None:
            setattr(animal, key, cond[key])
    animal.seen_at = now
    if (reading.get("yield") or {}).get("per_hour"):
        animal.wool_per_hour = reading["yield"]["per_hour"]
    if animal.status == "missing":
        animal.status = "alive"
        log(session, "alive", animal.id, notes="found (automatic capture)")
    if reading.get("lamb") and reading.get("age_minutes") is not None and animal.born_at is None:
        animal.born_at = now - timedelta(minutes=reading["age_minutes"])
    # Seen while the player says they're in a building: that's where it is.
    settings = settings_store.load()
    pools_cfg = settings.get("pools") or {}
    holding = pools_cfg.get("holding") or []
    buildings = list(pools_cfg.get("harems") or []) + ([holding] if isinstance(holding, str) else list(holding))
    here = settings.get("location") or ""
    if here in buildings and animal.pen != here:
        log(session, "moved", animal.id, notes=f"{animal.pen or 'not placed'} -> {here} (seen there)")
        animal.pen = here
    session.commit()
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


# ---------------------------------------------------------------- websocket

class Hub:
    """Connected browsers. A 'capturer' is one sharing the gaming PC's screen."""

    def __init__(self):
        self.clients: dict[WebSocket, bool] = {}

    async def broadcast(self, msg: dict, capturers_only=False):
        for ws, capturer in list(self.clients.items()):
            if capturers_only and not capturer:
                continue
            try:
                await ws.send_json(msg)
            except Exception:
                self.clients.pop(ws, None)

    async def broadcast_status(self):
        await self.broadcast({"type": "status", "capturers": sum(self.clients.values())})

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
                await hub.broadcast({"type": "auto_status", "enabled": bool(msg.get("enabled"))})
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
