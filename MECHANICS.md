# Livestock Mechanics

What we believe about Rust's livestock breeding (added October 2026), how sure we are, and how to confirm it.
Update this file as in-game results come in; the breeding log in the app is the evidence.

Sources:
- **Video**: one YouTube video published around 2026-10-02.
- **Convars**: the descriptions printed by `find livestock` in the F1 console (test server, 2026-10-04). These come from the game itself, so they outrank the video.
- **Seen**: our own observations (see the log below).

Confidence: **Known** · **Likely** · **Guess** · **Unknown**

## Published figures (RustHelp wiki, Facepunch, hosting guides, 2026-10-04)

These match everything we measured where we overlap (wool, dung, inbred ×0.8, gestation), so they are treated as reliable.
Sources: rusthelp.com/world/sheep and /cow, rust.facepunch.com/news/livestock, bisecthosting.com cow guide, plus search summaries of the wiki.

**Gene multipliers (Bad / Ok / Good; inbred Ok in brackets)**

| Gene | Bad | Ok | Good | Inbred Ok |
|---|---|---|---|---|
| D Dung | ×0.6 | ×1 | ×1.6 | ×0.8 |
| L Longevity | ×0.65 | ×1 | ×1.5 | ×0.825 |
| Y Yield | ×0.6 | ×1 | ×1.6 | ×0.8 |
| F Fertility | ×0.65 | ×1 | ×1.6 | ×0.825 |
| H Hardiness | ×0.7 | ×1 | ×1.5 | ×0.85 |

**Sheep and cows (Bad / Ok / Good)**

| Effect | Bad | Ok | Good |
|---|---|---|---|
| Lifespan (L) | 31h 12m | 48h (±10%) | 72h |
| Female cooldown after birth (F) | 1h 41m | 1h 6m | 41m 15s |
| Male cooldown after mating (F, sheep) | 15m 23s | 10m | 6m 15s |
| Litter size (F) | 1 | 1 | 1-2 (60% twins) |
| Hardiness (H): minimum need for full condition | 71% | 50% | 33% |
| Wool per fleece / regrow (Y, sheep) | 6 / 8m 20s | 10 / 5m | 16 / 3m 7s |
| Dung interval (D) | 16m 40s | 10m | 6m 15s |

