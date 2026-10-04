# Livestock Mechanics

What we believe about Rust's livestock breeding (added October 2026), how sure we are, and how to confirm it.
Update this file as in-game results come in; the breeding log in the app is the evidence.

Sources:
- **Video**: one YouTube video published around 2026-10-02.
- **Convars**: the descriptions printed by `find livestock` in the F1 console (test server, 2026-10-04). These come from the game itself, so they outrank the video.
- **Seen**: our own observations (see the log below).

Confidence: **Known** · **Likely** · **Guess** · **Unknown**

## Server variables (`find livestock`)

| Variable | Default | Description (game text, abridged) |
|---|---|---|
| `livestock.panelalleles` | False | Show both copies of every gene instead of only the one the animal expresses. "Reveals what an animal carries without breeding it." |
| `livestock.panelgenes` | False | Show the gene discs on the status panel, with the inbred warning. |
| `livestock.panelyield` | False | Show what the animal produces and how often, after its genes. |
| `livestock.paneldung` | False | Show how often it dungs, after its genes. |
| `livestock.paneltrust` | False | Show how much it trusts you, one segment per band of the trust ladder. |
| `livestock.panelgender` | False | Show ♂/♀ next to the name. |
| `livestock.panelage` | True | Show young or grown. |
| `livestock.inbredscale` | 0.5 | Every gene's slider position is multiplied by this on an inbred animal, for its coat and its production alike. At 0.5 Good looks and performs as Ok, and Ok falls halfway to Bad. An animal is inbred when both its lineage markers match. |
| `livestock.breedpausecondition` | 0.6 | At or below this condition an animal stops being willing to breed. |
| `livestock.breedresumecondition` | 0.7 | At or above this condition it is willing again. |
| `livestock.allowmounting` | True | Livestock can be loaded onto vehicle flatbeds. |

The list continued with a "Commands:" section that has not been captured yet.

## The animal card

| Item | Notes | Confidence |
|---|---|---|
| Name | Assigned by the game, in any script (a ranch sheep had a Cyrillic name). Stored as an image. | Known |
| Sex, status (e.g. Pregnant), age | Shown on the panel; sex symbol and age depend on server settings. | Known |
| Genes D L Y F H | **D**ung, **L**ifespan, **Y**ield (milk / wool), **F**ertility, **H**ardiness. | Known |
| Gene colours | Green / grey / red = Good / Ok / Bad bands. | Known (colours), Video (names) |
| Second row | Shown only when the server sets `livestock.panelalleles true`. Off on our live server and by default; the video's server must have had it on. | Known |
| 6th column | A **lineage marker** (the "herd number"). Two copies, like a gene. | Convars + Video |

## Genes

| Rule | Confidence | How to test |
|---|---|---|
| Each gene has two copies; the card shows "the one the animal expresses". | Known (Convars) | — |
| Genes are **continuous sliders**, and Good / Ok / Bad are bands on them. From the inbred description: Good ≈ 1, Ok ≈ 0.5, Bad ≈ 0. Two green animals can differ. | Likely (Convars) | Compare `panelyield` / `paneldung` rates of animals in the same band. |
| The expressed copy is the stronger one (Good > Ok > Bad), so red means both copies Bad. | Likely (Video + 50/50 genes seen) | With `panelalleles` on: does the top row always hold the higher of the two? |
| Each parent passes one of its two copies per gene, 50/50, independently per gene. | Likely (Video + first birth fits) | Tally offspring against parents' both rows. |
| Ranch and spawned animals are pure-bred (both copies identical). | **False** for spawned (Taylor, Brenda) and ranch-bought (Estella) | — |
| Coat colour depends on the genes ("its coat and what it produces"). | Likely (Convars) | Compare coat against gene values. |
| Fertility affects breeding cooldown and twin chance. | Video | Log births and twins against the mother's F. |
| Offspring sex is 50/50. | Guess | Tally births. |

## Lineage markers and inbreeding

