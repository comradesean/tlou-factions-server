# Factions Metagame / Progression Reference

Research note, 2026-08-16. Public-source documentation of *The Last of Us: Factions*
(PS3, 2013, Naughty Dog) clan metagame, supplies economy, 12-week Journey, and unlock
schedule, gathered for server-side reimplementation.

**This note is entirely from public/online sources.** Nothing here is derived from the
EBOOT or from live capture except where explicitly labelled `[LOCAL-XREF]`. Where the
public record is silent or self-contradictory, that is stated rather than papered over.

## TL;DR for implementers

- **Gear is gated by ONE scalar: cumulative lifetime "supplies acquired".** Not rank, not
  population. The game's own tutorial text says so. Rank is decorative and gates nothing.
  A server reporting a large `supplies_acquired_lifetime` unlocks every non-DLC weapon,
  skill, and all 13 loadout points at once — **rank-up does not need implementing** to give
  players free gear choice. (§5.1, §5.2, §6.4)
- **Loadout points (PS3): start 8, max 13**, at 75 / 525 / 1650 / 3825 / 7500 supplies.
  Remastered starts at 9 — most online guides use Remastered numbers. (§5.2, §6.1)
- **Journey = 84 days = 84 matches.** 16 fixed event slots on days
  6, 11, 16 … 81 — exactly **every 5 days from day 6**. Event *flavour* is random; event
  *timing and risk band* are fixed. (§4.3)
- **Survivor states: healthy → hungry(starving) → sick → dead**, driven by consecutive
  daily supply shortfalls; surplus heals first, then recruits. There is **no fourth
  "at-risk" state** — "at risk" is an event-level risk percentage. (§2)
- **50 parts = 1 supply**, confirmed four ways. (§3.2)
- **Starting clan = 5** (`[LIKELY]`, pre-release sources only). (§1.2)
- **Survivor name pool recovered**: 82 given names × 76 surnames, from the leaked
  pre-release string table. Survivors carry only a name and a state — no traits. (§1.6)
- **Biggest remaining gaps**, all numeric and all needing the decompile or live testing:
  the daily supplies requirement formula (one clean data point: 96 pop → 82/day),
  the surplus-to-recruit rate, and the per-failed-day casualty counts. (§8)

## Confidence markers

| Marker | Meaning |
| --- | --- |
| `[CONFIRMED]` | Two or more independent sources agree, or it comes from Naughty Dog directly. |
| `[LIKELY]` | One good-quality source (wiki, published guide, ND interview) and nothing contradicting it. |
| `[UNVERIFIED]` | Single forum post / anecdotal player recollection. Treat as a hint, not a spec. |
| `[UNKNOWN]` | Actively looked for, not found. Do **not** guess these in code — make them configurable. |
| `[LOCAL-XREF]` | Cross-reference against this repo's existing static-recon output. |
| `[STRINGS]` | Taken from the leaked pre-release MP string table (see §0). First-party game text — the strongest evidence class in this note. |

### The single best source found: the leaked May-31-2013 string table

`[CONFIRMED]` The single-player demo bundled with *God of War: Ascension* (build dated
**May 31 2013**, ~2 weeks pre-launch) shipped with the **complete multiplayer string table
intact**. It was extracted and posted publicly, and Eurogamer reported on it at the time.

- Artifact: <https://pastebin.com/raw/kM7bFGy9> ("TLOU Network Strings - May 31 Demo")
- Contemporary reporting: <https://www.eurogamer.net/the-last-of-us-leaked-multiplayer-details-point-to-in-depth-clan-based-survival-mode>

**Authenticity checks I performed personally:**
1. Fetched the paste directly and confirmed it contains the strings claimed.
2. Eurogamer's two quoted sample strings ("is spit-roasting a raccoon", "Gangrene is
   beginning to set in for…") appear **verbatim** in the paste.
3. The paste's clan-event descriptions match the fandom wiki's independently-transcribed
   event text word-for-word (see §4.2).
4. Player reports of in-game messages match paste entries exactly (e.g. a GameFAQs poster's
   "planting kale in the garden" ↔ `[TEXT] is planting kale in the garden.`).

This is **first-party game text** and therefore outranks every wiki and guide in this note.
Two standing caveats:
- It is a **pre-release** build. The shipped PS3 table could differ. No retail extraction
  has been published. (This repo has working psarc extraction — see §7.3 — so verifying
  against retail is a cheap local task.)
- **The table is contaminated with Uncharted 3 leftovers.** Naughty Dog reused the
  localisation pipeline, so strings about `RANK`, `XP`, `TREASURE SETS`, `$40,000
  earnings_penalty`, `skill_rating`, and the "Uncharted: Drake's Fortune™ Multiplayer Pack"
  sit in the same file. **These are NOT Factions features.** I verified this by reading the
  surrounding lines: the `skill_rating` strings (paste lines ~1926-1957) are bracketed by
  `TREASURE SETS`, `Money`, `Competitive Wins`, and Uncharted DLC store prompts. Anyone
  pattern-matching this table to infer server fields must filter these out — see §8.

### Platform caveat, read this first

Several numbers differ between the **PS3 original (2013)** and **PS4 Remastered (2014)**.
This project targets the **PS3** build. The most important divergence is the starting
loadout-point count — see §6. Many community guides were written against Remastered and
silently use its numbers. Every figure below is tagged where a divergence is known.

---

## 1. The Clan / Survivors system

### 1.1 Shape of the metagame

`[CONFIRMED]` A player picks one of two factions — **Hunters** (blue) or **Fireflies**
(yellow) — and then runs a clan of survivors through a **12-week "Journey"**. One
completed match = one in-game **day**; 7 days = 1 week; **12 weeks = 84 days = 84
matches**.
- <https://thelastofus.fandom.com/wiki/Factions_MP>
- <https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide> — "the 'journey' the trophies refer to is 12 in-game 'weeks' (84 matches) of playing multiplayer."

