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
| Second row | **Players see only the top row.** Our own ranch sheep showed one row, and so did animals on a test server while we were admin. The YouTuber's two-row screenshot, which they put down to being admin, must have come from something else (a debug command or an older build). | Known (one row); cause of two rows unknown |

## Inheritance

| Rule | Confidence | How to test |
|---|---|---|
| Each gene has two copies. | Likely | — |
| Dominance: Good > Ok > Bad. The stronger copy decides the animal's output. | Video (outcome table) | Compare bred offspring to the table. |
| Top row = the expressed (winning) copy; bottom row = the carried copy. Not "mother's row / father's row". | Guess | Offspring of Good/Ok × Ok/Ok should never show Ok on top with Good underneath. |
| Each parent passes one of its two copies per gene, 50/50, independently per gene. | Video (outcome table) | Tally offspring over many births. |
| Ranch (NPC) animals are pure-bred: both copies identical. (The "one line" we saw is just the normal-player view, so there is no evidence for this.) | Guess | If true, a calf of two ranch animals never shows worse than the better parent on any gene. One grey calf from two green parents disproves it. |
| Offspring sex is 50/50. | Guess | Tally births. |
| Fertility affects cooldown and twin chance. | Video | Log births and twins against the mother's F gene. |

## Herd numbers and incest

| Rule | Confidence | How to test |
|---|---|---|
| A ranch animal's two herd numbers are the same. | Guess | Admin view only. |
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

## Observation log

Raw sightings, kept separate from the conclusions above. Genes are the top row only (normal-player view) unless noted.
G = green, O = grey, B = red. Order D L Y F H.

| Date | Server | Name | Species | Sex | Source | Genes | Herd | Coat | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-04 | test (admin) | Taylor | sheep | M | spawned | O O G G G | 15 | dark brown | Admin did not show a second row. |
| 2026-10-04 | test (admin) | Brenda | sheep | F | spawned | O G G O B | 14 | dark brown | Red H: Bad/Bad if dominance holds. |
| 2026-10-04 | test (admin) | Estella | sheep | F (lamb) | bought from ranch NPC | G B G O O | 6 | white | Bought as a lamb. |

Notes so far:
- Being admin did not show the second row, so the two-row card in the video came from something else (a debug command, or an older build). Unresolved; `find livestock` in the F1 console may show the relevant commands.
- Herd numbers seen: 14 and 15 (spawned together), 6 (bought). Looks like a per-animal or per-batch ID.
- Coat colour varies (white vs dark brown). Cosmetic or meaningful: unknown.

## Goal and strategy (provisional)

- **God bull:** a male that is Good/Good on all five genes. Every offspring of his shows all Good, whatever the mother carries.
- Animals are the scarce resource, so plans should **minimise purchases first and breeding cycles second**.
- **The hidden row has to be inferred.** Red (Bad) on the card means Bad/Bad, fully known. Grey means Ok/Ok or Ok/Bad; green means Good with any hidden copy. A god bull looks identical to a Good/Bad male, so he can only be identified:
  - **by pedigree:** probabilities for each hidden copy, worked out from recorded parents and every relative's card. This needs both parents recorded for every birth.
  - **by test-breeding** with a female showing red (Bad/Bad) on the gene in question. A grey or red calf proves the male carries a non-Good copy; n all-green calves leave a (½)ⁿ chance that he does anyway.
- A local server with admin would show both rows and allow free animals for testing these rules.
- Inbreeding is acceptable for building the god bull, if the incest penalty only affects output. A fresh female should then "clean" the line in one generation.
- Run experiments on sheep first (half the price), assuming cows follow the same rules.
