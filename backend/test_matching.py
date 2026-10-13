"""Matching a card to the herd: the name as read counts as well as the name the player gave."""
from sqlmodel import Session, SQLModel, create_engine

import server
from models import Animal


def _session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_renamed_animal_still_matches_its_card():
    s = _session()
    lamb = Animal(code="S1", species="sheep", sex="M", genes_top="OGGGO", herd_top=3, name="ANTON", card_name="Anton")
    s.add(lamb)
    s.commit()
    assert server._match_reading(s, {"name": "Anton", "genes_top": "OGGGO", "herd_top": 3}).id == lamb.id


def test_different_name_same_genes_is_not_a_match():
    s = _session()
    s.add(Animal(code="S1", species="sheep", sex="M", genes_top="OGGGO", herd_top=3, name="Stanislav", card_name="Stanislav"))
    s.commit()
    assert server._match_reading(s, {"name": "Snezhana", "genes_top": "OGGGO", "herd_top": 3}) is None


def test_two_animals_with_the_same_name_and_genes_are_told_apart():
    s = _session()
    old = Animal(code="S1", species="sheep", sex="F", genes_top="OGGGG", herd_top=3, name="Polina", card_name="Polina", inbred=True)
    young = Animal(code="S2", species="sheep", sex="F", genes_top="OGGGG", herd_top=3, name="Polina", card_name="Polina", inbred=False)
    s.add(old)
    s.add(young)
    s.commit()
    card = {"name": "Polina", "genes_top": "OGGGG", "herd_top": 3}
    assert server._match_reading(s, {**card, "inbred": True}).id == old.id
    assert server._match_reading(s, {**card, "inbred": False}).id == young.id
