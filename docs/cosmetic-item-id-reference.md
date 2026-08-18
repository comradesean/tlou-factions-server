# Factions cosmetic item-id reference (StringId ↔ name)

Complete, validated map of the three head-item DC arrays to their in-menu names.
Built by parsing `research/net1bin/net1.bin` (DC00 archive) and pairing each
array's StringIds (in index order) against the retail customization menu lists
(user-provided, 2026-08-17). All three arrays match their menu counts exactly
(39 / 9 / 8), so the StringId↔name pairing is authoritative.

Source arrays (char record faction 1 / `0x3853C446`, record index 0): slot2 hat
= DC key `0x5854FB89`, slot3 mask = `0xC57086FD`, slot4 helmet = `0x49ECE8CD`.
Resolution/format: see `2026-08-17-member-blob-vanity-semantics.md` §7. Item id
lives in the profile at `P+0x670` (hat), `P+0x674` (mask), `P+0x678` (helmet);
`FUN_0033ff54` maps id → array index; the index drives the model.

Gestures (11, index 0 = NONE) and any 4th head category are NOT resolved through
this slot2/3/4 path and are not part of the in-match head-item render — listed at
the bottom for completeness only.

Note: **`0x6A86861F` = "Default" is a shared sentinel** — it is index 0 of BOTH
the hat and mask arrays (same StringId in both). Helmets have **no** "Default"
entry (index 0 = Riot Helmet, a real item).

## Hats — DC array `0x5854FB89` (39)

| idx | StringId | name |
|----|----------|------|
| 0 | `0x6A86861F` | Default *(shared sentinel)* |
| 1 | `0xDA9C8E3C` | Baseball Cap |
| 2 | `0x0ED38B5A` | Beanie |
| 3 | `0x0390AD83` | Crochet Beanie |
| 4 | `0x64138E3A` | Jeep Cap |
| 5 | `0xD52396B9` | Greek Fisherman |
| 6 | `0x66724F01` | Fedora |
| 7 | `0x6606EEEC` | Conductor Cap |
| 8 | `0x16999596` | Cadet Cap |
| 9 | `0x93EA5D87` | Straw Cowboy Hat |
| 10 | `0x77CECB4E` | Winter hat |
| 11 | `0xBA7C3C6D` | Legionairre |
| 12 | `0xD0338536` | Flat Cap |
| 13 | `0x55073B41` | Deerstalker |
| 14 | `0x1916E031` | Head Wrap |
| 15 | `0x2EC84E87` | Pawkul |
| 16 | `0x02415548` | Norwegian Hat |
| 17 | `0x51C626F6` | Sou'wester |
| 18 | `0x0AE4CE67` | Hunting Hat |
| 19 | `0xC2D1AF0F` | Bucket Hat |
| 20 | `0xA7BBBDAE` | Bowler Hat |
| 21 | `0x71C38587` | Pith Hat |
| 22 | `0x730FD6F9` | Military Hat |
| 23 | `0xAA30D7B8` | Skipper |
| 24 | `0x838BED5B` | Cavalry Hat |
| 25 | `0x3A33E789` | Garrison Cap |
| 26 | `0x015CFEFD` | Civil War Hat |
| 27 | `0x65B7BC41` | Porkpie |
| 28 | `0x39134340` | Boonie Hat |
| 29 | `0x6D4886FC` | Flame Head Wrap |
| 30 | `0x400E0354` | Campaign Cover |
| 31 | `0x498C383A` | Rancher |
| 32 | `0x785C4DE9` | Fur Aviator |
| 33 | `0x0751B034` | Headphones |
| 34 | `0x44CF1EE3` | Aussie Cattleman |
| 35 | `0x7A8DED97` | Poet Fedora |
| 36 | `0x0C1FD824` | Naval Officer Hat |
| 37 | `0x6060D856` | Beret |
| 38 | `0xD48B7C30` | Black Rancher Hat |

## Masks — DC array `0xC57086FD` (9)

| idx | StringId | name |
|----|----------|------|
| 0 | `0x6A86861F` | Default *(shared sentinel)* |
| 1 | `0x456DB03C` | Bandanna |
| 2 | `0x41ACAD8B` | Surgeon Mask |
| 3 | `0x838B45B6` | Goggles |
| 4 | `0xE47D6EC3` | Ballistic Mask |
| 5 | `0x2AD2C914` | Pollution Mask |
| 6 | `0x37D2BDED` | Hockey Mask |
| 7 | `0x811B52B6` | Combat Mask |
| 8 | `0x4E6DA88F` | Skull Mask |

## Helmets — DC array `0x49ECE8CD` (8, no Default)

| idx | StringId | name |
|----|----------|------|
| 0 | `0x0AE569A8` | Riot Helmet |
| 1 | `0xFD0E0860` | Biker Helmet |
| 2 | `0xF341FAEE` | Military Helmet |
| 3 | `0xDB3B6070` | Spiked Helmet |
| 4 | `0xA5364F12` | Battle Helmet |
| 5 | `0xD3766069` | Combat Helmet |
| 6 | `0xAE8A48B1` | SWAT Helmet |
| 7 | `0x5DF72076` | Flight Helmet |

## Decoded equipped loadouts (from real profile.21, 2026-08-17)

| slot | comradesean | mgnomad2 |
|------|-------------|----------|
| hat (`P+0x670`) | `0x93EA5D87` Straw Cowboy Hat | `0x6A86861F` **Default** |
| mask (`P+0x674`) | `0x41ACAD8B` Surgeon Mask | `0x456DB03C` **Bandanna** |
| helmet (`P+0x678`) | `0xFD0E0860` Biker Helmet | `0x0AE569A8` **Riot Helmet** |

comradesean renders this stably in-game (live-confirmed). mgnomad2's saved
loadout is coherent (2 of 3 deliberate non-default picks — Bandanna, Riot — so
his customization writes persist), yet he renders **bald + random every match**
→ a render-time bypass of his profile, not a data problem. See
`2026-08-17-member-blob-vanity-semantics.md` §8.

## Gestures (reference only — not head-item slot2/3/4)

11 entries, index 0 = NONE: NONE, Fist Pump, Knuckles, Chest Pound, Blow Smoke,
Salute, Come Here, Back Off, Neck Crack, Bow, Close Call. StringIds not dumped
(separate emote system, not part of the appearance-model render pipeline).
