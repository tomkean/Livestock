from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow():
    return datetime.now(timezone.utc)


class Animal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)  # app ID, e.g. C-01
    # Display name: the in-game name when it reads cleanly as Latin text, otherwise the code. Editable.
    # The name image is what identifies the animal in game, whatever script its name is in.
    name: str = ""
    species: str  # cow | sheep
    sex: str  # M | F | ? (lambs: sex only shows as horns once grown)
    origin: str = "ranch"  # ranch (bought from the NPC) | bred
    # One letter per gene in genetics.GENES order: G(ood) O(k) B(ad) or ? (unread)
    genes_top: str = "?????"
    genes_bottom: Optional[str] = None  # hidden copy; normal players can't see it, so usually None
    herd_top: Optional[int] = None
    herd_bottom: Optional[int] = None
    pregnant: bool = False
    born_at: Optional[datetime] = None
    pen: str = ""
    # Latest conditions read off its card (automatic capture), and when.
    food: Optional[int] = None
    water: Optional[int] = None
    personal_space: Optional[int] = None
    overall: Optional[int] = None
    seen_at: Optional[datetime] = None
    # From the card's YIELD line: set by the expressed Y gene (Good 320, Ok 120, Bad 45 an hour; inbred one grade less).
    wool_per_hour: Optional[float] = None
    # Wool stops growing at one shear's worth, so what counts is how much a shear gives and how soon it's back.
    wool_per_shear: Optional[int] = None
    wool_regrow_min: Optional[float] = None  # Pools mode: which room it lives in (e.g. Harem #1, Death Row); empty if not placed  # from the card's AGE line at capture; lambs grow up 60 min later
    status: str = "alive"  # alive | sold | dead | missing
    mother_id: Optional[int] = Field(default=None, foreign_key="animal.id")
    father_id: Optional[int] = Field(default=None, foreign_key="animal.id")
    name_image: Optional[str] = None  # relative to DATA_DIR
    card_image: Optional[str] = None
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Event(SQLModel, table=True):
    """Breeding log and history. Doubles as the evidence for MECHANICS.md."""
    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=utcnow, index=True)
    kind: str  # bought | born | mated | pregnant | not_pregnant | sold | dead | alive | captured | edited
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id", index=True)
    other_id: Optional[int] = Field(default=None, foreign_key="animal.id")  # e.g. the father in a mating
    notes: str = ""


class Reading(SQLModel, table=True):
    """Conditions read off an animal's card by automatic capture, kept over time (e.g. food falling overnight)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    animal_id: int = Field(foreign_key="animal.id", index=True)
    at: datetime = Field(default_factory=utcnow, index=True)
    food: Optional[int] = None
    water: Optional[int] = None
    personal_space: Optional[int] = None
    overall: Optional[int] = None


class Capture(SQLModel, table=True):
    """A full-screen frame uploaded from the gaming PC, waiting to be turned into an animal record."""
    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=utcnow)
    path: str  # file name in CAPTURE_DIR
    width: int
    height: int
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id")
    dismissed: bool = False
    location: str = ""  # where the player said they were (a building, or "Vendor" for offer screens)
