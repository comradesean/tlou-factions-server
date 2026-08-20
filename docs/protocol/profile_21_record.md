# profile.21 — player progression record

Companion evidence for `protos/profile_21.ksy`.

- **status:** partial (landmark scalars confirmed; ~80% of the record is
  zero/reserved or DC-indexed and not per-slot decoded).
- **direction:** client ↔ server, over HTTP/S3 — `GET`/`PUT`
  `profiles/<online_id>/profile.21`. This is the entire persisted player
  progression record (`NetPlayerData`), not a wire opcode, so the schema file
  carries no `0x…` opcode prefix.

## Transport / container (out of scope for the schema)

On the wire the file is:

```
LZF( [BE u32 version][BE u32 enc_len][ Blowfish-ECB( payload(0x5000) || pad(4) || HMAC-SHA1(20) ) ][ 8 slack ] )
```

- LZF-decompresses to a fixed **0x5028** bytes.
- The encrypted body (`enc_len` = 0x5018) is Blowfish-ECB under the solved
  static key; an HMAC-SHA1 (net-drm key) covers the 0x5004 bytes before it.
- **No server module implements this container at runtime** (see below for
  why it isn't needed there) but a standalone research codec now exists:
  `research/tools/profile21_codec.py` (added 2026-08-19) implements the LZF
  decompressor (not present anywhere else in the repo) plus the same
  Blowfish-ECB core `server/lib/psarc_crypt.py`/`userdata_crypt.py` use for
  the unrelated `.psarc.crypt`/`.txt.crypt` formats (no LZF layer there; HMAC
  plaintext and placed *before* the ciphertext, not in-band as the last 20
  bytes the way profile.21 does it - the two formats only share the
  Blowfish primitive and the two static keys). The codec has a `dump`
  command (prints every field this doc/`.ksy` confirms) and a `diff`
  command (byte-diff two captures of the same account) - `diff` is the
  exact technique that live-verified `custom_appearance`'s
  `equipped_item_ids` and the `emblem_layers` persisted format below.
  `protos/profile_21.ksy` models the **decrypted + decompressed plaintext** only.
- At runtime `server/http_gateway.py` serves and stores profile.21 as a
  byte-exact pass-through — the client signs its own record and the server
  returns it unchanged, so the container is never re-derived server-side and the
  self-HMAC stays valid.

## Endianness

Big-endian throughout (PPC target): `version` reads `00 00 00 15`, and every
scalar is assembled BE in the decompile.

## Confirmed landmark fields

Offsets are record-relative (`P+…`); the schema's `game_data` instances use the
payload-relative form (`P − 8`). Every row was checked against **both real
round-tripped sample records**
(`server/data/served_content/profiles/{comradesean,mgnomad2}/profile.21`).

| P+off | name | evidence | confidence |
|---|---|---|---|
| 0x0000 | version | `FUN_003cb818` writes 0x15; both samples = 21 | high |
| 0x0004 | enc_len | `FUN_003cc938` writes 0x5018; both = 0x5018 | high |
| 0x0008 | loadouts[4][14] u32 | `FUN_003ccb88`/`FUN_003cccd8`, asserts `<14`,`<4`; both all-zero (default) | high |
| 0x0300 | title_badge | note §5/§6, `lbz r0,771` = blob[9] source | high (offset) |
| 0x0654 | member_blob_word | note §6 (member card `card_stat_2/3` source) | high (offset) |
| 0x0A1C | total_matches | note §2; **== matches_mode_a + matches_mode_b (11 / 7)** | high |
| 0x0A20 | total_wins_result3 | note §2, `0x3f2750` result==3; 10 / 7 | high |
| 0x0A38 | survivor_count | `FUN_00378a24` `stw…,2616`; 86 / 33 | high |
| 0x0A3C | survivor_seeds[] u64 | `*(u64*)(base+i*8+0xa3c)`; populated | high |
| 0x1AD4 | day_counter | note §3 `0x37d948`; 13 / 8 | med-high |
| 0x1AD8 | day_counter2 | note §3 `0x37da4c`; 13 / 8 | med-high |
| 0x1BE0 | pop_highwater_a | note §3 `0x37e340`; **== pop_highwater_menu (81 / 33)** | high |
| 0x1BF0 | clan_state | note §5; 2 / 2 | med |
| 0x1E20 | pop_accumulator | note §3 `0x37e430`; **== pop_accum_highwater (569 / 139)** | high |
| 0x1E24 | pop_accum_highwater | note §3 `0x37e4f4`; 569 / 139 | high |
| 0x1E28 | clan_started | note §3 `0x37e6b8`; set by OnMatchEnd; 0 / 0 | high |
| 0x1E30 | pop_highwater_menu | note §1 `0x37e38c`; 81 / 33 | high |
| 0x1E34 | matches_mode_a | `*(byte*)(base+0x1e34)`, writer `0x3f2598` guard mode==2; 6 / 3 | high |
| 0x1E38 | matches_mode_b | `+0x1e38`, writer `0x3f2654` guard mode==3; 5 / 4 | high |
| 0x1E44 | journeys_completed | `+0x1e44<<0x18`, writer `0x37e6f4`; feeds `member_data.rank_value` | high |
| 0x1E48 | healthy_count | note §5 (per-player, menu-written); 4 / 6 | med |
| 0x1E4C | wins_mode_a | note §2 `0x3f25f8` team+result==3; 5 / 0 | high |
| 0x1E50 | wins_mode_b | note §2 `0x3f26b4`; 4 / 0 | high |
| 0x1E54 | pop_highwater_c | note §3 `0x37e740`; 0 / 0 | med-high |
| 0x066C | survivor_variant_id | `dc_hash_crack.py` vs retail-disc `.dci` corpus: comradesean=`*cc-fl-base*`, mgnomad2=`*cc-hb5-base*` (CORRECTED 2026-08-19 - was wrongly claimed identical across both accounts) | high |
| 0x0670-0x0687 | equipped_item_ids[6] | first 3 resolved via `text_table.py` vs `text1.psarc`: "Norwegian Hat"/"Ballistic Mask"/"Military Helmet" - human-confirmed against live in-game UI | high (slots 0-2) / open (3-5) |
| 0x07E8-0x0807 | emblem_layers[4] | layout, shape catalog (all layers), rotation/scale/opacity, colour-grid position all live-edit-verified, see `research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md` §9-§10 and `research/notes/2026-08-20-emblem-shape-catalog.tsv` | high (layout, shape catalog x4 layers, opacity/scale endpoints, colour grid formula) / open (rotation exact curve, colour SWATCH contents, 3 unexplained bytes) |
| 0x5008 | hmac_pad | zero | high |
| 0x500C | hmac_sha1 | verified OK on both samples | high |
| 0x5020 | slack | zero | high |

Cross-checks that prove alignment (both samples): `total_matches ==
matches_mode_a + matches_mode_b`, `pop_highwater_a == pop_highwater_menu`,
`pop_accumulator == pop_accum_highwater`.

## Genuinely unmapped / needs more work

- **DC-indexed net-stat slots** (P+0x91C upward, and the scattered named-var
  words at P+0x2D0–0x364 and P+0x654–0x854): the array mechanism is confirmed
  (`record[8 + (statIdx+581)*4]`) but each slot's meaning — including the
  lifetime-supplies stat that gates gear — is registry-assigned in the data
  compiler `.pak`, not recoverable from the EBOOT.
- **Per-survivor roster sub-structure** (P+0xA3C–0x1A3C beyond the u64 seed
  array): dense per-survivor appearance/state; only the name-seed array is
  decompile-pinned.
- **Clan cosmetics / emblem block**: real block is **P+0x7E8–0x807** (four
  layers x `{shape_word:{shape_index,rotation,scale,?}, color_word:{color_index,opacity,??}}`),
  not P+0x660–0x67C (that range is `custom_appearance`, the character/
  survivor/item block - unrelated to emblems, see `custom_appearance`
  above). SOLVED 2026-08-20, ALL FOUR LAYERS, same formula, no per-layer
  offset: `shape_index=0` -> "None" (sentinel), `shape_index` in `[1,192]`
  -> the retail disc's 192-entry flat name catalog (`net.bin` file offset
  `0x2be68`) at `[shape_index-1]` - proven by 192 consecutive live,
  human-confirmed pairs on layer0 (the ENTIRE catalog, zero mismatches)
  plus independent spot-checks on layer1 and layer2 that confirmed the
  identical formula and RETRACTED an earlier "layer2 uses a different
  `+41` offset" theory (that theory was built on a mislabeled ground-truth
  value from early in the investigation). layer3 inferred to match, not
  independently tested. Full table: `research/notes/2026-08-20-emblem-shape-catalog.tsv`.
  Rotation/scale/opacity (`shape_word` bytes 1-2, `color_word` byte 1) are
  also solved - real, live fields, not static as first thought - each
  confirmed by a controlled edit moving between two known endpoints
  (e.g. opacity `0xff`=visible/`0x00`=invisible), though the exact
  intermediate curve isn't pinned for any of the three. The colour
  PICKER's grid position is separately solved: a plain 8x8 swatch grid,
  `color_index = row*8 + column` (0-indexed, row-major, no sentinel) -
  confirmed at both grid corners. What each of the 64 swatches actually
  renders as (RGB/palette value), and the DC `net-emblem-colors` symbol's
  own contents, remain unmapped - two different things, don't conflate
  them. `shape_word` byte 3 and `color_word` bytes 2-3 are still
  genuinely unexplained (untouched by every edit tried so far). Full
  derivation, including the EBOOT resolver decompile
  (`FUN_00345038`/`FUN_0034527c`) and the two wrong theories this pass
  worked through before landing on the final answer:
  `research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md` §9-§10.
- **`unknown_1e2c`, `unknown_1e3c`, `flag_1e40`, `healthy_count` semantics:**
  populated but not pinned to a decompile writer.
- **Everything P+0x1E74 → P+0x5008** (~0x3190 bytes): zero in both samples —
  reserved space for higher stat indices / more survivors than these accounts
  have earned.
- **Mode-A vs Mode-B identity:** the `FUN_003a3d40 == 2/== 3` split (which is
  Supply Raid vs Survivors) is not resolved.

## Caveat

The record is ~80% zero/reserved. This map is anchored on two real
round-tripped samples whose match/population values are **live** (the S3 `PUT`
round-trip began working; the earlier research notes captured an all-zero
snapshot that this supersedes). Confirm any newly-populated field against a
third sample before trusting it.
