"""Livestock backend: herd register, breeding log and screen-capture intake."""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from sqlmodel import Session, or_, select

import genetics
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


class AnimalIn(CaptureCrop):
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


class AnimalPatch(CaptureCrop):
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
    "sex": ("M", "F"),
    "origin": ("ranch", "bred"),
    "status": ("alive", "sold", "dead"),
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
    return data


def last_mate(session: Session, mother_id: int) -> Optional[int]:
    """The male in the mother's most recent recorded mating."""
    event = session.exec(select(Event).where(Event.kind == "mated", Event.animal_id == mother_id)
                         .order_by(Event.at.desc())).first()
    return event.other_id if event else None


def check_animal(session: Session, animal: Animal):
    """Rules that span several fields, applied after create or update."""
    if animal.sex == "M":
        animal.pregnant = False
    for field, sex in (("mother_id", "F"), ("father_id", "M")):
        parent_id = getattr(animal, field)
        if parent_id is None:
            continue
        parent = session.get(Animal, parent_id)
        if not parent or parent.id == animal.id:
            raise HTTPException(422, f"{field} {parent_id} is not a valid animal")
        if parent.sex != sex or parent.species != animal.species:
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


def split_crop(data: dict) -> dict:
    return {k: data.pop(k) for k in ("capture_id", "card_box", "name_box") if k in data}


# ---------------------------------------------------------------- animals

@app.get("/api/animals")
def list_animals(include_gone: bool = False, session: Session = Depends(get_session)):
    query = select(Animal).order_by(Animal.code)
    if not include_gone:
        query = query.where(Animal.status == "alive")
    return session.exec(query).all()


@app.post("/api/animals")
def create_animal(body: AnimalIn, session: Session = Depends(get_session)):
    data = body.model_dump()
    crop = split_crop(data)
    animal = Animal(**clean(data), code=next_code(session, data["species"]))
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
    for field, value in clean(data).items():
        if getattr(animal, field) != value:
            setattr(animal, field, value)
            changed.append(field)
    check_animal(session, animal)
    if "pregnant" in changed:
        log(session, "pregnant" if animal.pregnant else "not_pregnant", animal.id)
    if "status" in changed:
        log(session, animal.status, animal.id)
    edits = [f for f in changed if f not in ("pregnant", "status")]
    if edits:
        log(session, "edited", animal.id, notes=", ".join(edits))
    if crop.get("capture_id"):
        apply_capture(session, animal, crop)
        log(session, "captured", animal.id)
    session.commit()
    session.refresh(animal)
    return animal


@app.post("/api/animals/match")
def match_animals(observed: Observed, session: Session = Depends(get_session)):
    """Existing animals a captured card could belong to, best first."""
    animals = session.exec(select(Animal).where(
        Animal.status == "alive", Animal.species == observed.species, Animal.sex == observed.sex)).all()
    scored = [(genetics.match_score(a, observed), a) for a in animals]
    scored = sorted(((s, a) for s, a in scored if s), key=lambda sa: -sa[0])
    return [{"score": s, "animal": a} for s, a in scored[:5]]


# ---------------------------------------------------------------- breeding log

@app.post("/api/matings")
def record_mating(body: MatingIn, session: Session = Depends(get_session)):
    mother = get_animal(session, body.mother_id)
    father = get_animal(session, body.father_id)
    if mother.sex != "F" or father.sex != "M":
        raise HTTPException(422, "mother must be female and father male")
    if mother.species != father.species:
        raise HTTPException(422, "parents must be the same species")
    incest = genetics.shares_herd(mother, father)
    log(session, "mated", mother.id, father.id, body.notes + (" [incest]" if incest else ""))
    session.commit()
    return {"incest": incest}


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
    capture = Capture(path=name, width=width, height=height)
    session.add(capture)
    session.commit()
    session.refresh(capture)
    await hub.broadcast({"type": "capture_ready", "capture": capture.model_dump(mode="json")})
    return capture


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
