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
| The expressed copy is the stronger one (Good > Ok > Bad), so red means both copies Bad. | Likely (Video + 20/20 genes seen) | With `panelalleles` on: does the top row always hold the higher of the two? |
| Each parent passes one of its two copies per gene, 50/50, independently per gene. | Video | Tally offspring against parents' both rows. |
| Ranch and spawned animals are pure-bred (both copies identical). | **False** for spawned (Taylor, Brenda) and ranch-bought (Estella) | — |
| Coat colour depends on the genes ("its coat and what it produces"). | Likely (Convars) | Compare coat against gene values. |
| Fertility affects breeding cooldown and twin chance. | Video | Log births and twins against the mother's F. |
| Offspring sex is 50/50. | Guess | Tally births. |

## Lineage markers and inbreeding

| Rule | Confidence | How to test |
|---|---|---|
| Each animal has two lineage markers. An animal is **inbred when its own two markers match**. | Known (Convars) | — |
| Each parent passes one of its two markers, like a gene. So a mating of relatives gives an inbred offspring only sometimes (25% when the parents share one marker). | Guess | With `panelalleles` on, compare offspring markers to the parents'. |
| Inbreeding multiplies the **expressed** gene sliders (coat and production) by `inbredscale`. Nothing says the genes passed on are changed. | Known (Convars) for expression; Guess for passing on | Breed an inbred animal with an unrelated one and check the offspring. |
| Does inbreeding affect fertility or willingness to breed? | Unknown | Not mentioned in the convars. |
| Ranch/spawned animals' two markers: same or different? | Unknown | `panelalleles`. |

## Breeding conditions

| Rule | Confidence |
|---|---|
| An animal refuses to breed once its condition drops to 0.6 or below, and resumes at 0.7 or above. | Known (Convars) |
| Gestation, breeding cooldown, time to maturity | Unknown: log timestamps |
| Trust: animals have a trust ladder in bands. What it affects is unknown. | Known (exists) |
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
| 2026-10-04 | test | Nettie | sheep | ? | spawned (1 white among 8) | G O G G G / **O B O O B** | 13 / **15** | white | Shares marker 15 with Taylor. |

Notes so far:
- Where both rows are known (written top / second), the top copy is never weaker than the second: 20 genes across four sheep, no exceptions. Consistent with "the stronger copy is expressed". Brenda's red H is Bad/Bad, as that rule predicts.
- Rates: Taylor and Brenda both express Good Y and Ok D and show identical rates (16 wool / 3 min, 1 dung / 10 min). Either each band has one fixed value, or slider differences are too small to show. Need an animal expressing Ok or Bad Y.
- Spawned animals are **not** pure-bred: Taylor carries Bad under Ok on D and L, and Bad under Good on F. His two markers differ (15 / 12).
- Markers seen: 15/12, 14/4, 13/15 (spawned), 6/0 (bought).
- Lambs may not dung: Estella's panel has no dung line. Recheck when grown.
- Coat colour varies (white vs dark brown); per the convars it reflects the genes. Of 8 sheep spawned together, 7 were brown and 1 white.
- **Coat hypothesis: white = Good D expressed.** Both white sheep (Estella, Nettie) express Good D; both brown sheep with known genes (Taylor, Brenda) express Ok D. Any brown sheep with green D disproves it. If true, Good-D animals can be spotted at the ranch by coat.
- **Markers are not unique:** Nettie and Taylor both carry 15. All markers seen are 0-15, so they look like random draws from a small range. Unrelated animals can share one, so a "fresh" mate still needs its markers checked.

## Goal and strategy (provisional)

- **God ram / bull:** a male that is Good/Good on all five genes. Every offspring of his expresses Good on every gene, whatever the mother carries.
- Animals are the scarce resource, so plans should **minimise purchases first and breeding cycles second**.
- On a server without `panelalleles` the hidden copy has to be inferred, by pedigree (needs both parents recorded for every birth) or by test-breeding against a female expressing Bad. On a server with it, the hidden copy is simply read off the card.
- Inbreeding looks safe for building the stud: per the convars it scales what an inbred animal *expresses*, not, as far as we know, what it passes on. A mate with different markers should give clean offspring. To confirm.
- Production needs condition ≥ 0.7 to keep animals breeding, so feeding and health are part of the cycle time.
- Run experiments on sheep first (half the price), assuming cows follow the same rules.