`[CONFIRMED]` The faction choice is **cosmetic only**. From the wiki: "There are no
multiplayer abilities unique to either faction, and at the end of 12 weeks, choosing the
other faction does not reset the player's progress."
(<https://thelastofus.fandom.com/wiki/Factions_MP>)

`[CONFIRMED]` Naughty Dog's own framing, from MP designer **Erin Daly**: "Instead of just
earning XP and ranking up like most multiplayer games, when you start multiplayer you are
put in charge of a small group of survivors trying to stay alive and grow their numbers…
As you progress events will occur that put your survivors at risk and require you to
complete missions during your multiplayer matches to keep them alive. You must survive for
12 weeks with either the Hunters or Fireflies to beat the metagame."
(<https://www.naughtydog.com/blog/the_last_of_us_remastered_multiplayer_factions>)

Note ND's phrase "put your survivors **at risk**" — see §2.4 on the "at-risk" terminology.

### 1.2 Starting number of survivors

`[LIKELY]` **5.** Eurogamer's pre-launch interview with MP designer Erin Daly:
"Each player begins with a **clan of five people** chosen from one of two clans: the
Hunters and the Fireflies."
(<https://www.eurogamer.net/stealth-scavenging-crafting-and-clans-the-last-of-us-multiplayer-detailed>, 2013-06-04)

A second source repeats the figure: "Crew is filled with NPC survivors, **initially five**
but increasing exponentially with each match played — Start on Week 1, Day 1"
(<https://razielsdomain.forumotion.net/t14513p25-the-last-of-us>).

Caveats worth flagging honestly:
- **Both sources are pre-release (early June 2013) and probably trace to the same press
  event**, so this is not two genuinely independent confirmations.
- **No post-launch source gives a number at all.** Naughty Dog's own blog says only "a
  small group of survivors"; GameSpot "a small number of survivors"; TheSixthAxis "a
  handful of survivors"; Haywire Magazine "a few survivors – represented only by coloured
  dots in the menus"
  (<https://haywiremag.com/features/how-the-last-of-us-factions-still-endures-and-survives/>).
- No shipped-game screenshot showing Week 1 Day 1 population was found.
- Treat 5 as `[LIKELY]` for the retail build, not settled. Make it configurable.

### 1.3 What the "population" number is

`[CONFIRMED]` Population = the **count of living survivors in your clan**, a single
integer. It is the metagame's central state variable and it drives three separate things:
1. The **per-day supplies requirement** (bigger clan = bigger daily target). See §3.
2. The **magnitude of event gains/losses**, which are applied as *percentages* of current
   population. See §4.
3. A large slice of the **cosmetic unlock schedule** ("25 population", "85 population",
   …). See §5.3.

Sources: <https://thelastofus.fandom.com/wiki/Factions_MP>;
<https://www.gamedeveloper.com/design/my-favorite-features---meta-game-in-last-of-us-factions-multiplayer>
("The size of the clan also dictates the number of supplies a player would need to bring
back.")

**Is there a population cap?** `[STRINGS]` The string table contains `MAX CLAN SIZE`,
`MAX CLAN SIZE REACHED [A]`, `Your maximum clan size was [A]`, and
`The world's best clan size is [A]`. Read together — especially the last two — these look
like a **high-water-mark statistic and leaderboard**, not an enforced ceiling. A hard cap
would not need a "world's best" comparison.

`[UNKNOWN]` Therefore whether a hard cap exists is genuinely unresolved. Evidence on the
range: the highest population-gated unlock is the Black rancher hat at **120**; players
routinely report 99–130 ("I have been able to get my clan up to 130 during week 10");
and one N4G commenter passes on hearsay of "a clan size of 300". No source states a maximum.
Do not assume 999 — the only 999 in the record is the *weeks-survived* counter.
(<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66814187>,
<https://n4g.com/news/1289566/how-to-farm-supplies-in-the-last-of-us-multiplayer>)

`[CONFIRMED]` A related datum: the **"Populace" trophy is awarded at a clan of 40**, so 40
is comfortably expected to be reached in normal play.

### 1.4 How survivors are GAINED

Two mechanisms, and only two:

**(a) Supply surplus → recruiting.** `[CONFIRMED]` "Any extra supplies over the amount
needed will be used to entice other survivors to join your clan."
(<https://thelastofus.fandom.com/wiki/Factions_MP>). Note the priority order: surplus first
heals hungry/sick survivors, and only what remains recruits. PixlBit describes the order
explicitly: "When you don't meet that goal, clan members become sick or injured. This
means that any future supplies you receive are used to get those members up to healthy.
**Anything past that** increases your clan size."
(<http://www.pixlbit.com/blog/4028/last_of_us_multiplayer>)

`[UNKNOWN]` **How much surplus recruits one survivor.** No source gives a rate. This is one
of the two biggest numeric gaps in the whole metagame (the other is the daily requirement
formula, §3.3).

Three loose calibration anchors, in decreasing order of usefulness — enough to sanity-check
an implementation, not enough to derive the constant:

1. `[CONFIRMED]` **Growth curve anchor.** The "Populace" trophy is awarded for reaching a
   clan of **40**, and trophy guides say a normal player earns it "**by week 4**" — i.e.
   roughly **5 → 40 survivors in ~28 days** of ordinary play.
   (<https://www.playstationtrophies.org/game/the-last-of-us-remastered/trophy/89715-populace.html>,
   <https://psnprofiles.com/guide/6004-the-last-of-us-remastered-trophy-guide>) That is a
   genuinely useful acceptance test: whatever recruiting rate you implement should produce
   roughly this curve for an average player, given the §3.2 parts economy.
2. `[UNVERIFIED]` At population 99 with "close to 4k parts a match", a player gained
   "a survivor or two" "every other match" — small surplus, small integer gain.
   (<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66814187>)
3. `[UNVERIFIED]` "Usually around **4-5 people** gives you a one use booster" — that is a
   *booster* threshold, not a recruiting rate, and is listed here only so the two are not
   confused. (<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67242712>)

**(b) Event/mission percentage growth.** `[CONFIRMED]` Positive events grant
**+5% / +7% / +10%** of current population for mission completion tiers 1/2/3, and **0%**
for failing to reach tier 1. See §4 for the full calendar.
(<https://thelastofus.fandom.com/wiki/Factions_MP>)

### 1.5 How survivors are LOST

1. **Starvation/sickness progression** from missing the daily supplies target — §2.
2. **Negative events** (Hunter/Firefly Assault) — percentage losses up to **-100%**
   (total clan wipe) — §4.
3. **Quitting a match** — §3.5.

### 1.6 Survivor NAMES — do individual survivors have identities?

This was a specific question for the revival project, so here is the full picture including
what is *not* known.

`[CONFIRMED]` **Survivors have individual randomly-generated names, drawn from a built-in
name pool, and this happens with or without Facebook.** A player describing the retail
game: "To make your clan more personal, **the game randomly generates names** for the
people in your clan and then tells you what they're doing every once in a while… ALL OF THE
NOTIFICATIONS IN THIS COMIC CAME DIRECTLY FROM THE GAME"
(<https://www.deviantart.com/thegouldenway/art/Factions-Week-1-Clan-Notifications-429588848>).

#### The name pool — RECOVERED

`[STRINGS]` The pool is present in the leaked string table (§0) as two contiguous
newline-separated blocks. **I verified this directly**, not just via the summary: the blocks
occupy paste lines **422–503** (given names) and **504–579** (surnames).

**82 given-name entries** (80 unique — `Adam` and `Ethan` each appear twice):

> Aaron, Joe, Arnaldo, Trevor, Robert, Claire, Alison, Raul, Adam, Adam, Adrian, Alex, Amy,
> Andres, Ana, Malcolm, Carson, Carlos, David, Rodney, Olivia, Jennifer, Sandra, Chris,
> Kion, Troy, Beverly, Ryan, Nara, Jin, Tyler, Anthony, Kurt, Eric, Jacob, Justin, Bruce,
> Neil, Peter, Sofia, Mia, Isabella, Santiago, Mateo, Diego, Ricky, Quentin, Artem,
> Christian, Jeremy, Jesse, Lauren, Edward, Max, Kan, Aliyah, Jordan, Kayla, Madison,
> Cameron, Ethan, Ethan, Kevin, Jane, Mike, Michael, Damon, Cynthia, Jose, Spencer,
> Stephanie, Sean, Ava, Alexander, Aiden, Ivan, Lars, Bernard, Simon, Scott, Maria, Matthew

**76 surname entries** (75 unique — `Diaz` appears twice):

> Stevens, Cho, Lin, Brown, De Silva, Kim, Singh, Nakata, Lee, Espino, Ly, Lam, Vasquez,
> Park, Newman, Goldman, Saito, Tanaka, Garcia, Rodriguez, Martinez, Diaz, Diaz, Chong,
> Choi, Wong, Chan, Chen, Ng, Cheung, Nguyen, Tran, Castillo, Reyes, Santos, Ahmadi, Cook,
> Khan, Patel, Shah, Williams, Jackson, Davis, Walker, Carter, Anderson, Ramirez, Thomas,
> Martin, Dubois, Kowalski, Nowak, Jones, Bauer, Moser, Lukic, Petrovic, Jensen, Salo,
> Karlsson, Leroy, Schmidt, Fischer, Vlahos, Nagy, Varga, Murphy, Murray, Wilson, Johnson,
> Clark, Mitchell, Campbell, Parker, Cohen, Levi

That yields **82 × 76 = 6,232** name combinations (6,000 distinct). The duplicated entries
are almost certainly deliberate weighting, not errors — worth preserving verbatim if you
want bit-identical name generation.

Caveats, stated plainly:
- **The split point between the two blocks is inferred, not labelled.** The paste is a flat
  dump with no field names. The boundary at `…Maria, Matthew` → `Stevens, Cho…` is
  semantically obvious (the second block is entirely surnames) and I am confident in it,
  but it is inference. Note that an automated summariser reading the same paste guessed a
  *different* split point, which is exactly why I read the raw lines myself.
- **Pre-release build.** Not verified against retail. See §7.3.
- Nearby placeholder/debug names — `George P.` / `Burdell` (a well-known fictitious-student
  joke name), and `Dan` / `Smith` / `Russel` / `Bill` — look like UI mock data and are
  probably **not** part of the random pool. Flagged rather than filtered.

#### Survivor attributes

`[STRINGS]` **Survivors have a name and a health state, and nothing else.** The only
per-survivor state in the table is a four-value enum:

```
[TEXT] is healthy.    [TEXT] is starving.    [TEXT] is sick.    [TEXT] has died.
```

There is **no** age, gender, skill, trait, or local portrait field anywhere in the table.
Gender is implied by the given name only. Facebook profile pictures are the sole portraits.
"Training" in mission text is always applied to the **whole clan** ("Improve the training of
the group"), never to an individual. A contemporary review agrees: "These people are only
ever numbers and text to you however, diminishing the attachment somewhat."
(<https://criticalgamer.co.uk/2013/06/20/the-last-of-us-multiplayer-review/>)

**Implication for the server:** a survivor is essentially `(name, state)`. The roster is
cheap to represent. `[UNKNOWN]` whether names are generated **client-side** (in which case
the server may only need a seed or index per survivor) or assigned **server-side**. Since
the pool ships in the client's own string table, client-side generation is the more likely
design — but this must be verified, because it changes the wire format materially.

`[STRINGS]` A `Clan Roster` screen string exists, so a browsable per-survivor list was
built. `[UNKNOWN]` whether the unlinked roster shows a name per dot — no screenshot found.

#### Facebook integration

`[CONFIRMED]` Optional and **additive**: "Clans can be linked to the players Facebook
account, allowing survivors to be represented by the player's friends list and profile
pictures." (<https://thelastofus.fandom.com/wiki/Factions_MP>) The string table shows it is
opt-in and *overwrites* names on an already-populated clan rather than creating them:
`Populate your clan with your friends' Facebook names.` / `Populate your clan with Facebook
friends?` / `CONNECT TO |FB| FACEBOOK` / `NO, THANK YOU`.

The wiki calls the feature "**purely cosmetic and does not change the gameplay or effects of
events or days**". **That is not quite right, and the correction matters:** `[STRINGS]`
`Linking to Facebook also gives you 3 One-Use Boosters.` So Facebook linking has exactly one
non-cosmetic effect — a **one-off grant of 3 One-Use Boosters**. A revival server can
otherwise ignore Facebook without altering metagame behaviour.

`[CONFIRMED]` The "choose who lives" screen at attack events is real — first-hand: "During
attack periods, sometimes I was asked to choose which friend would live between 3 of them."
(<https://thegamefanatics.com/hold-that-molotov-why-the-last-of-us-had-the-most-underrated-multiplayer-of-the-last-decade/>)

`[STRINGS]` **but the mechanic is parameterised, not fixed at "three, pick one"** — the wiki
description is a common case, not the rule:
```
[A] of your friends were badly injured by the [ENEMY-FACTION-PLURAL]. You can help [B] of them.
[A] of your friends were badly injured by the Infected Horde. You can help [B] of them.
[A] of your friends were badly injured in the Marauder attack. You can help [B] of them.
[A] of your friends were badly injured in the Infected attack. You can help [B] of them.
[A] of your friends are starving. You can feed [B] of them.
```
Note the last line: **the same N-of-M chooser is also used for starvation**, not only
attacks. Note also that these strings say "friends" unconditionally and are not gated behind
a Facebook-only string, which supports the screen appearing for unlinked players too
(`[LIKELY]`, no unlinked report found).

#### Lobby activity messages — full pool recovered

`[STRINGS]` The wiki is right that these are **state-reactive** ("if there are more hungry
survivors… the messages will change into more alarming ones such as clan survivors having a
nervous breakdown or considering cannibalism"). The complete pool is in the string table,
grouped by state. Every message names an individual via a `[TEXT]` token. No prior
transcription of this appears to exist online.

**Starving:**
```
[TEXT] is beginning to feel faint.          [TEXT] is desperate for food.
[TEXT] is gnawing on rat bones.             [TEXT] has terrible hunger pains.
[TEXT] can barely walk.                     [TEXT] is very malnourished.
[TEXT] has lost 15 pounds from malnourishment.
[TEXT] is starting to consider cannibalism. [TEXT] is considering eating the cat.
[TEXT] is trying not to think about food.   [TEXT] is accusing others of hoarding food.
[TEXT] is too weak to work.                 [TEXT] went into shock from hunger.
[TEXT] has started praying.                 [TEXT] has got the shakes.
[TEXT] did not get up from bed this morning.
```

**Sick:**
```
[TEXT] has been coughing a lot lately.      Gangrene is beginning to set in for [TEXT].
[TEXT] needs antibiotics right away.        [TEXT] is starting to look pretty far gone.
Everyone's getting worried about [TEXT].    No one is sure how much longer [TEXT] can hang on.
The situation for [TEXT] is looking pretty bad.
[TEXT] caught botulism from a can of old food.
[TEXT] has a severe infection.              [TEXT] has an intense fever.
[TEXT] can't stop coughing.                 [TEXT] hasn't slept in days.
[TEXT] had a mental breakdown.              [TEXT] is having a severe allergic reaction.
[TEXT] is coughing up blood.                [TEXT] has symptoms of pneumonia.
[TEXT] has a serious concussion.            [TEXT] is having severe hallucinations.
[TEXT] may have become infected.            [TEXT] is showing early signs of scurvy.
[TEXT] is shivering and feverish.           [TEXT] may require an amputation.
[TEXT] has contracted dysentery.            [TEXT] has a severe flu.
```

**Healthy** (~80 entries, abridged here; full list in the paste):
```
[TEXT] is exercising.                       [TEXT] is sharpening a machete.
[TEXT] is setting up perimeter alarms.      [TEXT] is cleaning the latrine.
[TEXT] is gathering nuts and berries.       [TEXT] is taking inventory.
[TEXT] is making moonshine.                 [TEXT] is making bombs.
[TEXT] is spit-roasting a raccoon.          [TEXT] is planting kale in the garden.
[TEXT] is repairing the north/west/east/south fence.
[TEXT] is reinforcing the main gate.        [TEXT] is reinforcing the rear gate.
[TEXT] is upgrading the water filtration system.
[TEXT] is digging an evacuation tunnel.     [TEXT] is learning guitar.
[TEXT] found an old cookbook.               [TEXT] JOINED YOUR_CLAN!
…
```
Quirks preserved from the source: the game's own typo `racoon` appears alongside `raccoon`;
`[TEXT] is skinning a deer.` is duplicated; and `[TEXT] is having a nervous breakdown.` is
filed in the **healthy** block, not the sick one — so the wiki's claim that breakdown
messages signal a hungry clan is not supported by the table's own grouping.

Also present: a weekly summary line `This week you did laundry and took out the trash.` and
`Members Dead: [A], Members Got Sick [B]`.

---

## 2. Survivor states: healthy / hungry / sick / at-risk

### 2.1 The states

`[STRINGS]` **Exactly three living states plus dead.** Per-survivor enum from the game's own
text:
```
[TEXT] is healthy.    [TEXT] is starving.    [TEXT] is sick.    [TEXT] has died.
```
Note the vocabulary split: the **per-survivor** message says *starving*, while the
**aggregate counter** is labelled *HUNGRY*. Same state, two labels.

`[STRINGS]` The clan panel counters:
```
POPULATION: [A] SURVIVORS      HEALTHY: [A]      HUNGRY: [A]      SICK: [A]
Hungry     Sick     Killed     Added
Supplies Needed: [A]           Supplies Gathered by Clan: [A]     Surplus/Deficit: [A]
WEEK [A]: DAY [B]              DAYS SURVIVED     CLAN SIZE
```
So the daily settlement UI is literally *needed / gathered / surplus-or-deficit*, which is
a strong hint that the underlying model is a single scalar comparison, not a per-survivor
simulation.

`[CONFIRMED]` Corroborated by the published guide and by players. TrueTrophies documents
the same panel: "**Number of Survivors**: This shows the number of TOTAL survivors in your
camp. **Healthy**: … healthy and thriving. **Hungry**: … hungry and *at risk of being
sick*. **Sick**: … sick and *at risk of dying*."
(<https://www.truetrophies.com/game/The-Last-of-Us-Remastered/walkthrough/17>)
A player quotes the UI showing all three at once: "Only got 96 survivors and it says I need
82 supplies a day. Maybe cause **5 are sick and 24 hungry**…"
(<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66814187>)

### 2.2 Transitions — what the sources actually say

`[STRINGS]` The game states the whole model in one sentence: "**A surplus of Supplies
|SUPPLIES| keeps your clan healthy and growing. A deficit will cause your people to get
hungry, sick, and eventually die.**" This is the authoritative statement of the chain.

`[CONFIRMED]` The documented chain is **healthy → hungry → sick → dead**, driven by
*consecutive* failures to meet the daily supplies target:

> "If you fail to reach the required amount, the shortfall will result in some of your
> survivors becoming **hungry**. Fail to reach it again and a number of your people will
> become **sick** and eventually **die**."

That phrasing appears in the PlayStation official user guide material and is echoed by the
wiki and by the community video guide.
- <https://thelastofus.fandom.com/wiki/Factions_MP>
- <https://www.youtube.com/watch?v=NfLYMnZwB-k> (DeltaCanuckian, *12 Weeks Metagame*): "if
  the target amount is not reached survivors will begin to get hungry or get sick and die."
- <https://www.gamedeveloper.com/design/my-favorite-features---meta-game-in-last-of-us-factions-multiplayer>:
  "When a player did not bring back enough supplies, clan members would get sick and
  eventually die decreasing the size of the clan."

`[CONFIRMED]` **Healing is via surplus**: "Hungry and sick survivors can be healed by
collecting more than the target amount of supplies during each day."
(<https://thelastofus.fandom.com/wiki/Factions_MP>) DeltaCanuckian: "hungry and sick
survivors can be healed by **meeting or exceeding** the supply target every in-game day."

Note the mild conflict: the wiki says healing requires *exceeding* the target; the video
guide says *meeting or exceeding*. `[UNVERIFIED]` which is exact at the boundary. Low
stakes, but pick one deliberately and document it.

### 2.3 What is NOT known about the state machine

These are the gaps that a faithful reimplementation actually needs, and the public record
does not close them. Do not invent values silently:

- `[UNKNOWN]` **How many survivors transition per failed day.** Every source says "some" /
  "a number of". Nothing says whether it is proportional to the size of the shortfall, a
  flat fraction of population, or a flat count. I searched specifically for a
  "1 survivor per X supplies short" style rule and found none anywhere.
- `[UNKNOWN]` **Whether sick → dead takes one further failed day or several.** The best
  indirect evidence is the tactical-quitting recipe, which implies **two consecutive
  zero-supply days** take a fully-healthy clan to "some dead, rest hungry and sick": "have
  a **fully healthy clan** … afterwards you can **quit twice in a row**. Subsequent, a few
  of your survivors will be dead and you will only have hungry and sick ones left. Thus
  **every third game** you will be busy getting your clan healthy again."
  (<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>) That is
  consistent with a one-stage-per-failed-day decay affecting a *portion* of each cohort,
  and with one good day restoring the whole clan — but it does not prove either.
- `[UNKNOWN]` **Whether healing steps sick → hungry → healthy, or jumps sick → healthy
  directly.** PixlBit's "any future supplies you receive are used to get those members up
  to healthy" hints at a direct jump but is not decisive.
- `[UNKNOWN]` **The supply cost of healing one hungry vs. one sick survivor** (they are
  very likely different, but nothing states it).
- `[UNKNOWN]` **Whether hungry/sick survivors still consume their full daily ration.** The
  one observed data point (96 population → 82 required, with 5 sick + 24 hungry) is
  *suggestive* that non-healthy survivors are weighted differently in the requirement
  calculation — 82 is notably less than 96 — but a single observation cannot distinguish
  that hypothesis from a simple sub-linear population curve. See §3.3.

### 2.4 "At risk"

`[CONFIRMED]` **"At risk" is NOT a fourth per-survivor health state.** Two independent
lines of evidence:

1. `[STRINGS]` The string table's per-survivor enum has exactly four values
   (healthy / starving / sick / died) and the clan panel has exactly three counters
   (HEALTHY / HUNGRY / SICK). **There is no "at risk" counter or state string.**
2. Where guides use the phrase, it is descriptive prose about the *next* transition, not a
   category: TrueTrophies glosses **Hungry** as "hungry and *at risk of being sick*" and
   **Sick** as "sick and *at risk of dying*".
   (<https://www.truetrophies.com/game/The-Last-of-Us-Remastered/walkthrough/17>)

Separately, Naughty Dog uses "at risk" at the **clan/event** level — Erin Daly: "events will
occur that **put your survivors at risk** and require you to complete missions… to keep them
alive." (<https://www.naughtydog.com/blog/the_last_of_us_remastered_multiplayer_factions>)
And `[STRINGS]` the event UI renders that as a percentage, not a state:
`RISK: |@CFFFF3030|[A]% OF POPULATION`.

**Model it as:** a property of the *active event* (`risk_pct`), plus prose framing of the
existing hungry/sick states. Do **not** add a fourth survivor state.

---

## 3. Resources / supplies economy

### 3.1 Two distinct currencies — keep them separate

`[CONFIRMED]` **Parts** are the *in-match* currency and score. **Supplies** are the
*metagame* currency. They are different things with different lifetimes.

- Parts are spent in the in-match store on ammo, weapon upgrades, armour, and purchasable
  weapons. Critically: "The use of parts during a match to purchase items and upgrades
  **does not affect** the amount of parts you will earn at the end of the match." Parts do
  not carry between matches, but do carry between lives/rounds within a match.
- Supplies persist into the metagame and feed the clan.

(<https://thelastofus.fandom.com/wiki/Factions_MP>)

### 3.2 How supplies are earned

`[CONFIRMED]` **Conversion rate: 50 parts = 1 supply.** Stated by the wiki
(<https://thelastofus.fandom.com/wiki/Factions_MP>), independently by the DeltaCanuckian
video guide ("50 Parts equaling one Supply",
<https://www.youtube.com/watch?v=NfLYMnZwB-k>), and independently confirmed by players
arithmetically on GameFAQs ("50/1 — 50 parts = 1 supply";
"I just got 3,900 and got 85 (some extra for picking up the ones left by dead bodies)" —
3900/50 = 78, plus pickups ≈ 85, which checks out).
(<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66814187>)

`[CONFIRMED]` **Second source of supplies: blue bottle/canister pickups** dropped by
downed/executed enemies, picked up off their bodies. These are *in addition* to the parts
conversion. In Supply Raid dropped supplies persist for the whole match and show on radar;
in Survivors they respawn each round.
(<https://thelastofus.fandom.com/wiki/Factions_MP>)

`[LIKELY]` **Population does NOT affect the conversion rate.** Naughty Dog's own
"Supply Drop" event post treats the rate as a single global tunable constant, and
explicitly separates it from enemy drops: "The Last of Us Supply Drop event will see an
**increase to the parts to supplies conversion**. … However, **we didn't alter the number of
supplies an enemy will drop when they are killed.**"
(<https://www.naughtydog.com/blog/the_last_of_us_supply_drop_and_uncharted_3_rare_treasure_drop_july_4th_even>)
That is good evidence the parts→supplies rate and the enemy-drop amount are two separate
global constants, neither population-scaled. **A revival server should expose both as
tunables** — ND itself changed them for events, so the client must tolerate it.

`[UNVERIFIED]` **Value of one blue can = 5 supplies**, per one experienced player:
"in Survivors, each supply can you pick up will credit your quota by 5 during the game. In
addition to this, it will also add 5 to your converted score for each one you grabbed.
That's 10 supply cans for each defeated enemy! I am not sure, but I believe this is NOT the
case for other game modes."
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556> — thread
"Earning more supply points as population increases in Factions"; the poster hedges twice
in his own sentence). **Single source, self-doubted, do not treat as spec.**

`[CONFIRMED]` **Parts payout table** (per action, in-match):

| Action | Parts |
| --- | --- |
| Downed opponent | 100 |
| Execution | 50 |
| Special execution | 75 |
| Assist | 50 |
| Marked opponent | 15 |
| Marked target killed | 25 |
| Revive | 100 |
| Craft item | 30 |
| Gift handed to a teammate | 100 |
| Molotov kill | 25 |
| Bomb kill | 25 |
| Shiv kill | 75 |
| Heal a teammate | 20 per 2s (First Aid Training 2) / 40 per 2s (First Aid Training 3) |

(<https://thelastofus.fandom.com/wiki/Factions_MP>)

Two skills increase parts earned (Collector, Reviver), and the "Increased Parts Earnings"
one-time booster adds +10% (explicitly *not* applying to parts from healing teammates or
gifting). Note the interaction: because supplies derive from parts, **support play
out-earns combat play for metagame purposes** — a well-attested community finding, and a
useful sanity check for anyone validating an economy implementation.
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>)

### 3.3 The per-day supplies REQUIREMENT — the biggest gap

`[CONFIRMED]` A target exists and is population-derived: "At the start of every game, the
player will be told the target amount of supplies needed to keep the clan healthy."
"Supplies are the main currency needed to sustain the clan in multiplayer and **changes
based on the number of survivors** within the player's clan."
(<https://thelastofus.fandom.com/wiki/Factions_MP>)

`[UNKNOWN]` **The formula.** No source — wiki, guide, ND interview, or datamine — publishes
it. This is the single most important missing number in this document.

**Observed data points**, such as they are. These are all I could find; both are forum
posts, so `[UNVERIFIED]`:

| # | Population | Stated daily requirement | Quality | Source |
| --- | --- | --- | --- | --- |
| A | **96** (67 healthy / 24 hungry / 5 sick) | **82 supplies/day** | best pair — a direct UI readout | <https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66814187> |
| B | **99** | ~"slightly under" 80 + can pickups | approximate, inferred from "close to 4k parts … slightly over the total amount I needed" | same thread |
| C | ~80+ | ≥ ~79 implied | player's *earning* ceiling, not a quoted requirement — weak | <https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556> |
| D | not stated | **160 supplies/day** | requirement quoted but population omitted — useless for fitting, but bounds the top end | <https://n4g.com/news/1289566/how-to-farm-supplies-in-the-last-of-us-multiplayer> |

The one clean pair (A) gives ≈ **0.85 supplies per survivor per day**, and pair (B) lands in
the same neighbourhood. Treat this as an order-of-magnitude anchor only. With effectively
n=2 in a narrow population band (96–99) it cannot distinguish between:
(a) a flat ~0.85/survivor rate; (b) a sub-linear curve passing through those points; or
(c) a rate that weights hungry/sick differently from healthy — note 82 ≈ 67 healthy × 1.22,
and the poster in (A) himself wondered whether the sick/hungry counts fed the target. **Not
separable from this data.**

Data point (D) at 160/day would imply ~190 survivors at 0.85/head, and a commenter in that
same thread claims hearsay of "a clan size of 300" — so *if* the relationship is linear it
stays linear well past 100. That is consistent with, but does not establish, linearity.

**Recommendation:** implement the requirement as a pluggable function of
`(population, healthy, hungry, sick)` with a default of `round(0.85 × population)`,
clearly commented as an unverified two-point fit, and gather real pairs from live testing
to refine. Do not hard-code it as though it were known. `[STRINGS]` The UI is
`Supplies Needed: [A]` / `Supplies Gathered by Clan: [A]` / `Surplus/Deficit: [A]`, so the
server needs to send only the single computed target — the client does not appear to
compute it itself.

### 3.4 Priority of supply spending

`[CONFIRMED]` Order of application at end of day: (1) meet the daily requirement,
(2) surplus heals hungry/sick, (3) any remaining surplus recruits new survivors. See §1.4.

### 3.5 Quitting a match, and late joining

`[CONFIRMED]` **Quitting mid-match penalty:** "If you quit a multiplayer match, you won't
get any supplies for your survivors, some of your healthy survivors become hungry or sick,
and others die. But at the same time you will **advance one day**."
(<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>) The
gamedeveloper.com design write-up agrees: leaving "will make parts of their clan sick while
also losing progress made in a match as well as **still counting as a day**."

`[UNVERIFIED but important]` **Zero-healthy-survivors rule:** "If you have 0 healthy
survivors and you quit a match, you will lose your whole clan."
(<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>) Single
source, but it is a widely-followed published guide whose entire "tactical quitting"
strategy depends on the rule being true, so it is better-attested in practice than a bare
forum claim.

`[UNVERIFIED]` Exact counts of how many die/sicken on a quit: not stated anywhere.

`[CONFIRMED]` **Two distinct quit paths, with different day semantics** — important for
server logic:

| Path | Day advances? | Penalty |
| --- | --- | --- |
| In-game / pause-menu quit, or being kicked | **yes** | no supplies; some healthy → hungry/sick; some die |
| Quit to XMB / close the app / sign out | **no** | match treated as if never started — *except* an equipped One-Use Booster is still consumed |
| Disconnect / lose connection to host | **no** (post-patch) | — |

- "you can quit out of the game by holding down the PS button… and selecting 'Quit Game'
  DURING a multiplayer match and when you go back into the game you'll notice that the day
  you were playing did not count."
  (<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>)
- "Quitting the match via the pause menu will still advance the days. The way to quit
  without it counting against you is to **close the Last of Us application completely**."
  (<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69897154>)
- "if you use a one time booster and quit the match, it will be gone, even though everything
  else resets as if you had never started the first match."
  (<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67320819>)
- **Official patch note** `[CONFIRMED]`: "Disconnecting or losing connection to the host
  will no longer advance a clan day. Clan days will only be advanced if the player is
  **kicked from a match or exits using the menu**."
  (<https://thelastofus.fandom.com/wiki/The_Last_of_Us/Patch_notes>)

That patch note is the cleanest statement of the rule and should be the implementation
target: **day advances iff the player was kicked or exited via the in-game menu.** Note it
is a *post-launch* change — a revival targeting a specific PS3 patch level should check
which behaviour that build expects.

`[CONFIRMED]` **Late join compensation:** "When you first join, you will be rewarded 100
parts for each reinforcement you are down to the opposing team."
(<https://thelastofus.fandom.com/wiki/Factions_MP>)

`[LIKELY]` **Late-join day suppression:** "if more than 2 minutes has passed when a player
joins, the match will not count as an in-game day and will not reward any supplies
afterwards; however if the player is on a mission and successfully completes part of it,
the progress will count."
(<https://www.youtube.com/watch?v=NfLYMnZwB-k>) The wiki agrees on the mission-progress
carve-out and on "The player can quit this match without any consequences", but gives no
2-minute threshold — that number is single-source.

---

## 4. The 12-week campaign (Journey) structure

### 4.1 There is no named story campaign

`[CONFIRMED — negative finding]` Worth stating plainly because "named
story milestones" was an explicit research question: **Factions has no named, ordered story missions.** The Journey is a
fixed *calendar of event slots*; what fills each slot is a randomly-chosen flavour event,
and the player then picks a gameplay objective ("mission") to attempt against it. There is
no "Week 3: "The Dam"" style script.

DeltaCanuckian states the randomisation boundary precisely: "players will encounter random
events throughout the 12 weeks — **while the event itself is randomized, when they occur is
not**." (<https://www.youtube.com/watch?v=NfLYMnZwB-k>) PSNProfiles concurs: "The mission
alerts you get aren't randomized."
(<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>)

A GameFAQs veteran adds `[UNVERIFIED]` corroboration that the *type* (positive vs negative)
per slot is fixed while flavour varies, and one player asked whether events are randomised
per journey and was answered that the calendar is learnable and exploitable.
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>)

### 4.2 Event flavours (cosmetic wrappers)

`[CONFIRMED]` The random event types, with their in-game text:

| Event | Direction | Text |
| --- | --- | --- |
| Firefly/Hunter Attack | **negative** | "Scouts have picked up a large group of Fireflies/Hunters massing nearby for an attack. Improve the training of the group to help us survive the attack." |
| Dysentery Outbreak | positive | "Dysentery is spreading rapidly in the area. The Fireflies/Hunters have a supply of antibiotics. Improve the training of the groups so we can mount an attack and steal it." |
| Malaria Outbreak | positive | "An outbreak of malaria is spreading rapidly throughout the area. The Fireflies/Hunters have a supply of antibiotics. Improve the training of the group so we can mount an attack and steal it." |
| Rescue Allies | positive | "A group of allies trying to reach our camp were captured by Fireflies/Hunters. Improve the training of the group so we can mount a rescue operation." |
| Marauder Attack | positive | "Marauders have been raiding camps in the area and are heading our way. Improve the training of the group to repel the attack." |
| Friendly Survivors | positive | "Some friendly survivors have been found. If we can protect them from the Fireflies/Hunters, they'll join our clan." |

(<https://thelastofus.fandom.com/wiki/Factions_MP>) A community guide confirms these labels
are pure flavour: "The labels 'dysentery outbreak' or 'Firefly/Hunter/Marauder attack' are
just flavour. What you need to pay attention to are whether or not you can gain clan
members or lose them."
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69784044>)

### 4.3 The event calendar — exact, and it has a clean formula

`[CONFIRMED]` Identical calendar published by three independent sources (the wiki, the
PSNProfiles guide, and a GameFAQs community post), which is as good as this record gets:

| # | Week, Day | Absolute day | Tier 0 (fail) | Tier 1 | Tier 2 | Tier 3 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | W1 D6 | 6 | 0% | +5% | +7% | +10% |
| 2 | W2 D4 | 11 | 0% | +5% | +7% | +10% |
| 3 | W3 D2 | 16 | **-60%** | -40% | -20% | -10% |
| 4 | W3 D7 | 21 | 0% | +5% | +7% | +10% |
| 5 | W4 D5 | 26 | 0% | +5% | +7% | +10% |
| 6 | W5 D3 | 31 | **-60%** | -40% | -20% | -10% |
| 7 | W6 D1 | 36 | **-100%** | -60% | -40% | -20% |
| 8 | W6 D6 | 41 | 0% | +5% | +7% | +10% |
| 9 | W7 D4 | 46 | 0% | +5% | +7% | +10% |
| 10 | W8 D2 | 51 | **-100%** | -60% | -40% | -20% |
| 11 | W8 D7 | 56 | 0% | +5% | +7% | +10% |
| 12 | W9 D5 | 61 | 0% | +5% | +7% | +10% |
| 13 | W10 D3 | 66 | **-100%** | -60% | -40% | -20% |
| 14 | W11 D1 | 71 | 0% | +5% | +7% | +10% |
| 15 | W11 D6 | 76 | **-100%** | -60% | -40% | -20% |
| 16 | W12 D4 | 81 | **-100%** | -60% | -40% | -20% |

Sources: <https://thelastofus.fandom.com/wiki/Factions_MP> (percentages + calendar);
<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide> (calendar +
risk levels); <https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69784044>
(calendar, independently posted).

**Derived, and worth implementing as a formula rather than a table** `[CONFIRMED by
arithmetic]`: converting to absolute day numbers (day = 7×(week−1) + day), the 16 event
days are **6, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56, 61, 66, 71, 76, 81** — an exact
arithmetic sequence, **one event every 5 days starting on day 6**. i.e.
`event_days = {d : d ≡ 1 (mod 5), 6 ≤ d ≤ 81}`.
This matches DeltaCanuckian's description: "beginning with Week 1 day six players will be
prompted with a new event and to choose an accompanying mission **every five in-game
days**." (<https://www.youtube.com/watch?v=NfLYMnZwB-k>) Deriving the same sequence two
ways (from the published table, and from an independent verbal description) is strong
confirmation.

**Escalation structure** `[CONFIRMED]`: negative events begin at W3 D2 at the -60% severity
band; the catastrophic **-100%** band begins at **W6 D1** and there are exactly **five**
-100% events (days 36, 51, 66, 76, 81). The wiki explains the band switch as time-based:
the assault event "yields (100%/60%/40%/20%) or (60%/40%/20%/10%) loss of survivors …
**depending on how many weeks have passed by**."

`[CONFIRMED]` During an assault event "the player gains **10% more Parts**."
(<https://thelastofus.fandom.com/wiki/Factions_MP>)

### 4.4 Missions (the objectives you pick against an event)

`[CONFIRMED]` Each event window lasts **3 in-game days (3 matches)**. The player picks one
objective from a fixed list; each has tiered thresholds; reaching tier 1 is the minimum to
"pass".
(<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>,
<https://thelastofus.fandom.com/wiki/Factions_MP>)

`[CONFIRMED]` **Re-picking the same objective escalates it**: "If you choose that same
specific mission objective a second time in your 12 week run, then Tier 1 will NOT be the
minimum requirement, **Tier 2 will be the minimum requirement**, and Tier 3 and Tier 4 will
be the stretch goals, and so on." So the tier table is a per-objective ladder with a
per-journey pick counter as the offset.

`[UNVERIFIED — and sources conflict]` How many times an objective can be picked. The
GameFAQs resources thread says "you can only pick missions a total of **6 times** in one 12
week journey" (<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69784044>),
but the PSNProfiles tier table runs to **8 tiers**, implying up to 8 picks of one objective.
There are 16 event slots in a journey. These three numbers do not obviously reconcile; the
"6" claim is a forum post and the "8 tiers" is a published guide table. **Flagged as an
open conflict** — see §8.

`[CONFIRMED]` **Full mission objective ladder** (PSNProfiles, published guide; the wiki
carries the same objective list without numbers, so the *list* is double-sourced and the
*numbers* single-sourced-but-published):

| Objective | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Down Enemies | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Executions | 2 | 4 | 7 | 12 | 15 | 20 | 30 | 35 |
| Special Executions | 2 | 4 | 6 | 8 | 10 | 12 | 16 | 20 |
| Revives | 2 | 4 | 6 | 8 | 10 | 15 | 20 | 25 |
| Heal Teammate | 5 | 10 | 15 | 20 | 25 | 30 | 35 | 40 |
| Downs with Molotovs | 2 | 4 | 6 | 8 | 10 | 12 | 16 | 20 |
| Downs with Bombs | 2 | 4 | 6 | 8 | 10 | 12 | 16 | 20 |
| Give Crafting Items | 2 | 4 | 6 | 8 | 10 | 12 | 16 | 20 |
| Mark Enemies | 7 | 14 | 21 | 28 | 35 | 42 | 48 | 56 |
| Downs with Melee | 3 | 6 | 9 | 12 | 15 | 18 | 25 | 30 |
| Shiv Executions | 1 | 2 | 3 | 5 | 7 | 9 | 12 | 15 |
| Downs with 9mm | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Downs with Revolver | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Downs with Shorty | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Downs with Hunting Rifle | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Downs with Semi-Auto | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Downs with Burst Rifle | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Downs with Bow | 3 | 6 | 9 | 15 | 20 | 25 | 35 | 45 |
| Downs with Long-Range | 2 | 4 | 6 | 8 | 10 | 16 | 20 | 24 |
| Downs with Headshots | 2 | 4 | 6 | 8 | 10 | 12 | 16 | 20 |

(<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>. The guide
also notes the list order is the in-game menu order, which is useful if the server ever
needs to send an ordered objective list.)

`[CONFIRMED]` The wiki adds a display note: "The mission list screen now displays an exact
amount of survivors for positive missions. **The math used has not changed**, and missions
rewards are still calculated on the percentage of survivors the player currently has on the
end of the last day." — i.e. the percentage is evaluated against population at event
resolution time, not at event start. That is a real implementation detail.

### 4.5 Win / lose conditions

`[CONFIRMED]` **Lose:** population reaches **0**. Cause can be starvation attrition, a
failed -100% event, or quitting with zero healthy survivors. On loss the journey resets to
week 1 and the player starts a fresh clan. "If you lose all of the members of your clan at
some point, you will have to restart your entire 12 week run all over again."
(<https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>)

`[CONFIRMED]` **Survival with 1 survivor is viable** — there is no minimum-viable-clan
rule: "you can still succeed even with one person in your population" (PSNProfiles);
"You can go all 12 weeks as long as one person is alive."
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>)

`[CONFIRMED]` **Win:** complete Week 12, Day 7. This awards the "Firefly" or "Hunter"
trophy (separate trophies, one per faction, so a full completionist run is two journeys =
168 matches). "The trophy pops as you finish Week 12, Day 7."
(<https://www.playstationtrophies.org/game/the-last-of-us-remastered/trophy/89717-Hunter.html>)

`[CONFIRMED]` **What happens at week 12:** the clan's rank symbol advances (§5.1),
population-gated unlocks that specify "after 12 weeks" resolve (§5.3), and the player
starts a new journey. Progress is *not* wiped by finishing: "at the end of 12 weeks,
choosing the other faction does not reset the player's progress"
(<https://thelastofus.fandom.com/wiki/Factions_MP>), and unlocked head items "will remain in
the player's inventory even if their clan is reset"
(<https://thelastofus.fandom.com/wiki/Head_item>).

`[LIKELY]` There is a **final population deduction at the end of week 12** — the last event
is the -100%-band assault on day 81, and a veteran describes the Skull Mask requirement as
"85 final pop (**107 before final deduction**)", i.e. the W12 D4 event's loss is applied
before the final population is scored for unlocks.
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>) Note
107 × 0.8 = 85.6, consistent with a -20% (tier-3 completion) outcome on that last -100%-band
event. That arithmetic cross-check is reassuring but it is still one player's report.

---

## 5. Ranking / progression and unlocks

### 5.1 Rank is journeys completed, and it is COSMETIC

`[CONFIRMED]` This is the single most important finding for the revival project's "players
can't change gear because rank-up isn't implemented" problem, and the answer is that
**rank is not what gates gear**.

- The rank **symbol** starts looking like `//` and "will change **every successful survival
  of the player's clan for twelve in-game weeks**." There are **ten** rank symbols.
- The **number** shown next to a player's PSN ID and rank symbol "is how many **weeks**
  they have survived in total regardless of whether their clans have survived or not. Days
  carry over from campaign to campaign… The maximum is **999**."

(<https://thelastofus.fandom.com/wiki/Factions_MP>)

**Corroborated directly by a Naughty Dog community manager** (EvangM), quoted on
gaming.stackexchange (<https://gaming.stackexchange.com/questions/121726/what-is-the-number-next-to-your-name-in-multiplayer>):

> "To answer your questions S4, **there is no such thing as 'levels' in TLOU MP.** One of
> the things we wanted to move away from was the traditional progression iconography and
> descriptions that people use to make snap judgements on whether or not a teammate/opponent
> is 'good' or 'bad'. … Instead, we have a small number next to your name. It displays
> approximately **the number of weeks you have completed of MP for your entire career**, not
> just on one clan loop. And again, **this is no indicator of skill at all**, merely a
> 'timestamp' of sorts."

Also corroborated by Haywire Magazine: lobbies with "the highest-possible '999' ranks sitting
proudly beside their name tags – **an indication of the number of weeks survived**."
(<https://haywiremag.com/features/how-the-last-of-us-factions-still-endures-and-survives/>)

**Rank index = number of successfully completed 12-week journeys** `[CONFIRMED]`, capped at
10 icons (i.e. 9 completions to reach the last one). Corroborating player reports:
- "Your symbol changes each time you clear a 12 week campaign until you reach the 10th
  symbol (9 clears)." (<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67196264>)
- "the symbols represent the amount of 12 weeks you successfully completed… **you don't get
  the dot or upgrade if you lose all of your population**" (same thread)
- "you just need to make it through the 12 weeks to complete it with ANY population. You
  could have only 1 person left and it would still count."
  (<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67763979>)

Key asymmetry for implementation: **a wipe resets the journey but never regresses the rank.**

`[UNVERIFIED dissent, noted for completeness]` One poster in the 67763979 thread claims "it's
4 successful run-throughs… that warrants a change of symbol", i.e. the dots are sub-steps and
only the base glyph counts. That contradicts the "10th symbol (9 clears)" statement and the
rank-icon album's own 1–10 labelling. **Going with one icon per journey**, dissent flagged.

**The 10 rank icons** `[LIKELY]` — no names are given anywhere; the community refers to them
purely descriptively, so I record them as unnamed rather than inventing labels. Visual
progression, from the wiki's `Multi_rankicons.jpg` and a 2013 Imgur album whose ten images
are individually titled "Rank 1"…"Rank 10" (<https://imgur.com/a/hS88H>): rank 1 is a bare
`//`; ranks 2–4 add 1/2/3 dots; ranks 5–7 switch the glyph to an `X` with 1/2/4 dots; rank 8
is an asterisk form with 2 dots; ranks 9–10 use a 45°-rotated hatch with 1/2 dots.
`[UNVERIFIED]` The Imgur poster cautions that his ranks 9 and 10 images may be mirrored
relative to in-game.

`[CONFIRMED]` **Rank confers no gameplay benefit.** Four independent lines of evidence:
1. The ND developer statement above ("no such thing as 'levels'", "no indicator of skill").
2. Eurogamer draws the line explicitly: "**The rewards for the clan meta-game are entirely
   cosmetic, but the unlocks through the rest of the multiplayer are cumulative and
   practical.**"
   (<https://www.eurogamer.net/stealth-scavenging-crafting-and-clans-the-last-of-us-multiplayer-detailed>)
3. `[STRINGS]` The game's own tutorial text splits the two currencies and never mentions
   rank: `Collect supplies from defeated opponents to acquire gameplay unlocks` /
   `Unlock character customization items by increasing your clan size` /
   `Unlock more LOADOUT POINTS by earning SUPPLIES.`
4. `[STRINGS]` The unlock-condition templates are exhaustively:
   `SURVIVE [A] DAYS TO UNLOCK`, `SURVIVE [A] WEEKS TO UNLOCK`,
   `SURVIVE UNTIL WEEK [A], DAY [B]`, `[A] POPULATION TO UNLOCK`,
   `[A] POPULATION AFTER 12 WEEKS`, `[A] / [B] TO UNLOCK`, `New Loadout Points`.
   **There is no "reach rank N to unlock" template.**

> ⚠️ **False-positive warning.** The same string table contains
> `Next Rank: [TEXT] XP`, `Total XP: [TEXT]`, `RANK UP!`,
> `Must reach rank [A] (current rank is [B])`,
> `New PISTOLS and LONG GUNS are unlocked by RANK or by completing TREASURE SETS`, and
> `BOOSTERS … Each BOOSTER is unlocked by reaching a certain RANK`. **These are Uncharted 3
> leftovers, not Factions features.** I verified by reading the surrounding lines: they sit
> among `TREASURE SETS`, `Money`, `$40,000 earnings_penalty`, `skill_rating`, and
> "Uncharted: Drake's Fortune™ Multiplayer Pack" store prompts. ND explicitly removed XP
> from TLOU. Anyone grepping this table to infer server fields **must** filter this block —
> it would otherwise lead straight to implementing an XP/rank system the game does not have.
> By the same token, **`skill_rating` is not evidence of a TLOU matchmaking rating**; it
> lives in that Uncharted block. Whether Factions has a hidden skill rating is `[UNKNOWN]`.

`[LOCAL-XREF]` This repo has already observed a rank field on the wire — see
`research/notes/2026-08-17-member-data-blob-rank-and-0x142-hostrank.md` and the `HostRank`
reply work in `server/`. The public record above says that value should be interpretable as
**cumulative weeks survived, 0–999**, with the displayed symbol derived from completed
journeys. Worth validating against captured values.

### 5.2 What ACTUALLY gates gear: cumulative "supplies acquired"

`[CONFIRMED]` Weapons and loadout points unlock against a **lifetime cumulative supplies**
counter, not rank and not current population. The wiki's weapon entries state thresholds
directly ("Unlocked at 375 supplies"), and its "Table of progression" maps loadout points
to "Supplies Acquired". (<https://thelastofus.fandom.com/wiki/Factions_MP>)

`[STRINGS]` **The game says so in its own tutorial text**, which is the strongest possible
confirmation and settles the question outright:

```
CLANS:   Collect supplies from defeated opponents to acquire gameplay unlocks
         Unlock character customization items by increasing your clan size

You have a limited number of LOADOUT POINTS to spend. Spend these points on SURVIVAL
SKILLS, FIREARMS, and PURCHASABLES.  Unlock more LOADOUT POINTS by earning SUPPLIES.
```

Read that as the whole progression design in three lines: **supplies → gameplay unlocks
(loadout points, weapons, skills); clan size → cosmetics; rank → nothing.**

**Loadout point unlock schedule** `[CONFIRMED]`:

| Loadout points | Cumulative supplies acquired |
| --- | --- |
| 8 (PS3 start) | 0 — starting value |
| 9 | 75 |
| 10 | 525 |
| 11 | 1,650 |
| 12 | 3,825 |
| 13 (max) | 7,500 |

**Independent arithmetic corroboration of the 7,500 figure** `[CONFIRMED]`: a veteran wrote
"With only 83 matches per journey, you would need to average around **4500 points** per
match to get your 13th LP unlocked at the END of the first journey."
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>)
Check: 7,500 supplies × 50 parts/supply = 375,000 parts; 375,000 / 83 ≈ 4,518 parts/match.
That independently reproduces "around 4500" from a completely different direction, which
strongly validates both the 7,500 threshold and the 50:1 conversion.

> **PS3 vs Remastered — implement the PS3 numbers.** `[CONFIRMED]` Naughty Dog on the
> Remastered changes: "If you're a **new player you'll start with 9 loadout points instead
> of 8**. You'll reach the max of 13 loadout points sooner as a result."
> (<https://www.naughtydog.com/blog/the_last_of_us_remastered_multiplayer_factions>)
> So **PS3 starts at 8 LP**; the wiki's "Every class has 8 loadout points to start out
> with… up to a max of 13" is the PS3 behaviour and is what this project needs.
> `[UNKNOWN]` whether Remastered also shifted the 75/525/1650/3825/7500 thresholds or
> merely skipped the first step.

**Weapon unlock schedule** `[CONFIRMED]` — the numbers below in braces are the wiki's
"{N supplies to unlock}" annotations:

| Weapon | Slot | LP cost | Unlock |
| --- | --- | --- | --- |
| 9mm Pistol | small firearm | 0 | unlocked at start |
| Revolver | small firearm | 0 | unlocked at start |
| Semi-Auto Rifle | large firearm | 2 | unlocked at start |
| Full-Auto Rifle | large firearm | 2 | unlocked at start |
| Hunting Rifle | large firearm | 2 | unlocked at start |
| **El Diablo** | purchasable | 3 | **150 supplies** |
| **Shorty** | small firearm | 1 | **375 supplies** |
| **Assault Rifle** | purchasable | 3 | **900 supplies** |
| **Burst Rifle** | large firearm | 2 | **1,375 supplies** |
| **Machete** | purchasable | 2 | **2,625 supplies** |
| **Bow** | large firearm | 3 | **3,400 supplies** |
| **Flamethrower** | purchasable | 2 | **4,750 supplies** |
| **Military Sniper** | purchasable | 3 | **6,900 supplies** |
| Shotgun | purchasable | 4 | *(no supplies figure given by the wiki — `[UNKNOWN]`)* |
| Enforcer | small firearm | 1 | PS Store purchase (DLC) |
| Double Barrel | purchasable | 1 | PS Store purchase (DLC) |
| Specter | purchasable | 3 | PS Store purchase (DLC) |
| Launcher | purchasable | 3 | PS Store purchase (DLC) |
| Silencer attachment | modifier | +2 | not available on Revolver or Bow |

(<https://thelastofus.fandom.com/wiki/Factions_MP>)

Note the tidy ordering: **150, 375, 900, 1375, 2625, 3400, 4750, 6900** interleave with the
loadout-point steps **75, 525, 1650, 3825, 7500**, giving a steady unlock drip across
roughly one and a half journeys. Nothing unlocks above 7,500 supplies except cosmetics.

### 5.3 Cosmetic unlocks — three different gate types

`[CONFIRMED]` The head-item table is the best-documented unlock list in the game and it
proves the metagame exposes **three independent progression counters**, all of which a
server must persist:

1. **Current clan population** ("25 population", "85 population")
2. **Journey progress reached** ("Survive until week 4, day 3")
3. **Cumulative supplies acquired** ("25,000 supplies", "150,000 supplies")

plus a fourth, "**N population after 12 weeks**", which is a *conjunction* of (1) and a
completed journey.

Totals: 146 head items — 75 hats (40 unlockable / 35 PS Store), 38 masks (10 / 28), 33
helmets (8 / 25). 58 unlockable in the base game; 87 purchasable. Unlocked head items
"remain in the player's inventory even if their clan is reset."
(<https://thelastofus.fandom.com/wiki/Head_item>)

**Full unlockable head-item schedule** `[CONFIRMED]` (PS Store items omitted):

*Population-gated:*
| Population | Items |
| --- | --- |
| 10 | Baseball cap, Beanie, Crochet beanie |
| 25 | Fedora, Conductor cap, Biker helmet |
| 30 | Cadet cap, Straw cowboy hat, Surgeon mask |
| 40 | Pawkul, Norwegian hat, Spiked helmet |
| 55 | Bowler hat, Ballistic mask |
| 60 | Garrison cap, Civil War hat |
| 70 | Boonie hat, Flame head wrap |
| 85 | Rancher, Hockey mask |
| 90 | Aussie cattleman, Combat helmet |
| 100 | Poet fedora, SWAT helmet |
| 115 | Beret |
| 120 | Black rancher hat |

*Journey-progress-gated:*
| Reach | Items |
| --- | --- |
| W1 D3 | Jeep cap, Greek fisherman, Bandana |
| W2 D7 | Winter hat, Legionnaire, Flat cap |
| W3 D7 | Deerstalker, Head wrap, Goggles |
| W4 D3 | Sou'wester, Military helmet |
| W5 D7 | Hunting hat, Bucket hat |
| W6 D7 | Pith hat, Military hat |
| W7 D3 | Skipper, Cavalry hat |
| W8 D7 | Porkpie, Pollution mask |
| W9 D7 | Campaign cover, Battle helmet |
| W10 D3 | Fur aviator, Headphones |
| W11 D7 | Combat mask |
| W12 D7 | Naval officer hat |

*Cumulative-supplies-gated:*
| Supplies | Item |
| --- | --- |
| 25,000 | Camo hat |
| 50,000 | Día de los Muertos mask |
| 75,000 | Dragonfly helmet |
| 100,000 | Ski mask |
| 150,000 | Skimmer hat |

*Conjunction (population **after** completing 12 weeks):*
| Requirement | Item |
| --- | --- |
| 70 population after 12 weeks | Flight helmet |
| 85 population after 12 weeks | **Skull mask** |

`[UNVERIFIED corroboration]` A veteran independently states: "The last of the pop based
unlockables are the **Skull Mask (85 final pop (107 before final deduction))**, and the
**Black Rancher (120 or more pop)**."
(<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>) This
matches the wiki table on both items — two independent sources agreeing, so treat the Skull
Mask (85 post-journey) and Black Rancher (120) figures as `[CONFIRMED]`.

`[CONFIRMED]` **Emblems** follow the identical gating pattern (192 emblem images; examples:
15 unlocked by default, then bands at "20 population", "Survive until week 1, day 7", "35
population", "Survive until week 3, day 3", "50 population", "Survive until week 4, day 7",
…). Full list at <https://thelastofus.fandom.com/wiki/Emblem>. Emblems also support 64
colours, 4 layers, and 3 placement locations (torso / helmet / backpack) — all of which is
per-player persisted state a server must store.

**Gestures** `[CONFIRMED]` — 10 unlockable, activated with R3 in combat. Retrieved via the
MediaWiki API (see §9 tip). Same three gate types, confirming the pattern holds across every
customisation category:

| Gesture | Unlock |
| --- | --- |
| Fist Pump | 15 population |
| Knuckles | Survive until week 2, day 3 |
| Chest Pound | 45 population |
| Blow Smoke | Survive until week 5, day 3 |
| Salute | Survive until week 8, day 3 |
| Come Here | Survive until week 11, day 4 |
| Back Off | 75 population |
| Neck Crack | Survive until week 12, day 3 |
| Bow | 105 population |
| **Close Call** | **40 population after 12 weeks** |

A further 12 are PS Store purchases across three "Gesture Bundle" packs (The Gif, Oh Snap!,
Victory / Dust Myself Off, Evil Laugh, Game Over, Intimidation / You're Done, Combat
Formation, Stretch, I'm Watching You).
(<https://thelastofus.fandom.com/wiki/Gesture>)

### 5.4 One-time boosters

`[CONFIRMED]` Earned "as the clan population increases and as missions are completed";
one may be equipped per match, consumed on use.
(<https://thelastofus.fandom.com/wiki/Factions_MP>, corroborated by
<https://www.youtube.com/watch?v=NfLYMnZwB-k>)

| Booster | Effect |
| --- | --- |
| Cheaper Ammo | ammo costs −25% |
| Cheaper Armor | armour costs −25% |
| Cheaper Purchased Weapons | purchasable weapon cost −25% |
| Starting Ammo Multiplier | +25% starting large & small firearm ammo |
| Small Firearm Upgrade Level 1 | Revolver, 9mm, Enforcer, Shorty start at upgrade level 1 |
| Large Firearm Upgrade Level 1 | Hunting Rifle, Burst Rifle, Full-Auto, Semi-Auto, Bow start at upgrade level 1 |
| Increased Parts Earnings | +10% parts (excludes parts from healing teammates and gifting) |

`[STRINGS]` The in-game description confirms the two grant sources: "ONE-USE BOOSTERS can
only be used for one match. **Earn them by growing your CLAN population and completing
MISSIONS.**" Also present: `Mission performance also determines how many One-Use Boosters
you earn.`, `NEXT ONE-USE BOOSTER`, `ONE-USE BOOSTER AWARDED:`, `ONE-USE BOOSTER REWARDS:`,
`CHOOSE ONE-USE BOOSTER`, and `Event Reward (Tier [A])`. The `NEXT ONE-USE BOOSTER` string
implies the UI shows progress toward the next grant, so the threshold is a value the server
must expose, not just an event.

`[UNKNOWN]` The exact population/mission thresholds that grant each booster, and how many
of each can be stockpiled. `[UNVERIFIED]` One player's estimate: "Usually around **4-5
people** gives you a one use booster."
(<https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67242712>) — i.e. roughly one
booster per 4–5 population gained. Single source, but it is the only quantitative claim
found.

`[STRINGS]` Facebook linking grants **3 One-Use Boosters** as a one-off
(`Linking to Facebook also gives you 3 One-Use Boosters.`) — see §1.6.

`[STRINGS]` The table also contains three entries reading `Test booster for progression.
Nothing to see here...` — debug/placeholder boosters. If the client's booster index space
is sparse (see the `< 64` assertion below), these may account for some of the gap.

`[LOCAL-XREF]` The EBOOT string dump in `research/strings/strings_ascii.txt` contains
`game/net/net-booster-manager.cpp`, the assertion `boosterIndex >= 0 && boosterIndex < 64`,
`storeMenuIconIndex >= 0 && storeMenuIconIndex < kMaxNetUpgradeBoosters`, `NetEventSwapBooster`,
and the state `NET_SM_SELECT_CLAN_BOOSTER_SCREEN`. So the client supports a **booster index
space of up to 64**, far more than the 7 documented boosters — either the space is sparse,
or boosters are stored per-level/per-variant. Worth resolving before designing the booster
inventory wire format. (Also present: `clan/tutorial-supplies-1`, `clan/tutorial-supplies-2`,
`clan/intro-world`, `clan/hunter`, `clan/firefly`.)

---

## 6. Loadout system

### 6.1 Loadout points

`[CONFIRMED]` Each class/loadout has a point budget. **PS3: starts at 8, maximum 13.**
"Every class has 8 loadout points to start out with, and each weapon and survival skill
uses up these points (with the exception of the 9mm Pistol and Revolver, which are free to
equip). As the player levels up, he or she will gain more loadout points, up to a max of 13
loadout points." (<https://thelastofus.fandom.com/wiki/Factions_MP>)

Despite the wiki's phrase "as the player levels up", the same page's progression table
makes clear the gate is **supplies acquired**, not any rank — see §5.2. Remastered starts
at 9 (§5.2 box).

`[CONFIRMED]` The player has **6 customisable loadouts** plus **8 pre-made loadouts**. The
pre-made ones "often contain weapons and survival skills that are not available to players
with little Supplies or without the DLC" — i.e. **pre-made loadouts bypass the unlock
gates**. (<https://thelastofus.fandom.com/wiki/Factions_MP>)

> **Directly relevant to this project's gear-change problem.** If rank/unlock progression
> is not yet implemented server-side, the pre-made loadouts are the intended escape hatch —
> they are designed to be usable regardless of supplies. A veteran even recommends them:
> "until you get your 13th LP, you are *almost* always better off with one of the presets."
> (<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>)
> A server that reports a large cumulative-supplies value (≥7,500 unlocks everything
> non-DLC and non-cosmetic; ≥150,000 unlocks every supplies-gated cosmetic) would
> unlock the full non-DLC loadout space without needing the metagame simulated at all.
> `[LIKELY]` — depends on whether unlock checks are client-side against a server-supplied
> counter, which is `[UNKNOWN]` and should be verified against the client.

### 6.2 Costs

Weapon LP costs and unlock thresholds: see the table in §5.2.

Survival skills: see §6.3.

`[CONFIRMED]` In-match store prices (parts), for completeness — these are client-side match
economy, not metagame state, so the server likely does not need them, but they anchor the
parts↔supplies scale:
- Armour: 450 → 500 → 575 (price rises per purchase); vest absorbs 50 HP, helmet 100 HP.
- Weapon ammo/upgrades, per weapon, e.g. 9mm ammo 150 / upgrade 1 250 / upgrade 2 500;
  Hunting Rifle ammo 240 / 300 / 600; Bow ammo 195 / 400 / 800.
- Purchasable weapon costs: El Diablo 270, Assault Rifle 350, Shotgun 400, Military Sniper
  440, Flamethrower 240, Machete 400, Double Barrel 240, Specter 350, Launcher 375.

(<https://thelastofus.fandom.com/wiki/Factions_MP>)

### 6.3 Survival skills

Survival Skills are Factions' perk system. They spend loadout points from the same budget as
weapons. `[CONFIRMED]` **At most 4 skills may be equipped at once.**
(<https://thelastofus.fandom.com/wiki/Survival_skills>)

`[STRINGS]` The tutorial text puts skills in the same unlock bucket as weapons — "Spend
these points on **SURVIVAL SKILLS**, FIREARMS, and PURCHASABLES" + "Collect supplies … to
acquire **gameplay unlocks**" — so the base skills are **supplies-gated**, like weapons.

#### Loadout-point costs — CONFIRMED by two fully independent sources

`[CONFIRMED]` The table below is corroborated by (a) the wiki's Survival skills page and
(b) an independently-authored community loadout calculator whose data file I fetched and
parsed directly. **All 26 skills' per-tier LP costs match exactly between the two.** That is
about as solid as a non-datamined figure gets.

- <https://thelastofus.fandom.com/wiki/Survival_skills>
- <https://freddybushboy.github.io/tlou-loadout/> (data at `js/services/skillService.js`)

**Base skills — included with the game, unlocked with supplies:**

| Skill | L1 | L2 | L3 | Effect summary |
| --- | --- | --- | --- | --- |
| Pistol Auto-Zoom | 1 | 2 | — | Zoom while aiming a pistol; L2 zooms further |
| Explosion Expert | 1 | 3 | — | Explosive radius +20%/+40% (Molotov +10%/+20%) |
| Reviver | 1 | 3 | 4 | Revive 30/45/55% faster, +20/25/30% health; L2/L3 give +25%/+50% parts from revives |
| Brawler | 2 | 3 | — | Craft modded melee in half time, +10 HP per melee hit; L2 adds an extra hit |
| Covert Training | 2 | 4 | 5 | L1 spawn with shiv; L2 invisible to listen mode when crouch-walking; L3 cannot be marked |
| Sharp Ears | 1 | 2 | 3 | Listen-mode regen +15/30/35%, duration +20/20/30%; L3 move quickly in listen mode |
| Strategist | 1 | 4 | 5 | L1 know when marked; L2 nearby enemies on radar; L3 **spawn on an ally** |
| Hawk-eyed | 2 | 3 | 4 | Marks last +3s; L2 marked enemies glow; L3 splash-marks nearby enemies |
| Crafter | 2 | 4 | 6 | Craft 75% faster; L2 giftbox per 3 items; L3 giftbox per 2 items |
| First-Aid Training | 2 | 4 | 6 | Health kits 75% faster; L2/L3 heal teammates (see conflict below) |
| Sharpshooter | 2 | 4 | 5 | Scope sway −25/37/50%, wobble −20/35/65%; L2/L3 +15/+25 HP per headshot |
| Marathon Runner | 1 | 3 | — | Sprint duration and regen +15%/+30% |
| Collector | 3 | 5 | — | Parts earned +10%/+20% (excludes parts from healing and gifting) |

**DLC skills — PS Store purchase only, NOT supplies-unlockable.** Important for a revival
server: no amount of cumulative supplies grants these, so a player without the DLC
entitlement cannot equip them outside the pre-made loadouts.

| Category | Skill | L1 | L2 | L3 |
| --- | --- | --- | --- | --- |
| Professional | Executioner | 1 | 3 | 4 |
| Professional | Damage Marker | 2 | 4 | — |
| Professional | Gunslinger | 2 | 4 | — |
| Professional | Bomb Expert | 2 | 3 | 5 |
| Situational | Scavenger | 2 | 4 | 5 |
| Situational | Awareness | 1 | 3 | — |
| Situational | Fortitude | 1 | 3 | — |
| Situational | Agility | 2 | 4 | — |
| Risk Management | Lone Wolf | 2 | 3 | — |
| Risk Management | Second Chance | 1 | 2 | — |
| Risk Management | Jack of All Trades | 5 | 10 | — |
| Risk Management | Lucky Break | 2 | 3 | 4 |
| Risk Management | Lethal Efficiency | 2 | 3 | — |

Two of these are bundle skills that are cheaper than their contents, which matters if you
ever validate loadout legality server-side: **Jack of All Trades L1 costs 5 LP but grants
8 LP worth** (Brawler 1, Covert Training 1, Sharp Ears 1, Strategist 1, Crafter 1); **L2
costs 10 LP and grants 16 LP worth**. **Lone Wolf** similarly grants Agility 2 +
Sharpshooter 2 (+ Sharp Ears 3 at L2) for 2–3 LP, conditional on being away from teammates.

#### Per-skill supplies unlock thresholds

`[LIKELY — single source, but cross-checks well]` Neither the wiki nor the loadout
calculator carries these, but a **GameFAQs text walkthrough does**: Krystal109,
*The Last of Us — Guide and Walkthrough* v1.5 (updated 2017-08-02), "Gearing Up → Survival
Skills", `Unlock` column.
(<https://gamefaqs.gamespot.com/ps3/652686-the-last-of-us/faqs/67221>, page 4; mirrored under
Remastered at `.../ps4/783739-the-last-of-us-remastered/faqs/67221`)

**Every number here appears in only this one source**, so treat as medium confidence — but
two independent checks raise it above a bare forum claim:
1. The **same table's weapon column reproduces the known-good weapon ladder exactly**
   (Shorty 375, Burst Rifle 1375, Bow 3400, …, all matching §5.2 / Fandom / IGN), so the
   guide's `Unlock` column is transcribed accurately for the rows we *can* verify.
2. The **LP costs in this table match the LP costs I confirmed two other ways** in §6.3
   (Crafter 3 = 6, Strategist 1 = 1, Covert 3 = 5, …), i.e. it is the same post-patch-1.06
   revision, so the thresholds correspond to that revision's LP layout — internally
   consistent.

`-` = unlocked at start.

| Skill | Tier | LP | Supplies to unlock |
| --- | --- | --- | --- |
| Pistol Auto-Zoom | 1 / 2 | 1 / 2 | – / **150** |
| Explosion Expert | 1 / 2 | 1 / 3 | **25** / **2275** |
| Reviver | 1 / 2 / 3 | 1 / 3 / 4 | – / **1375** / **2625** |
| Brawler | 1 / 2 | 2 / 3 | **150** / **1950** |
| Covert Training | 1 / 2 / 3 | 2 / 4 / 5 | – / **700** / **6325** |
| Sharp Ears | 1 / 2 / 3 | 1 / 2 / 3 | **250** / _blank in source_ / **3000** |
| Strategist | 1 / 2 / 3 | 1 / 4 / 5 | – / **2275** / **5775** |
| Hawk-eyed | 1 / 2 / 3 | 2 / 3 / 4 | **25** / **375** / **4275** |
| Crafter | 1 / 2 / 3 | 2 / 4 / 6 | – / **700** / **5250** |
| First-Aid Training | 1 / 2 / 3 | 2 / 4 / 6 | **25** / **1125** / **4275** |
| Sharpshooter | 1 / 2 / 3 | 2 / 4 / 5 | – / **900** / **4750** |
| Marathon Runner | 1 / 2 | 1 / 3 | – / **250** |
| Collector | 1 / 2 | 3 / 5 | **375** / **4275** |

`[UNKNOWN]` **Sharp Ears L2** — cell blank in the guide.
`[UNKNOWN]` **DLC skills** — the guide marks their tier 1 as `DLC` (store purchase) and
leaves upper tiers blank, so whether DLC skill L2/L3 carry an *additional* supplies gate on
top of the entitlement is not recorded.

`[CONFIRMED]` These thresholds fall on the **same discrete milestone ladder** as the weapons
and loadout points — a shared set of unlock milestones, with several items unlocking at each
(batch unlocks). Observed milestones: 25, 150, 250, 375, 700, 900, 1125, 1375, 1950, 2275,
2625, 3000, 3400, 4275, 4750, 5250, 5775, 6325, 6900, 7500. No value was interpolated;
this is just the union of the published weapon (§5.2), LP (§5.2), and skill thresholds.

Practical mitigation still holds: since all gear keys off one scalar
(`supplies_acquired_lifetime`), a server reporting ≥ 7,500 unlocks every base skill, weapon,
and loadout point at once — the per-skill schedule above only matters if you want the
unlock *drip* to match the original.

#### Conflicts and version notes

- `[CONFLICT]` **First-Aid Training heal rate.** Three sources disagree:
  the Survival skills page says **L2 = 10 HP / 2s, L3 = 20 HP / 2s**; the Factions MP page's
  parts table says heal *parts* are 20/2s at L2 and 40/2s at L3; and the pre-release string
  table says **L2 = "20 health every 2 seconds"**. The HP and parts figures are different
  quantities and are being conflated by some sources; additionally the pre-release build
  looks to have been nerfed before release. Resolve empirically before implementing.
- `[UNVERIFIED]` One forum poster believed First Aid Training was a PS Store purchase
  (<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>).
  **The wiki's categorisation refutes this** — First-Aid Training is listed under "Basic
  Skills … included with the game and do not need to be purchased from the PlayStation
  Store." Treat the forum claim as mistaken.
- `[PS3 vs later]` The calculator's weapon list includes **Burst Pistol, Tactical Shotgun,
  Frontier Rifle, Variable Rifle, Crossbow** and scoped/silenced rifle variants. These are
  **later DLC / Remastered-era additions** and are not part of the PS3 launch weapon set in
  §5.2. Do not treat the calculator's weapon roster as the PS3 baseline.
- `[MINOR]` The calculator encodes silenced weapon variants as a second cost entry. Silencer
  appears to cost **+2 LP** on most weapons (Shorty 1→3, rifles 2→4) but only **+1 LP** on
  the 9mm (0→1), which differs from the wiki's flat "+2 LP" claim. Low stakes, but noted.

> ⚠️ **Contamination warning — and a correction.** Do not harvest skill names indiscriminately
> from the leaked string table. Entries such as **Warp Speed**, **Grave Robber**,
> **Headhunter**, **Juggernaut**, **Steady Aim**, **Unshakable**, and **Score Boost** sit
> beside `Next Rank: [TEXT] XP`, `You won a diamond shard!`, and `PLAY HEAD TO HEAD` — these
> are **Uncharted 3 boosters**, not Factions skills. **However, `Marathon Runner` appears in
> both games and IS a genuine Factions skill** (confirmed in the wiki navbox and the
> calculator, 1/3 LP). Name-matching alone is not sufficient to classify these; check against
> the confirmed roster above.

### 6.4 Population vs. rank gating — the summary answer

`[CONFIRMED]` To state the project-critical conclusion plainly:

| Thing unlocked | Gated by |
| --- | --- |
| Loadout points (9→13) | **cumulative supplies acquired** |
| Weapons (Shorty, Burst Rifle, Bow, El Diablo, Assault Rifle, Machete, Flamethrower, Military Sniper) | **cumulative supplies acquired** |
| Survival skills (13 base skills) | **cumulative supplies acquired** — per-skill thresholds `[UNKNOWN]` (§6.3) |
| Survival skills (13 DLC skills) | **real money (PS Store)** — not supplies-unlockable at any value |
| Head items, emblems | **population** and/or **journey day reached** and/or **cumulative supplies** |
| One-time boosters | **population** and **mission completions** |
| Rank symbol (10 tiers) + weeks counter (max 999) | **journeys completed** / **weeks survived** — cosmetic, gates nothing |
| Enforcer, Double Barrel, Specter, Launcher, most head items | **real money (PS Store)** |

**Nothing gameplay-affecting is gated by rank.** A revival server that wants players to
have free gear choice needs to supply a high **cumulative-supplies-acquired** value; it does
not need rank-up implemented at all.

---

## 7. Notes for server implementation

### 7.1 Minimum persisted per-player metagame state

Derived from the above; every field here is something a source shows the game reacting to:

```
faction                     Hunters | Fireflies                (cosmetic)
journey_day                 1..84                              (drives event calendar)
journeys_completed          int                                (drives rank symbol, 10 tiers)
weeks_survived_total        0..999                             (the number beside the PSN ID)
population                  int                                (gates cosmetics, scales requirement)
survivors_healthy           int  }
survivors_hungry            int  }  must sum to population
survivors_sick              int  }
supplies_acquired_lifetime  int                                (gates ALL gear + some cosmetics)
active_event                {type, day_started, mission, tier_progress, pick_count_per_mission}
boosters_owned              multiset over booster ids (index space up to 64, per EBOOT)
unlocked_items              set (head items, emblems, gestures) — survives clan reset
loadout_slots               6 custom + 8 premade
emblem_config               4 layers x {image, colour(64), rotation, opacity, scale} + placement
survivor_roster             [(name, state)] where state ∈ {healthy, starving, sick}
max_clan_size_reached       high-water mark (stat/leaderboard, not a cap — see §1.3)
```

`[STRINGS]` Clan-UI strings a stub will need to satisfy, verbatim:
`WEEK [A]: DAY [B]`, `POPULATION: [A] SURVIVORS`, `HEALTHY: [A]`, `HUNGRY: [A]`, `SICK: [A]`,
`Supplies Needed: [A]`, `Supplies Gathered by Clan: [A]`, `Surplus/Deficit: [A]`,
`RISK: [A]% OF POPULATION`, `Event Reward (Tier [A])`, `POPULATION +[A]`,
`MAX CLAN SIZE REACHED [A]`, `Your maximum clan size was [A]`,
`The world's best clan size is [A]`, `Clan Roster`, `CLAN EVENTS`, `DAYS SURVIVED`,
`12 WEEKS SURVIVED`, `Clan size was [A] after finishing the story`,
`Members Dead: [A], Members Got Sick [B]`, `[A]/[B] Loadout Points`,
`1 Loadout Point Remaining`, `New Loadout Points`.

`[STRINGS]` **A `CLAN HARDCORE` mode existed in the May-31 build and was cut**, with its own
unlock templates (`SURVIVE [A] DAYS ON HARDCORE TO UNLOCK`,
`SURVIVE [A] WEEK(S) ON HARDCORE TO UNLOCK`). It is not in the shipped game. Noted here
because if hardcore-flavoured fields or enum values turn up in captured clan/journey
structures, **this is why** — they are vestigial, not a feature to implement.

### 7.2 Things to make configurable rather than hard-coded

Because they are `[UNKNOWN]`: the daily-supplies requirement formula; surplus-per-recruit
rate; number of survivors that transition state per failed day; sick→dead delay; healing
costs; booster grant thresholds; starting population (5 is `[LIKELY]`, not certain).

### 7.3 The one local task that would close the remaining gaps

The name pool and activity-message pool are now **recovered** (§1.6) — but from a
**pre-release** build. The highest-value remaining local task is to **verify them against
retail**, which this repo can already do: psarc extraction works
(`research/notes/2026-08-14-blowfish-psarc-solve.md`) and a string-dump pipeline exists.

Concretely: grep the extracted retail localisation paks for distinctive activity-message
templates — `spit-roasting a raccoon`, `planting kale in the garden`, `considering eating
the cat`, `Gangrene is beginning to set in` — and the name-pool anchors `Arnaldo`, `Vlahos`,
`Kowalski`. Finding them confirms the pool shipped unchanged; the adjacent lines will then
give the retail pool exactly, plus the retail values of `Supplies Needed`, unlock-condition
templates, and any numeric constants embedded in the text.

Tooling others have used for TLOU psarc/localisation, if useful:
<https://github.com/amrshaheen61/TLOU_PSARC_Tool>.

Confirmed present in **this repo's own EBOOT string dump** already: `clan/intro-world`,
`clan/hunter`, `clan/firefly`, `clan/tutorial-supplies-1`, `clan/tutorial-supplies-2` —
asset/screen keys, so clan UI content is data-driven and extractable.

**Why this matters for the wire format:** if the name pool ships in the client, the server
may only need to persist a seed or small index per survivor rather than name strings. That
is a materially smaller protocol surface. Decide this before designing the roster message.

### 7.4 Corroborating what this repo already knows

`research/notes/clan-tus-commerce-findings.md` concluded that clan/progression data goes
through a custom Naughty Dog HTTP(S) backend rather than Sony NP storage (no `sceNpTus*`
imports; only `sceNpScoreInit` from Score). Nothing in the public metagame record
contradicts that — and the state list in §7.1 is large and bespoke enough that a custom
backend is exactly what you would expect. The metagame documented here is therefore a
specification for *that* backend's contents.

---

## 8. Open questions, conflicts, and gaps

**Numeric gaps that block a faithful simulation. These are the real blockers — everything
else in this note is documented.**
1. `[UNKNOWN]` **Daily supplies requirement formula.** Two usable pairs, both ~pop 96–99,
   both ≈0.85/survivor. Cannot distinguish linear from sub-linear from composition-weighted.
2. `[UNKNOWN]` **Surplus-to-recruit conversion rate.** No source gives any number.
3. `[UNKNOWN]` **Per-failed-day transition counts** (how many healthy→hungry, hungry→sick).
   I searched specifically for a proportionality rule; none exists publicly.
4. `[UNKNOWN]` **Sick→dead timing.** Indirect evidence suggests ~2 failed days from fully
   healthy to first deaths, but that is inference from a quitting exploit, not a spec.
5. `[UNKNOWN]` **Healing cost per hungry vs. sick survivor**, and whether healing steps
   sick→hungry→healthy or jumps straight to healthy.
6. `[UNKNOWN]` **Booster grant thresholds** (one unverified estimate: ~1 per 4–5 population).
7. `[UNKNOWN]` **Whether a hard population cap exists.** `MAX CLAN SIZE` strings look like a
   high-water-mark stat, not a ceiling.
8. `[UNKNOWN]` **Blue-can supply value outside Survivors mode**; the Survivors "5 + 5"
   figure is one self-doubting poster.
9. `[UNKNOWN]` **Whether Factions has a hidden matchmaking skill rating.** The `skill_rating`
   strings in the leaked table are Uncharted 3 leftovers and prove nothing either way.
10. ~~Gesture unlock table~~ — **CLOSED**, retrieved via the MediaWiki API (§5.3).
11. `[UNKNOWN]` Shotgun's supplies unlock threshold — the wiki gives LP and parts cost but no
    `{supplies}` annotation, unlike its sibling purchasables. May be unlock-at-start; may be
    an omission.
12. ~~Per-skill supplies unlock thresholds~~ — **mostly CLOSED** (§6.3): a full single-source
    table now exists for all 13 base skills except **Sharp Ears L2** (`[UNKNOWN]`) and
    whether DLC-skill upper tiers carry an extra supplies gate (`[UNKNOWN]`).
13. `[CONFLICT]` First-Aid Training heal rate — 10 vs 20 HP per 2s at L2, confused further by
    sources mixing up HP and parts. See §6.3.

**Gaps CLOSED by this note** (previously expected to be unanswerable): the survivor name
pool, the full activity-message pool, the per-survivor state enum, the rank mechanic, and —
decisively — the fact that gear is gated by cumulative supplies rather than rank.

**Verification debt:** everything marked `[STRINGS]` comes from a **pre-release (2013-05-31)
build**. It is first-party and internally consistent with the retail record, but it has not
been checked against a retail extraction. §7.3 describes how to close that cheaply.

**Direct source conflicts, unresolved:**
- **Mission pick limit.** "you can only pick missions a total of 6 times in one 12 week
  journey" (GameFAQs) vs. the PSNProfiles 8-tier ladder implying up to 8 picks, vs. 16
  event slots per journey. Cannot reconcile from sources.
- **Healing boundary.** Wiki: heal by "collecting **more than** the target". Video guide:
  "**meeting or exceeding**".
- **Matches per journey.** 84 days is arithmetically certain (12×7), but a veteran says
  "only **83** matches per journey" (<https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>).
  Possibly the final day resolves without a playable match, or possibly just an off-by-one
  in a forum post. Worth confirming — it affects the day counter's terminal condition.
- **PSNProfiles internal inconsistency**: the same guide says a journey is "84 matches" and
  later "you'd normally have to complete **168 games**". 168 = 2 × 84, i.e. both the Firefly
  and Hunter trophies. Not a real conflict, but easy to misread.

**Version divergence to watch:** PS3 starts at 8 loadout points, Remastered at 9. Most
online guides are Remastered-era. `[UNKNOWN]` whether the supplies thresholds themselves
also shifted.

---

## 9. Source list

Primary / highest value:
- **Leaked MP string table, May-31-2013 demo build (first-party game text)**: <https://pastebin.com/raw/kM7bFGy9>
- Eurogamer's contemporary report on that leak: <https://www.eurogamer.net/the-last-of-us-leaked-multiplayer-details-point-to-in-depth-clan-based-survival-mode>
- Naughty Dog community manager on the rank number ("no such thing as 'levels' in TLOU MP"): <https://gaming.stackexchange.com/questions/121726/what-is-the-number-next-to-your-name-in-multiplayer>
- The Last of Us Wiki — Factions MP: <https://thelastofus.fandom.com/wiki/Factions_MP>
- The Last of Us Wiki — Head item (full unlock schedule): <https://thelastofus.fandom.com/wiki/Head_item>
- The Last of Us Wiki — Emblem: <https://thelastofus.fandom.com/wiki/Emblem>
- The Last of Us Wiki — **Survival skills** (full LP-cost table; note the URL is lowercase `skills`, the capitalised variant 404s/times out): <https://thelastofus.fandom.com/wiki/Survival_skills>
- Community loadout calculator, independent corroboration of every skill LP cost: <https://freddybushboy.github.io/tlou-loadout/> (data file: `js/services/skillService.js`)
- PSNProfiles, *The Last of Us — Multiplayer Missions Guide* (BlindMango & Lordidude): <https://psnprofiles.com/guide/596-the-last-of-us-multiplayer-missions-guide>
- Naughty Dog blog, *The Last of Us Remastered Multiplayer: Factions* (Erin Daly / Quentin Cobb interview): <https://www.naughtydog.com/blog/the_last_of_us_remastered_multiplayer_factions>
- GameFAQs, Krystal109 *The Last of Us — Guide and Walkthrough* v1.5 (only source for per-skill supplies-unlock thresholds; §6.3): <https://gamefaqs.gamespot.com/ps3/652686-the-last-of-us/faqs/67221>
- Eurogamer, *Stealth, scavenging, crafting & clans* (Erin Daly interview, 2013-06-04): <https://www.eurogamer.net/stealth-scavenging-crafting-and-clans-the-last-of-us-multiplayer-detailed>

Secondary:
- GameFAQs, *The Last of Us: Factions Multiplayer Resources*: <https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69784044>
- GameFAQs, *Earning more supply points as population increases in Factions*: <https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69781556>
- GameFAQs, *Parts to supplies*: <https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66814187>
- GameFAQs, *Can someone explain multiplayer to me*: <https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66474606>
- YouTube, DeltaCanuckian, *12 Weeks Metagame — TLoU Factions Survival Guide ep.5*: <https://www.youtube.com/watch?v=NfLYMnZwB-k>
- Game Developer, *My Favorite Features — Meta Game in Last Of Us Factions Multiplayer*: <https://www.gamedeveloper.com/design/my-favorite-features---meta-game-in-last-of-us-factions-multiplayer>
- Haywire Magazine, *How The Last Of Us Factions Endures and Survives*: <https://haywiremag.com/features/how-the-last-of-us-factions-still-endures-and-survives/>
- IGN wiki, Multiplayer: <https://www.ign.com/wikis/the-last-of-us-part-1/Multiplayer>
- PixlBit, *Last of Us multiplayer*: <http://www.pixlbit.com/blog/4028/last_of_us_multiplayer>
- PlayStationTrophies.org, Hunter trophy: <https://www.playstationtrophies.org/game/the-last-of-us-remastered/trophy/89717-Hunter.html>
- PlayStation LifeStyle, *How to Survive The Last of Us' Online Multiplayer*: <https://www.playstationlifestyle.net/2013/06/27/how-to-survive-the-last-of-us-online-multiplayer/>
- TrueTrophies, TLoU Remastered multiplayer walkthrough (clearest clan-UI documentation): <https://www.truetrophies.com/game/The-Last-of-Us-Remastered/walkthrough/17>
- The Last of Us Wiki — Patch notes (clan-day advance rule): <https://thelastofus.fandom.com/wiki/The_Last_of_Us/Patch_notes>
- Naughty Dog blog — Supply Drop event (parts→supplies rate is a global tunable): <https://www.naughtydog.com/blog/the_last_of_us_supply_drop_and_uncharted_3_rare_treasure_drop_july_4th_even>
- Rank icon set (10 icons, from the old official ND forum): <https://imgur.com/a/hS88H> and <https://static.wikia.nocookie.net/thelastofus/images/e/ed/Multi_rankicons.jpg>
- First-hand account of randomly-generated clan names + notification feed: <https://www.deviantart.com/thegouldenway/art/Factions-Week-1-Clan-Notifications-429588848>
- Critical Gamer MP review (survivors are "only ever numbers and text"): <https://criticalgamer.co.uk/2013/06/20/the-last-of-us-multiplayer-review/>
- The Game Fanatics (confirms the "choose which friend lives" screen): <https://thegamefanatics.com/hold-that-molotov-why-the-last-of-us-had-the-most-underrated-multiplayer-of-the-last-decade/>
- N4G, *How to Farm Supplies in The Last of Us Multiplayer* (comments contain the 160/day and "clan size of 300" data points): <https://n4g.com/news/1289566/how-to-farm-supplies-in-the-last-of-us-multiplayer>
- GameFAQs, quit-path day semantics: <https://gamefaqs.gamespot.com/boards/783739-the-last-of-us-remastered/69897154> and <https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67320819>
- GameFAQs, rank-symbol mechanics: <https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67196264>, <https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/67763979>, <https://gamefaqs.gamespot.com/boards/652686-the-last-of-us/66792965>

Dead sources (noted so nobody re-burns time on them):
- `userguides.eu.playstation.com` — DNS no longer resolves; the official PlayStation user
  guide for TLoU Remastered is gone. Its Factions text survives only in search-engine
  snippets, which is a real loss since it was the closest thing to an official manual.
- `tlou-loadout.com` — the loadout calculator referenced by contemporary guides; the domain
  is dead. **Superseded and closed:** an equivalent calculator is live at
  <https://freddybushboy.github.io/tlou-loadout/> and its data file was fetched and parsed
  for §6.3.

### Retrieval tips (these cost real time to rediscover)

1. **Use the MediaWiki API, not the HTML page.** Fandom returns HTTP 402 to plain fetches
   and its pages frequently time out crawler-based fetchers, but the API is open and returns
   clean wikitext including full tables:
   ```
   curl "https://thelastofus.fandom.com/api.php?action=parse&page=Gesture&prop=wikitext&format=json"
   ```
   This is how the Gesture table in §5.3 was recovered after two crawler failures. It is the
   most reliable route for any remaining wiki table.
2. **Fandom titles are case-sensitive past the first letter.** `Survival_Skills` fails;
   `Survival_skills` works. An apparent "page unavailable" may just be a URL error.
3. `psnprofiles.com` returns 403 to plain fetches — use a crawler-backed fetcher.
4. `web.archive.org` is blocked for direct fetches in this environment.
