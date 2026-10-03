# Livestock Mechanics

What we believe about Rust's livestock breeding (added October 2026), how sure we are, and how to confirm it.
Everything marked **Video** comes from a single YouTube video published around 2026-10-02.
Update this file as in-game results come in; the breeding log in the app is the evidence.

Confidence: **Known** (seen in game) · **Likely** (consistent with what we've seen) · **Guess** (needs testing)

## The animal card

Looking at an animal shows a card the game generates; the player cannot change it.

| Item | Notes | Confidence |
|---|---|---|
| Name | Assigned by the game. Can be in any script — the first sheep bought had a Cyrillic name. Stored as an image, not text. | Known |
| Sex (♀/♂) and status (e.g. Pregnant) | Shown top right. | Known |
| Genes D L Y F H | **D**ung output, **L**ifespan, **Y**ield (milk / wool), **F**ertility (breeding cooldown and twin chance), **H**ardiness (tolerance of poor conditions). | Known |
| Gene colours | Green = Good, Grey = Ok, Red = Bad. | Video |
| 6th column | Herd number, two rows like the genes. Used to detect incest. | Video |

## Inheritance

| Rule | Confidence | How to test |
|---|---|---|
| Each gene has two copies. | Likely | — |
| Dominance: Good > Ok > Bad. The stronger copy decides the animal's output. | Video (outcome table) | Compare bred offspring to the table. |
| Top row = the expressed (winning) copy; bottom row = the carried copy. Not "mother's row / father's row". | Guess | Offspring of Good/Ok × Ok/Ok should never show Ok on top with Good underneath. |
| Each parent passes one of its two copies per gene, 50/50, independently per gene. | Video (outcome table) | Tally offspring over many births. |
| Ranch (NPC) animals have only one line. Assumed to be pure-bred: both copies identical. | Guess | Breed two ranch animals: the offspring should be exactly one copy from each parent, with no randomness in the genes. |
| Offspring sex is 50/50. | Guess | Tally births. |
| Fertility affects cooldown and twin chance. | Video | Log births and twins against the mother's F gene. |

## Herd numbers and incest

| Rule | Confidence | How to test |
|---|---|---|
| A ranch animal has one herd number. | Guess | Check purchases. |
| A bred animal takes one herd number from each parent. | Guess | Check every birth. |
| Mating two animals that share a herd number counts as incest. | Video | — |
| Incest reduces the offspring's output below what its genes would give. | Video | — |
| Does incest also reduce fertility or breeding ability? | Unknown | Compare cooldowns of inbred and clean animals. |
| Is an inbred × unrelated mating clean? | Guess (yes) | Breed an inbred male with a fresh ranch female. |
| Does inbreeding change the genes, e.g. raise the chance of Bad? | Unknown | Watch for offspring genes the parents could not have produced. |

## Economics

| Item | Value | Confidence |
|---|---|---|
| Sheep from ranch NPC | 150 scrap | Known |
| Cow from ranch NPC | 300 scrap | Known |
| Can genes be seen before buying? Can sex be chosen? | Unknown | — |
| Trips to the ranch are dangerous and often fail, so animals are scarce. | Known | — |
| Gestation, breeding cooldown, time to maturity | Unknown | Log timestamps. |
| Space per animal before a pen counts as overcrowded | Unknown | — |

## Goal and strategy (provisional)

- **God bull:** a male that is Good/Good on all five genes. Every offspring of his shows all Good, whatever the mother carries.
- Animals are the scarce resource, so plans should **minimise purchases first and breeding cycles second**.
- Inbreeding is acceptable for building the god bull, if the incest penalty only affects output. A fresh female should then "clean" the line in one generation.
- Run experiments on sheep first (half the price), assuming cows follow the same rules.