| Rule | Confidence | How to test |
|---|---|---|
| Each animal has two lineage markers. An animal is **inbred when its own two markers match**. | Known (Convars + Elsie: 12/12, card says INBRED) | — |
| Each parent passes one of its two markers, like a gene. So a mating of relatives gives an inbred offspring only sometimes (25% when the parents share one marker). | Likely (first birth: 14 from mother, 15 from father) | With `panelalleles` on, compare offspring markers to the parents'. |
| Inbreeding multiplies the **expressed** gene sliders (coat and production) by `inbredscale`. Nothing says the genes passed on are changed. | Known (Convars + Elsie: inbred Good Y makes 2.0 wool/min, the same as Santos's Ok Y) for expression; Guess for passing on | Breed an inbred animal with an unrelated one and check the offspring. |
| Does inbreeding affect fertility or willingness to breed? | Unknown | Not mentioned in the convars. |
| Ranch/spawned animals' two markers: same or different? | Unknown | `panelalleles`. |

## Breeding conditions

| Rule | Confidence |
|---|---|
| An animal refuses to breed once its condition drops to 0.6 or below, and resumes at 0.7 or above. | Known (Convars) |
| Gestation, breeding cooldown, time to maturity | Unknown: log timestamps |
| Trust: animals have a trust ladder in bands. What it affects is unknown. | Known (exists) |
| Giving birth seems to cost health: Brenda went from 150 to 113 HP (−25%) after Brenda junior. If "condition" is HP / max HP she is at 0.75, just above the 0.7 resume threshold, and another birth would drop her below the 0.6 pause threshold. Recovery speed may set the real breeding cycle. Whether H (hardiness) changes the loss is unknown. | Seen once |
| A closing garage door can pass straight through an animal standing in its path (Brenda, test server). She survived, apparently through a clipping bug. Don't rely on that: keep doors clear of where animals stand. | Seen once |

## Economics

| Item | Value | Confidence |
|---|---|---|
| Sheep from ranch NPC | 150 scrap | Known |
| Cow from ranch NPC | 300 scrap | Known |
| Can genes be seen before buying? Can sex be chosen? | Unknown | — |
| Trips to the ranch are dangerous and often fail, so animals are scarce. | Known | — |
| Space per animal before a pen counts as overcrowded | Unknown | — |

## Observation log

Raw sightings. Genes are the expressed row unless noted. G = green, O = grey, B = red. Order D L Y F H.

| Date | Server | Name | Species | Sex | Source | Genes | Marker | Coat | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-04 | test | Taylor | sheep | M | spawned | O O G G G / **B B G B G** | 15 / **12** | dark brown | Second row via `panelalleles`. Dung 1 per 10 min, wool 16 per 3 min. |
| 2026-10-04 | test | Brenda | sheep | F | spawned | O G G O B / **O B O B B** | 14 / **4** | dark brown | Red H confirmed Bad/Bad. Dung 1 per 10 min, wool 16 per 3 min. A garage door closed through her; unharmed. |
| 2026-10-04 | test | Estella | sheep | F (lamb) | bought from ranch NPC | G B G O O / **B B O B O** | 6 / **0** | white | Bought as a lamb. Wool 16 per 3 min; no dung line shown (lamb?). |
| 2026-10-04 | test | Nettie | sheep | ? | spawned (1 white among 8) | G O G G G / **O B O O B** | 13 / **15** | white | Shares marker 15 with Taylor. Wool 16 per ? min, dung 1 per ? min (periods not recorded). |
| 2026-10-04 | test | Marcella | sheep | ? | spawned | O O O O G / **O O O O G** | 14 / **10** | brown | Same copies on every gene. Wool 10 per ? min (period not recorded), dung 1 per 10 min. Shares 14 with Brenda. |
| 2026-10-04 | test | Santos | sheep | M | spawned | O O O O O / **B O B O O** | 11 / **15** | brown | Wool 10 per 5 min (2.0/min), dung 1 per 10 min. |
| 2026-10-04 | test | Jay | sheep | M | spawned | O G G B O / **B G O B O** | 15 / **? (red)** | brown | L Good/Good. F Bad/Bad. Wool 16 per 3 min (5.3/min), dung 1 per 10 min. Second marker reported as "red": number to check. |
| 2026-10-04 | test | Brenda junior | sheep | ? (lamb) | **bred: Brenda × Taylor** | O G G B G / **B B G B B** | 14 / **15** | ? | Every gene and both markers possible under the model (see notes). Wool 16 per 3 min, no dung line. |
| 2026-10-04 | test | Angie | sheep | F | spawned | O O G O O / **B B O O B** | 13 / **8** | brown | Wool 16 per 3 min (5.3/min), dung 1 per 10 min. Shares 13 with Nettie. |
| 2026-10-04 | test | Elsie | sheep | F | **bred in the wild** by two spawned sheep (parents unknown; both carry marker 12) | O O G G G / **O B O O B** | **12 / 12** | brown | **Card says INBRED.** Wool 10 per 5 min (2.0/min) despite Good Y; dung 1 per 12 min. |

Notes so far:
- Where both rows are known (written top / second), the top copy is never weaker than the second: 50 genes across ten sheep, no exceptions. Consistent with "the stronger copy is expressed". Brenda's red H is Bad/Bad, as that rule predicts.
- **Rates must be compared per minute:** the panel changes the time period as well as the amount from animal to animal. Per minute so far: Good-Y wool 5.3 (Taylor G/G, Brenda G/O, Estella G/O, Jay G/O, Angie G/O, so the hidden copy seems not to matter); Santos (Ok/Bad Y) 2.0. Periods for Nettie and Marcella still to check.
- **Dung does follow D, in small steps:** inbred Elsie (Ok/Ok D, halved) dungs 1 per 12 min against 1 per 10 min for every non-inbred sheep. Earlier note, now superseded: Nettie expresses Good D yet shows the same 1 dung per 10 min as Taylor, Brenda and Marcella (Ok D). Either D doesn't change the shown rate, something else (food, condition, age) also drives it, or the panel rounds too coarsely to show the difference.
- Spawned animals are **not** pure-bred: Taylor carries Bad under Ok on D and L, and Bad under Good on F. His two markers differ (15 / 12).
- Markers seen: 15/12, 14/4, 13/15 (spawned), 6/0 (bought).
- **Sheep left together breed by themselves.** Elsie was born to two spawned sheep running loose. Keep males and females in separate pens on the live server, or you'll get unplanned (and possibly inbred) lambs.
- Lambs don't seem to dung: neither Estella nor Brenda junior has a dung line. Both make wool at the adult rate.
- **First birth (Brenda × Taylor):** the lamb's genes D Ok/Bad, L Good/Bad, Y Good/Good, F Bad/Bad, H Good/Bad and markers 14/15 are all one copy from each parent. The rows are not parent-specific: D's top copy came from the mother, H's from the father. Gestation was roughly 10 minutes (not timed).
- Coat colour varies (white vs dark brown); per the convars it reflects the genes. Of 8 sheep spawned together, 7 were brown and 1 white.
- **Coat hypothesis: white = Good D expressed.** Both white sheep (Estella, Nettie) express Good D; all six brown sheep with known genes (Taylor, Brenda, Marcella, Santos, Jay, Angie) express Ok D. Any brown sheep with green D disproves it. If true, Good-D animals can be spotted at the ranch by coat.
- **Markers are not unique:** Nettie and Taylor both carry 15; Marcella and Brenda both carry 14. 15 has turned up on four of seven sheep (Taylor, Nettie, Santos, Jay), so markers are not a uniform 0-15 draw.
- Marker circles may be coloured (the video showed a red 0 over a blue 1; Jay's second marker was reported as "red"). What the colour means is unknown. All markers seen are 0-15, so they look like random draws from a small range. Unrelated animals can share one, so a "fresh" mate still needs its markers checked.

## Goal and strategy (provisional)

- **God ram / bull:** a male that is Good/Good on all five genes. Every offspring of his expresses Good on every gene, whatever the mother carries.
- Animals are the scarce resource, so plans should **minimise purchases first and breeding cycles second**.
- On a server without `panelalleles` the hidden copy has to be inferred, by pedigree (needs both parents recorded for every birth) or by test-breeding against a female expressing Bad. On a server with it, the hidden copy is simply read off the card.
- Inbreeding looks safe for building the stud: per the convars it scales what an inbred animal *expresses*, not, as far as we know, what it passes on. A mate with different markers should give clean offspring. To confirm.
- Production needs condition ≥ 0.7 to keep animals breeding, so feeding and health are part of the cycle time.
- Run experiments on sheep first (half the price), assuming cows follow the same rules.
