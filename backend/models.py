from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow():
    return datetime.now(timezone.utc)


class Animal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)  # app ID, e.g. C-01; the in-game name is only an image
    species: str  # cow | sheep
    sex: str  # M | F
    origin: str = "ranch"  # ranch (bought from the NPC) | bred
    # One letter per gene in genetics.GENES order: G(ood) O(k) B(ad) or ? (unread)
    genes_top: str = "?????"
    genes_bottom: Optional[str] = None  # hidden copy; normal players can't see it, so usually None
    herd_top: Optional[int] = None
    herd_bottom: Optional[int] = None
    pregnant: bool = False
    status: str = "alive"  # alive | sold | dead
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


class Capture(SQLModel, table=True):
    """A full-screen frame uploaded from the gaming PC, waiting to be turned into an animal record."""
    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=utcnow)
    path: str  # file name in CAPTURE_DIR
    width: int
    height: int
    animal_id: Optional[int] = Field(default=None, foreign_key="animal.id")
    dismissed: bool = False