- **Gestation 10 min.** Growth to adult: not published; we measured 60 min (Estella).
- **Wild animals roll each gene copy Good 20%, Ok 50%, Bad 30%.** So a wild animal is Good/Good on a given gene only 4% of the time, and shows Good on it 36% of the time.
- Breeding: adult female near an adult male, both with overall condition ≥ 0.7 (pauses at 0.6). Overall condition = the lowest of food, water and personal space.
- Inbred animals express weaker genes but still pass on their Good copies.
- Personal space: comfortable with up to 8 herd mates within 20 m; crowded beyond 12. Grazing and trough range 25 m. Wild group size: sheep 2-6, cows 1-4. Sheep HP 150.
- Taming (trust levels): Known 5 s, Tolerated 30 s, Bonded 5 min, Herd 15 min. Hurting the animal adds 60 s, hurting its herd 30 s.
- Selling: grown animals sell at the Stable / Large Barn vendor for a **randomised offer based on gene quality**; 3 offers, then it refuses for 15 min. **Wild and purchased animals sell at a penalty; bred animals at full value.** Wool trades for rewards, up to 400 per transaction.
- Buying calves (one guide's prices; may vary by server): wild Ok 373, wild Good 582, bred Ok 466, bred Good 700 scrap. So the vendor grades what it sells.
- Milk: tame adult cow, **1 milk per milking, every 5 min** (rusthelp; Y effect not stated, ×1.6 for Good if it follows the other genes). Spoils after 48 h. A powered fridge or vending machine skims 1 milk into 1 skimmed milk + 1 cream over 4 h. **Every Milky Pure tea = 1 Pure tea + 3 milk.** Pie amounts not found. Our use: milk goes into teas and pies, never into the biofuel generator. Open: does milk build up between milkings or cap at 1 like wool?
- Biofuel generator: organic matter → low grade fuel; output by calorific value; needs stirring about every 30 min. **Dung works but gives only 1 low grade each** (worthless); **milk isn't accepted.**
- Infrastructure: Animal Fence 250 wood, Fence Gate 500 wood, Hitch & Trough 200 wood (a cow drinks up to 200 ml per session).

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
| Lamb names | A bred lamb is **sometimes** named after **one parent** plus "Junior": Brenda Junior and Elsie Junior after their mothers, **Jay Junior after his father** (Estella × Jay). Guess: the parent of the lamb's own sex (Jay Junior has no horns yet: recheck once grown; female would disprove it). Not always: Dale (Taylor × Elsie, Elsie junior or Nettie) got a name of her own. Any "Junior" is bred; a lamb without it may still be bred. | Known |
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
| The expressed copy is the stronger one (Good > Ok > Bad), so red means both copies Bad. | Likely (Video + 84/84 genes seen) | With `panelalleles` on: does the top row always hold the higher of the two? |
| Each parent passes one of its two copies per gene, 50/50, independently per gene. | Likely (Video + both births fit) | Tally offspring against parents' both rows. |
| Ranch and spawned animals are pure-bred (both copies identical). | **False** for spawned (Taylor, Brenda) and ranch-bought (Estella) | — |
| Coat colour depends on the genes ("its coat and what it produces"). | Likely (Convars) | Compare coat against gene values. |
| Fertility affects breeding cooldown and twin chance. | Video | Log births and twins against the mother's F. |
| Offspring sex is 50/50. | Guess | Tally births. |

## Lineage markers and inbreeding

| Rule | Confidence | How to test |
|---|---|---|
| Each animal has two lineage markers. An animal is **inbred when its own two markers match**. | Known (Convars + Elsie: 12/12, card says INBRED) | — |
| Each parent passes one of its two markers, like a gene. So a mating of relatives gives an inbred offspring only sometimes (25% when the parents share one marker). | Likely (both births: one marker from each parent) | With `panelalleles` on, compare offspring markers to the parents'. |
| Inbreeding multiplies the **expressed** gene sliders (coat and production) by `inbredscale`. Nothing says the genes passed on are changed. | Known (Convars + Elsie: inbred Good Y makes 2.0 wool/min, the same as Santos's Ok Y) for expression. **Known: it does not pass down** (Elsie junior, non-inbred Good Y from inbred Elsie, makes the full 5.3/min). | Breed an inbred animal with an unrelated one and check the offspring. |
| Does inbreeding affect fertility or willingness to breed? | Unknown | Not mentioned in the convars. |
| Ranch/spawned animals' two markers: same or different? | Unknown | `panelalleles`. |

## Breeding conditions

| Rule | Confidence |
|---|---|
| An animal refuses to breed once its condition drops to 0.6 or below, and resumes at 0.7 or above. | Known (Convars) |
| **Overall happiness = the lowest of the conditions** (food, water, personal space): Lou 74/98/100 → 74; Elsie Junior food 53 → 53; Santos food 28 → 28. Food is usually the limiting one. A "GRAZED BARE" warning appears when the grass they graze is used up. | Known |
| What "condition" is: health fraction (Brenda 113/150 = 0.75 after a birth) or **happiness** (shown as a %; personal space feeds into it). Happiness fits the wording at least as well. Santos (back from outside, less food) and Elsie did not mate while under 70%; once over it they lay down together and Elsie became pregnant. Points to happiness, with food feeding into it. | Likely happiness |
| **Mating has no animation:** the pair just lie down together. The only sign is "Pregnant" on the ewe's card, so unplanned matings (through walls, after a restart) are invisible until then. Record a mating when Pregnant appears; the lamb's markers confirm the father. | Known |
| Gestation, breeding cooldown, time to maturity | Gestation roughly 10 min (not timed). The panel shows age in minutes. **Maturity at exactly 60 min** (Estella, test server); she grew to full size instantly. One generation ≈ 10 min gestation + 60 min growth. Live-server timers may differ. A grown sheep is much bigger, so a pen can become overcrowded when lambs grow up. |
| Trust: animals have a trust ladder in bands. What it affects is unknown. | Known (exists) |
| Giving birth seems to cost health: Brenda went from 150 to 113 HP (−25%) after Brenda junior. If "condition" is HP / max HP she is at 0.75, just above the 0.7 resume threshold, and another birth would drop her below the 0.6 pause threshold. Recovery speed may set the real breeding cycle. Whether H (hardiness) changes the loss is unknown. She later recovered to 150; recovery time and whether food matters not yet measured. | Seen once |
| Animals clip through walls: Jay slept with his head through the wall into the female stalls. Whether mating works through a wall is unknown. Bigger risk: if the game re-places an animal by its head position (on waking, server restart or area reload), it could end up in the other pen. Test by letting him wake, then restarting the server with him in that position. A corridor between the pens means a clipped animal lands in the corridor, not with the other sex. Check pens after every restart. Leave a gap (a one-foundation corridor or a double wall) between male and female pens, and breed in a separate room. | Seen once |
| **A lamb vanished from an upstairs room** (live server, one floor above ground, with food and water; base undamaged) over 14 hours that included the daily 09:05 restart (server down 09:05–09:09 on 2026-10-04 per Sentinel's log). Suspects: the restart re-placed it at ground level; despawn of an unowned or abandoned animal; death and decay - e.g. it stayed in one spot until the ground was grazed bare and starved (seen with a sheep beside a full trough). Test: before 09:00 place one cheap sheep each upstairs, in a ground-floor room on foundations, and on terrain inside animal fences; check all three after 09:10. If only the fenced one survives, animals need real ground (a fenced pen inside a high-walled compound would keep them protected). Until then keep animals on the ground floor. | Seen once |
| **Indoor starvation (test server, 2026-10-05):** two or three sheep in an indoor pen with a trough starved while sheep loose outside survived. Possibly a bug Facepunch will patch; until confirmed otherwise, start breeding in a fenced pen on terrain with a trough, and don't build an elaborate indoor farm. Recheck after each Rust update (findings here are from the October 2026 release). | Seen once |
| **Feeding is grazing in place, even indoors:** a sheep doesn't walk to the trough, it nibbles the floor where it stands and the trough (within range) feeds it. But the spot gets "GRAZED BARE" if it doesn't move, and a sheep that stays put starves next to a full trough (one fell to 0% food, 90/150 HP; it fed again once another sheep was led past and it shifted). Lone animals are most at risk, which may explain the lamb that vanished upstairs. Give pens room to wander, walk through on each visit, and watch for the GRAZED BARE bar on the card. | Known (seen once); mechanism inferred |
| **Lambs can't be sexed until grown** (no horns, same card portrait), and grown animals breed unsupervised, siblings included. A nursery is only safe for the ~60 min until they grow up. Single stalls don't work (a confined sheep grazes its spot bare and starves). A crowded nursery doesn't work either: crowded sheep get stuck and starve. **The workable answer is timing:** only mate when someone will be on to sort the lambs ~70 min later (10 gestation + 60 growth). | Known |
| **Sheep follow the one being led:** with 3+ in a small pen, others tag along and it's hard to bring out just one. Risk of a stray follower in the breeding room (unseen mating). Use a one-sheep airlock (two doors) between pen and breeding room, or individual stalls off a corridor. | Known |
| **Shearing:** hitting the same spot twice makes the sheep angry; it chases you for a long time (Elsie, while pregnant). Effect on trust, happiness or pregnancy: to check. | Known |
| A closing garage door can pass straight through an animal standing in its path (Brenda, test server). It glitches through them without hurting them, so garage doors are fine in pens. | Known |

## Economics

| Item | Value | Confidence |
|---|---|---|
| Sheep from ranch NPC | 150 scrap | Known |
| Cow from ranch NPC | 300 scrap | Known |
| Can genes be seen before buying? Can sex be chosen? | Unknown | — |
| Trips to the ranch are dangerous and often fail, so animals are scarce. | Known | — |
| **The map spawns wild sheep in grassland** (near barns). If they can be tamed and led home, they are a free alternative to buying. Wild rams near the base are also a risk of unseen, unplanned matings. **Taming:** adults are briefly hostile on approach; stand still, wait 30–60 s nearby, then they can be led. Easy on the test server, exposed on a busy one. Pick by coat from a distance (white = Good D) and read the card while waiting. **Wild sheep in a safe zone can't be tamed:** standing next to one for a long time never gave the Lead prompt. Wild genes/markers vs bought: unknown. | Known | — |
| Wool value | Shearing about 5 ewes that had gone unsheared for an hour or more gave ~100 wool (~20 each), worth next to nothing. **Wool is capped at about one batch per sheep:** it doesn't build up, so it only pays with shearing every few minutes. Y matters little in sheep. Value is more likely in dung (fertilizer, if it piles up unattended), milk (cows) or selling animals. | Known |
| Dung value | Only as fertilizer sold to the NPC, which pays well but has a small purse that takes hours to refill, so selling much is slow. The livestock update also added a **biofuel generator**. It takes food items, even spoiled ones, so milk is the likely livestock fuel (cows, Y gene). Dung gives only 1 low grade each, and milk isn't accepted. | Known |
| Shearing throughput | Each sheep takes a few seconds (two clean hits per side, sometimes repositioning). Wool is limited by player time, not herd size: with t seconds per sheep, a herd of 180/t Good-Y (or 300/t Ok-Y) sheep keeps one player busy; wool per hour ≈ batch × 3600/t (16 for Good Y, 10 for Ok). More sheep beyond that add nothing. | Known (mechanics); t to measure |
| Selling (test server) | Offers are item bundles, not a scrap price. Elsie junior (bred, shows O O G G G, Good/Ok on Y F H): offer 1 = SMG body + 30 HQM + 15 scrap; offer 2 = 44 pistol bullets + workbench fragment + 85 scrap; offer 3 = 24 HQM ore + 2 SMG bodies + 105 scrap (best). The offers look like a similar value budget filled with random items. **How offers work** (from a published table): the vendor has a list of items, each with a scrap value; it pays part of the animal's price in items and the rest in scrap. Compare offers by total scrap value (item values + scrap). Item values still to collect. Santos (spawned, shows Ok on all five, adult ram): offer 1 = 2 tarps + 2 "laptops" (targeting computers?) + 125 scrap; offer 2 = 1 tarp + 28 pistol bullets + 85 scrap; offer 3 = 32 incendiary pistol bullets + 1 camera + 5 scrap (offer 1 taken). Offer 1 clearly beats offer 2, so **each offer is a fresh random total**, not a fixed price split differently: compare gene grades by averages over several sales. **Offers come one at a time and a rejected offer is gone**, so it's a stopping problem: take a good offer 1, take any reasonable offer 2, and at offer 3 either accept or decline and retry after the 15-minute timeout (three fresh offers). So far wild all-Ok Santos's best offer is at least as good as bred Elsie junior's (three Good): the randomness swamps the gene and bred effects at this level. Needs more sales, or a big contrast (all Good vs mostly Bad), before planning around sale value. | Seen |
| Space per animal before a pen counts as overcrowded | 3 sheep in a 2×2 (≈12 m² each): personal space 83%, happiness 77%. Need readings at 2 and 4 sheep to see the curve. | Seen once |

## Observation log

Raw sightings. Genes are the expressed row unless noted. G = green, O = grey, B = red. Order D L Y F H.

| Date | Server | Name | Species | Sex | Source | Genes | Marker | Coat | Notes |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-04 | test | Taylor | sheep | M | spawned | O O G G G / **B B G B G** | 15 / **12** | dark brown | Second row via `panelalleles`. Dung 1 per 10 min, wool 16 per 3 min. |
| 2026-10-04 | test | Brenda | sheep | F | spawned | O G G O B / **O B O B B** | 14 / **4** | dark brown | Red H confirmed Bad/Bad. Dung 1 per 10 min, wool 16 per 3 min. Wool unchanged after her pregnancy and HP drop. A garage door closed through her; unharmed. |
| 2026-10-04 | test | Estella | sheep | F (lamb; grown at 60 min) | bought from ranch NPC | G B G O O / **B B O B O** | 6 / **0** | white | Bought as a lamb. Wool 16 per 3 min. No dung line as a lamb; once grown, dung 1 per 6 min and wool unchanged. |
| 2026-10-04 | test | Nettie | sheep | ? | spawned (1 white among 8) | G O G G G / **O B O O B** | 13 / **15** | white | Shares marker 15 with Taylor. Wool 16 per ? min, dung 1 per ? min (periods not recorded). |
| 2026-10-04 | test | Marcella | sheep | ? | spawned | O O O O G / **O O O O G** | 14 / **10** | brown | Same copies on every gene. Wool 10 per ? min (period not recorded), dung 1 per 10 min. Shares 14 with Brenda. |
| 2026-10-04 | test | Santos | sheep | M | spawned | O O O O O / **B O B O O** | 11 / **15** | brown | Wool 10 per 5 min (2.0/min), dung 1 per 10 min. |
| 2026-10-04 | test | Jay | sheep | M | spawned | O G G B O / **B G O B O** | 15 / **?** (seen as red; read the number) | brown | L Good/Good. F Bad/Bad. Wool 16 per 3 min (5.3/min), dung 1 per 10 min. Second marker reported as "red": number to check. |
| 2026-10-04 | test | Brenda junior | sheep | ? (lamb) | **bred: Brenda × Taylor** | O G G B G / **B B G B B** | 14 / **15** | ? | Every gene and both markers possible under the model (see notes). Wool 16 per 3 min, no dung line. |
| 2026-10-04 | test | Angie | sheep | F | spawned | O O G O O / **B B O O B** | 13 / **8** | brown | Wool 16 per 3 min (5.3/min), dung 1 per 10 min. Shares 13 with Nettie. |
| 2026-10-04 | test | Elsie | sheep | F | probably spawned (found among the spawns; has a dung line, which lambs lack). Possibly born in the wild: unconfirmed. | O O G G G / **O B O O B** | **12 / 12** | brown | **Card says INBRED.** Wool 10 per 5 min (2.0/min) despite Good Y; dung 1 per 12 min. |
| 2026-10-04 | test | Dorothy | sheep | F (lamb) | bought from ranch NPC | O O O O G / **B O O B ?** (second H not reported) | **11 / 11** | brown | Inbred, sold that way by the NPC. Wool 8 per 6 min (1.3/min), no dung line. |
| 2026-10-04 | test | Marie | sheep | F (lamb) | bought from ranch NPC | G O O O G / **B B B B G** | 13 / **14** | white | Wool 10 per 5 min (2.0/min), no dung line. |
| 2026-10-04 | test | Lori | sheep | F | bought from ranch NPC (assumed) | G G G O O / **O O O O O** | 4 / **15** | white | Good D, L, Y. Rates not recorded. |
| 2026-10-04 | test | Olga | sheep | F (lamb?) | bought from ranch NPC (assumed) | G O O G B / **B O B O B** | 13 / **2** | white | Good D and F. H Bad/Bad. Wool 10 per 5 min (2.0/min), no dung line. |
| 2026-10-04 | test | Stacie | sheep | F | not one of the 8 spawns (only white spawn was Nettie); source to confirm | G O O O O / **B B B B B** | 4 (cyan) / **10 (light green)** | white | Wool 10 per 5 min (2.0/min), dung 1 per 6 min. |
| 2026-10-04 | test | Lou | sheep | F | ? | O G G G O / **B B O B B** | 1 / **9** | ? | Age 2 hours. Wool 16 per 3 min, dung 1 per 10 min. First entered by hand with H wrong (Good); the card shows Ok. |
| 2026-10-04 | test | Laurie | sheep | F | spawned? (brown adult) | O G O G G / **B G O O B** | 1 (blue) / **5 (yellow)** | brown | L Good/Good. Wool 10 per 5 min (2.0/min), dung 1 per 10 min. |
| 2026-10-04 | test | Elsie junior | sheep | ? (lamb) | **bred: Elsie (inbred 12/12) × Santos** | O O G G G / **O O O O O** | 12 / **15** | ? | Not inbred. Every gene one copy from each parent. Wool 16 per 3 min (5.3/min): full rate, so inbreeding did not carry over from Elsie. |

Notes so far:
- Where both rows are known (written top / second), the top copy is never weaker than the second: 84 genes across seventeen sheep, no exceptions. Consistent with "the stronger copy is expressed". Brenda's red H is Bad/Bad, as that rule predicts.
- **Wool against Y value** (Good ≈ 1, Ok ≈ 0.5, inbred halves): 1.0 → 5.3/min (five sheep); 0.5 → 2.0/min (Santos, Marie, Olga, Stacie and Laurie, Ok; Elsie, inbred Good); 0.25 → 1.3/min (Dorothy, inbred Ok). Inbred Good matching Ok fits the convar text. Not a straight line: halving from 1 to 0.5 more than halves the rate, halving again cuts it by a third. A non-inbred red-Y sheep would give the bottom of the scale.
- **The NPC sells inbred animals** (Dorothy, 11/11). Check markers before buying. Ranch markers so far: 6/0, 11/11, 13/14: no sign of a different pool from spawned sheep.
- **Rates must be compared per minute:** the panel changes the time period as well as the amount from animal to animal. Per minute so far: Good-Y wool 5.3 (Taylor G/G, Brenda G/O, Estella G/O, Jay G/O, Angie G/O, so the hidden copy seems not to matter); Santos (Ok/Bad Y) 2.0. Periods for Nettie and Marcella still to check.
- **Dung follows D:** Good (Estella grown, Stacie) 1 per 6 min; Ok (six sheep) 1 per 10 min; inbred Ok (Elsie) 1 per 12 min. Like wool, the rate falls faster from Good to Ok than from Ok to inbred Ok. An earlier note that dung ignored D came from Nettie's reading without a period; hers is expected to be 1 per 6 min.
- Spawned animals are **not** pure-bred: Taylor carries Bad under Ok on D and L, and Bad under Good on F. His two markers differ (15 / 12).
- Markers seen: 15/12, 14/4, 13/15 (spawned), 6/0 (bought).
- **If Elsie was spawned, an animal can arrive already inbred:** both markers drawn from a small pool can match. Check a purchase's markers before relying on it as a clean mate.
- **The card's AGE line is only reliable on lambs.** Adult cards have shown "0 SECONDS" (Laurie, Taylor, Santos, Brenda Junior) and "15 MINUTES" for Brenda, hours old. Lamb ages looked right (Elsie Junior 9 min, Dale 46 min, Jay Junior 1 min). The app reads the age only when the portrait is a lamb's.
- **Card portrait:** every adult sheep has the same generic portrait, rams included (horns only show on the animal itself). Lambs have a different, lamb portrait. Sex appears on the card only with `livestock.panelgender true`.
- **Inbred cards** show a red "INBRED" label under GENETICS and a red box round the marker pair.
- Santos's card showed age "0 SECONDS" although he was adult: unexplained (perhaps age resets when a wild animal is tamed).
- **Lambs have no dung line;** every adult has one (lambs: Estella, Brenda junior, Dorothy, Marie, Olga).
- **Lambs show the adult wool rate for their Y:** Good 5.3/min (Estella, Brenda junior, same as adults), Ok 2.0/min (Marie, Olga, same as Santos). Estella's wool stayed at 16 per 3 min when she grew up, so wool does not depend on age. Only dung starts at maturity. Still open: whether a lamb actually yields the wool its panel shows.
- **First birth (Brenda × Taylor):** the lamb's genes D Ok/Bad, L Good/Bad, Y Good/Good, F Bad/Bad, H Good/Bad and markers 14/15 are all one copy from each parent. The rows are not parent-specific: D's top copy came from the mother, H's from the father. Gestation was roughly 10 minutes (not timed).
- Coat colour varies (white vs dark brown); per the convars it reflects the genes. Of 8 sheep spawned together, 7 were brown and 1 white.
- **Coat: white = Good D expressed** (6 white, all Good D: Estella, Nettie, Marie, Lori, Olga, Stacie; 8 brown, all Ok D). Earlier evidence: both white sheep (Estella, Nettie) express Good D; all six brown sheep with known genes (Taylor, Brenda, Marcella, Santos, Jay, Angie) express Ok D. Any brown sheep with green D disproves it. If true, Good-D animals can be spotted at the ranch by coat.
- **Markers are not unique:** Nettie and Taylor both carry 15; Marcella and Brenda both carry 14. 15 has turned up on four of seven sheep (Taylor, Nettie, Santos, Jay), so markers are not a uniform 0-15 draw.
- Marker circles may be coloured (the video showed a red 0 over a blue 1; Jay's second marker was reported as "red"). **Each number has its own colour, and some look alike.** Seen: 0 red, 1 blue (video, and Laurie), 2 light green, 4 cyan, 5 yellow, 10 light green, 13 orange, 14 purple, 15 green. A "number mod 8" pattern was ruled out by 5 (yellow) vs 13 (orange); 2 and 10 are probably two close shades. Read the number, not the colour. Jay's "red" second marker: number still to read.

## Goal and strategy (provisional)

- **God ram / bull:** a male that is Good/Good on all five genes. Every offspring of his expresses Good on every gene, whatever the mother carries.
- Animals are the scarce resource, so plans should **minimise purchases first and breeding cycles second**.
- On a server without `panelalleles` the hidden copy has to be inferred, by pedigree (needs both parents recorded for every birth) or by test-breeding against a female expressing Bad. On a server with it, the hidden copy is simply read off the card.
- **Inbreeding is safe for building the stud** (confirmed by Elsie junior): it only scales what the inbred animal itself expresses. A mate with different markers gives clean offspring at full production.
- Production needs condition ≥ 0.7 to keep animals breeding, so feeding and health are part of the cycle time.
- Run experiments on sheep first (half the price), assuming cows follow the same rules.
