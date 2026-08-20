meta:
  id: profile_21
  endian: be
  license: CC0-1.0
doc: |
  Direction: client<->server (S3 GET/PUT of profiles/<online_id>/profile.21).

  The ~0x5028-byte NetPlayerData progression record, version 21. This .ksy
  models the DECRYPTED+DECOMPRESSED plaintext. On the wire the file is
  LZF( [u32 ver][u32 enc_len][ Blowfish-ECB( payload || pad || HMAC ) ][8] );
  that container framing is out of scope for this schema. server/lib/psarc_crypt.py
  and userdata_crypt.py handle the DIFFERENT .psarc.crypt/.txt.crypt format (no LZF
  layer; HMAC placed/scoped differently) and only share the Blowfish-ECB primitive
  and the two static keys. A STANDALONE CODEC NOW EXISTS (2026-08-19):
  `research/tools/profile21_codec.py` implements the LZF decompressor (not
  present anywhere else in the repo) plus this Blowfish core, and can dump
  every decompile-confirmed field below or diff two captures of the same
  account - the exact technique that live-verified custom_appearance's
  equipped_item_ids and the emblem_layers persisted format (see their own
  doc entries). It is not needed at runtime: server/http_gateway.py
  serves/stores profile.21 as a byte-exact pass-through (the client signs
  its own record), so the container is never re-derived server-side - this
  codec is a research/verification tool only.

  Big-endian throughout (PPC target; version reads `00 00 00 15`, and every
  field is assembled BE in the decompile). Layout from FUN_003cb818 (init),
  the loadout accessors, the survivor-seed accessor, and the OnMatchEnd match
  counters, cross-checked against two real round-tripped sample records
  (server/data/served_content/profiles/{comradesean,mgnomad2}/profile.21).

  CAVEAT: ~80% of the record is zero/reserved (space for higher stat indices
  and more survivors than these accounts have earned). The named scalars below
  are the decompile-pinned ones; large dense regions (DC-indexed net-stat slots,
  the per-survivor roster sub-structure, the clan cosmetics block) are left as
  sized reserved regions because their per-slot meaning lives in the data
  compiler .pak, not the EBOOT - decoding them further needs the DC modules,
  not more EBOOT work. See docs/protocol/profile_21_record.md.
doc-ref: ../docs/protocol/profile_21_record.md
seq:
  - id: version
    type: u4
    doc: "P+0x0000. Schema version, always 21 (0x15); the client resets to defaults if this is not 21."
  - id: enc_len
    type: u4
    doc: "P+0x0004. Encrypted-blob length, always 0x5018 in practice."
  - id: game_data
    size: 0x5000
    type: game_data
    doc: "P+0x0008..P+0x5007. The 0x5000-byte game payload (flat BE-u32 array with subsystem-claimed index ranges)."
  - id: hmac_pad
    size: 4
    doc: "P+0x5008. Four zero pad bytes before the digest."
  - id: hmac_sha1
    size: 20
    doc: "P+0x500C. HMAC-SHA1 over the 0x5004 bytes preceding it (net-drm key); verified OK on both real samples."
  - id: slack
    size: 8
    doc: "P+0x5020. Unused trailing slack, always zero."
types:
  game_data:
    doc: |
      0x5000-byte flat BE-u32 game payload. `pos:` offsets in the instances
      below are payload-relative (= record P-offset minus 8). Everything past
      payload 0x1E6C (P+0x1E74) is zero in both real samples - reserved/unearned.
      Only the loadout table (whose struct is decompile-confirmed) is laid out
      sequentially; the known scalars are random-access instances so no
      sub-structure is invented for the dense DC-indexed regions between them.
    seq:
      - id: loadouts
        type: loadout_mode
        repeat: expr
        repeat-expr: 4
        doc: "Payload 0x000..0x0DF (P+0x008). kNumCustomLoadoutsPerMode = 4 custom loadout modes. All-zero (default items) in both samples."
    instances:
      session_key:
        pos: 0x02F4
        type: u4
        doc: "P+0x02FC. Per-lobby/match session key. FUN_003487a4 re-randomises the character descriptor whenever BE_u32(P+0x2FC) changes vs its saved copy (once per lobby/match cycle); read @0x00348840-0x003488e0. Value not sampled."
      title_badge:
        pos: 0x02F8
        type: u4
        doc: "P+0x0300. Low byte = lobby title/badge index (blob[9] source). 0 in both samples."
      equipped_gesture_id:
        pos: 0x0300
        type: u4
        doc: |
          P+0x0308. RENAMED 2026-08-20 from `gated_customization_id` (kept
          as an alias in old docs) once its real meaning was pinned: this
          is the account's EQUIPPED GESTURE. Still gated the same way as
          previously documented - FUN_0033f9b4's tail zeroes it when it
          fails the unlock check FUN_003ec084 (kind=0); mgnomad2's `0`
          value is consistent with "no gesture unlocked/selected" under
          that same gate, not a separate mechanism.

          CONFIRMED via SIX controlled live edits (change gesture in-game,
          save, decode, diff against the pre-change snapshot - each
          isolated a single clean change to exactly this word, nothing
          else):

              0x0e69839d = None
              0xd40e5495 = Fist Pump
              0xdd8c6ffb = Knuckles
              0xc70a2249 = Chest Pound
              0xd94d724c = Blow Smoke (the account's ORIGINAL/default gesture)
              0x02d688fe = Back Off

          Also confirmed LOCKED for this account (no value captured, since
          a locked option can't be selected/saved): Salute, Come Here,
          Neck Crack, Bow, Close Call.

          NOT resolved: the hash algorithm. All six values were checked
          against `research/tools/text_table.py` (the `text1.psarc`
          StringId table - including confirming "Blow Smoke"'s OWN
          text-table key, `0x328e4395`, does NOT match its
          `equipped_gesture_id` value, ruling out "it's just the display
          name's StringId" as a hypothesis) and
          `research/tools/dc_hash_crack.py` (the disc's `crc32_mpeg2`
          compiler-symbol corpus) - no match under either tool for any of
          the six values. Whatever hash/id scheme this is, it is
          DIFFERENT from every other id scheme this project has cracked so
          far (DC00 directory hashes, text StringIds). A live RPCS3
          memory read is the only remaining lever identified for this
          field specifically.
      member_blob_word:
        pos: 0x064C
        type: u4
        doc: "P+0x0654. A separate word PRECEDING the custom_appearance block (which itself starts 12 bytes later, at P+0x0660 - not literally part of that struct despite an earlier version of this doc calling it \"word 0\" of it). Copied verbatim into the member card (member_data card_stat_2/card_stat_3). RE-CHECKED 2026-08-19 against 842 live 0x13a frames (not just the original 2 samples): still exactly zero in every one, even after the S3 profile round-trip was implemented and confirmed working with genuine non-zero data elsewhere in the same file (custom_appearance's equipped_item_ids etc). See member_data.ksy's card_stat_2 doc for the full finding."
      custom_appearance:
        pos: 0x0658
        type: custom_appearance
        doc: "P+0x0660..P+0x068F. Persisted MP character-appearance block (chosen character, survivor variant, equipped items, palette). See the custom_appearance type."
      emblem_layers:
        pos: 0x07E0
        type: emblem_layer
        repeat: expr
        repeat-expr: 4
        doc: "P+0x07E8..0x0807. Four emblem layers x {shape_word:{shape_index,rotation,scale,unknown}, color_word:{color_index,opacity,unknown x2}}. SOLVED 2026-08-20: every field except the two unknown bytes is confirmed by controlled live edits, and shape_index resolves to a real display name (all four layers, identical formula - see the emblem_layer type doc and research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md §9). color_index is a solved GRID POSITION (row*8+col in an 8x8 swatch picker) but the swatches themselves have no recovered names/RGB values."
      total_matches:
        pos: 0x0A14
        type: u4
        doc: "P+0x0A1C. Incremented every match. Cross-checks: == matches_mode_a + matches_mode_b in both samples (11 / 7)."
      total_wins_result3:
        pos: 0x0A18
        type: u4
        doc: "P+0x0A20. Incremented when match result == 3 (win). 10 / 7 in the samples."
      randomize_latch:
        pos: 0x0A20
        type: u4
        doc: "P+0x0A28. Customization-randomise latch: FUN_0034279c sets it to 1 (@0x00348960) the first time the deterministic profile-driven appearance is built, so the randomise arm FUN_003433d0 (guarded on ==0) does not re-roll afterwards. 1 / 1 in both samples (both took the normal, non-random arm)."
      survivor_count:
        pos: 0x0A30
        type: u4
        doc: "P+0x0A38. Clan roster / population count; the length of survivor_seeds. 86 / 33 in the samples."
      survivor_seeds:
        pos: 0x0A34
        type: u8
        repeat: expr
        repeat-expr: survivor_count
        doc: "P+0x0A3C. u64 name seeds, one per survivor (survivor_count entries)."
      day_counter:
        pos: 0x1ACC
        type: u4
        doc: "P+0x1AD4. Clan-day / settlement counter. 13 / 8."
      day_counter2:
        pos: 0x1AD0
        type: u4
        doc: "P+0x1AD8. Companion settlement counter. 13 / 8."
      faction:
        pos: 0x1AD4
        type: u4
        doc: "P+0x1ADC. Player faction / MP team: 0 or 1 (Hunters / Fireflies), asserted < NetInfo::kMaxNetTeams (==2) by FUN_00340e84/00340a6c/00340f80/00341344. Selects which chosen_char_id slot in custom_appearance is live. 1 / 1 in both samples."
      pop_highwater_a:
        pos: 0x1BD8
        type: u4
        doc: "P+0x1BE0. Population high-water (written at OnMatchEnd). 81 / 33; equals pop_highwater_menu."
      clan_state:
        pos: 0x1BE8
        type: u4
        doc: "P+0x1BF0. Clan/settlement status enum. Seeded to a DC-bounded random value at clan setup (FUN_0037a7b4 @0x37aba8), then ticked down when idle (@0x37d13c) or re-randomised when active (@0x37d180) by the settlement updater FUN_0037cf90. 2 / 2 (in-bounds). Exact enum meaning is DC-config-bounded."
      pop_accumulator:
        pos: 0x1E18
        type: u4
        doc: "P+0x1E20. Cumulative population accumulator. 569 / 139; equals pop_accum_highwater."
      pop_accum_highwater:
        pos: 0x1E1C
        type: u4
        doc: "P+0x1E24. max(., pop_accumulator). 569 / 139."
      clan_started:
        pos: 0x1E20
        type: u4
        doc: "P+0x1E28. Set to 1 by OnMatchEnd (a result flag, not a gate). 0 / 0 in the samples."
      milestone_latch_1e2c:
        pos: 0x1E24
        type: u4
        doc: "P+0x1E2C. One-shot milestone latch (bitfield). FUN_0035f1bc sets bit0 (`ori r0,r31,1` / `stw r0,7724(r3)` @0x35f26c/0x35f274) the first time its predicate-6 holds at game-state==3, awarding event 0x40b5d875 - resolved via `research/tools/text_table.py` against `text1.psarc`'s `2.networking` StringId table (see docs/protocol/text_table.md) to the display string \"Added Extra Supplies from Promotion!\". Persisted so the award fires once. comradesean 1 (done) / mgnomad2 0 (not)."
      pop_highwater_menu:
        pos: 0x1E28
        type: u4
        doc: "P+0x1E30. Population high-water (menu-written); equals pop_highwater_a. 81 / 33."
      matches_mode_a:
        pos: 0x1E2C
        type: u4
        doc: "P+0x1E34. Matches played, mode A (writer guarded on mode == 2). 6 / 3."
      matches_mode_b:
        pos: 0x1E30
        type: u4
        doc: "P+0x1E38. Matches played, mode B (writer guarded on mode == 3). 5 / 4."
      match_ratio_1e3c:
        pos: 0x1E34
        type: u4
        doc: "P+0x1E3C. OnMatchEnd-computed scaled ratio statistic: (matchStatA->0x4 * 6000) / (matchStatB->0x10) (`mulli r29,r29,6000` / `divwu` / `stw r29,7740(r3)` @0x3f29b4-0x3f29c8, also @0x3f2d60 in FUN_003f208c), reported under DC StringId 0x5c494554; cleared to 0 outside a match (@0x3b6124/@0x3b7f00). 0 / 0xE0C2. Precise numerator/denominator meaning is DC-side. NOTE: 0x5c494554 checked against text1.psarc's StringId text tables (docs/protocol/text_table.md) and NOT found in any of the four English category files, nor in bin.psarc/pak23.psarc/actor34.psarc - likely an internal telemetry id with no localized display string, but not conclusively ruled out (untried resources: gallery1.psarc, animstream4.psarc, animtex0.psarc, vtex1.psarc, lut0.psarc, and any 01.11-only content)."
      emblem_location:
        pos: 0x1E38
        type: u4
        doc: |
          P+0x1E40. RENAMED 2026-08-20 from `flag_1e40` once its real
          meaning was pinned - and the old "boolean toggle" description
          was WRONG, not just incomplete: CONFIRMED via two controlled
          live edits as a small enum, not a boolean:

              0 = None
              1 = Torso
              2 = Helmet
              3 = Backpack

          (0->1 confirmed by a clean, isolated diff when set to "Torso";
          1->2 confirmed the same way when set to "Helmet"; 2->3 confirmed
          when set to "Backpack", human-confirmed as the LAST option in
          the in-game menu, so 0-3 is very likely the complete value
          range.) Dedicated setter FUN_003188d4(this, value)
          stores the caller's argument verbatim here (`stw r28,7744(r3)`
          @0x318918) and mirrors it to obj+0xC (UI-refreshed) - this part
          of the original finding stands unchanged, only the value's
          meaning was previously unknown.
      journeys_completed:
        pos: 0x1E3C
        type: u4
        doc: "P+0x1E44. Incremented per journey at OnMatchEnd. Feeds member_data.rank_value (journeys*1000 + weeks). 0 / 0."
      healthy_count:
        pos: 0x1E40
        type: u4
        doc: "P+0x1E48. Healthy-survivor sub-count: RNG-drawn in [1, population-1] by the clan sim (init FUN_0037a7b4 @0x37ac50, per-tick FUN_0037cf90 @0x37d07c) - NOT menu-written as previously thought. 4 / 6."
      wins_mode_a:
        pos: 0x1E44
        type: u4
        doc: "P+0x1E4C. Wins, mode A (team + result == 3). 5 / 0."
      wins_mode_b:
        pos: 0x1E48
        type: u4
        doc: "P+0x1E50. Wins, mode B. 4 / 0."
      pop_highwater_c:
        pos: 0x1E4C
        type: u4
        doc: "P+0x1E54. Population high-water (OnMatchEnd). 0 / 0."
  custom_appearance:
    doc: |
      Persisted MP character-appearance block, P+0x0660..P+0x068F. The descriptor
      builder FUN_00341344 (item loop @0x003414dc, base P+0x660 + i*4 + 8 for
      i=2..7) and the randomise arm FUN_003433d0 (@0x003434ec) read these to build
      the 16-byte render descriptor. The character/survivor/item values are DC
      StringIds: the ids live here, but which model/item each id resolves to is
      data-compiler-assigned (.pak), not in the EBOOT. There is no EBOOT writer for
      survivor_variant_id / equipped_item_ids - the customization menu (DC) writes
      them; the EBOOT only reads them here on load.
    seq:
      - id: chosen_char_id_team0
        type: u4
        doc: "P+0x0660. Chosen character-record id for team/faction 0. Written by the randomise arm FUN_003433d0 @0x003434ec; non-zero => the randomise arm ran at least once."
      - id: chosen_char_id_team1
        type: u4
        doc: "P+0x0664. Chosen character-record id for team/faction 1 (the live one when faction==1, as in both samples)."
      - id: unmapped_668
        type: u4
        doc: "P+0x0668. No traced reader or writer (the item loop starts at P+0x670; the char-id writes are 0x660/0x664). 0 in both samples; left named rather than folded into a pad."
      - id: survivor_variant_id
        type: u4
        doc: |
          P+0x066C. Persisted survivor / appearance-variant StringId;
          linear-searched in the character record's list at +0x0C to yield
          descriptor slot desc[1] (read @0x0034185c; desc[1]=0 if not
          found). CORRECTED 2026-08-19: an earlier pass claimed
          "0x638EF35A in both samples" - that is WRONG, disproven by a
          fresh direct decode of both accounts' live profile.21 (see
          `research/tools/profile21_codec.py`): comradesean =
          `0x638ef35a`, mgnomad2 = `0x92211c99` (DIFFERENT). Both resolved
          via `research/tools/dc_hash_crack.py` against the retail disc's
          `bin.psarc` `.dci` compiler-symbol corpus: comradesean's is DC
          symbol `*cc-fl-base*`, mgnomad2's is `*cc-hb5-base*` - i.e. per-
          account character skin/base variant, exactly as expected (two
          different accounts, two different confirmed real DC symbol
          names, at the correct offset). status: confirmed (mechanism +
          both live values); the DDS/render asset each symbol maps to is
          not further resolved here.
      - id: equipped_item_ids
        type: u4
        repeat: expr
        repeat-expr: 6
        doc: |
          P+0x0670..P+0x0687. Six equipped-item StringIds read by the
          FUN_00341344 loop into desc[2..7]. Only the first three resolve
          to visible render slots (desc[2..4] -> engine slots 2/3/0);
          [3..5] are read but never rendered and are 0 in every capture so
          far.

          RESOLVED 2026-08-19 for the first three (hat/mask/helmet):
          decoded comradesean's live profile.21
          (`research/tools/profile21_codec.py`) and resolved each
          StringId against `text1.psarc`'s English text table
          (`research/tools/text_table.py`, `docs/protocol/text_table.md`):
          `0x02415548` -> "Norwegian Hat", `0xe47d6ec3` -> "Ballistic
          Mask", `0xf341faee` -> "Military Helmet" - all THREE
          independently confirmed byte-for-byte against what the account
          actually had equipped on screen at capture time (a human read
          the in-game UI and it matched exactly). mgnomad2's slot 0
          (`0x6a86861f`) resolves to "Default"; slot 1 wasn't in the text
          table (checked, no match). status: confirmed mechanism (StringId
          -> text_table lookup) for slots 0-2; slots 3-5 still unobserved
          non-zero on any account.
      - id: palette
        type: u4
        doc: "P+0x0688. Character palette id (read @0x0034157c). 0 in both samples."
      - id: tint
        type: u4
        doc: "P+0x068C. Character tint id (read @0x003415b8). 0 in both samples."
  emblem_layer:
    doc: |
      One of the four emblem layers, P+0x07E8+i*8..P+0x07EF+i*8. Layer index
      i (0..3) is passed directly as the cache-slot selector by the draw loop
      in FUN_00345a0c, and pins each layer to a fixed DC category in a fixed
      order: layer0 = net-emblem-layers-frame, layer1 = net-emblem-layers-base,
      layer2 = net-emblem-layers-parts, layer3 = net-emblem-layers-parts AGAIN
      (FUN_003444fc's init code writes the identical parts hash into both the
      3rd and 4th cache slots - not a typo, confirmed in the literal
      instruction stream). See
      research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md.

      status: CONFIRMED for the shape catalog on ALL FOUR layers, plus
      rotation/scale/opacity and the colour grid position formula
      (2026-08-20) - see below -
      the byte layout was already confirmed by three controlled live edits;
      the EBOOT-side resolver is fully decompiled and disassembly-verified
      (FUN_00345038/FUN_0034527c: idx = shape_index % *(u32*)value; name =
      *(u32*)(elemBase + idx*12 + 4); elemBase = *(u32*)(value+4); value =
      the cached DC resolve of that layer's hash) - what was NOT confirmed
      until now was what that chain resolves to at runtime, since raw
      file-offset arithmetic over the DC00 payload (net1.bin/net.bin)
      reaches a multiply-nested tree of typed sub-records at that address,
      not a flat name array.

      SOLVED, 2026-08-20: layer0's (the account UI's "Layer 1") shape
      catalog is the SAME 192-entry flat ASCII name pool this file's
      2026-08-19 pass already found and then wrongly ruled out (see the
      history note below) - `net.bin` file offset `0x2be68`, 12-byte
      stride, name pointer at `elem+0`, 192 contiguous entries. The correct
      formula, PROVEN by 192 consecutive live, human-confirmed
      (shape_index, display-name) pairs with ZERO mismatches (every single
      catalog entry checked, not a sample):

          shape_index == 0            -> "None" (sentinel, not in the catalog)
          shape_index in [1, 192]     -> catalog[shape_index - 1]

      i.e. the earlier pass's two hypotheses failed only because they
      never tried the trivial off-by-one (treating `0` as a reserved "no
      selection" sentinel rather than a valid catalog index) - once that's
      accounted for, the flat, unfiltered, non-modulo catalog is exactly
      right, immediately, with no per-category filtering needed. Also
      recovered along the way: this account's unlock boundary sits at
      catalog index 151 (`tlou-vest`, shape_index=152, display "Vest") -
      every entry after that (40 entries, "Flower" through "Stealth Mask")
      is locked for this account. Full verification methodology and the
      complete 192-entry index->name table:
      research/notes/2026-08-19-emblem-name-resolver-and-dc-catalog.md §9.

      ALL FOUR LAYERS CONFIRMED using the SAME formula, 2026-08-20: layer1
      ("Layer 2", `net-emblem-layers-base`) tested live at shape_index=50 ->
      `catalog[49]` = `shape-egg` = "Egg", exact match. layer2 ("Layer 3",
      `net-emblem-layers-parts`) tested live at shape_index=97 ->
      `catalog[96]` = `tlou-el-diablo` = "El Diablo", exact match - this
      RETRACTS the earlier `shape_index=55 -> El Diablo` claim below as a
      mislabeling from early in the investigation (before the live-diff
      methodology existed), NOT a real second offset. There is no per-layer
      offset: every layer indexes the identical 192-entry catalog the
      identical way. Only the colour catalog (`net-emblem-colors`, hash
      `0xbcbbdfbd`) remains unmapped - see `shape_word`/`color_word`'s
      field docs below for rotation/scale/opacity (all solved 2026-08-20)
      and the colour GRID's own solved formula (a plain 8x8 position grid,
      unrelated to the DC colour catalog's still-unknown contents).

      HISTORY (why this was marked "definitively falsified" for 20+ hours
      before being solved, and why a wrong per-layer-offset theory briefly
      replaced it): the 2026-08-19 pass tested `catalog[shape_index]`
      directly (no offset) and `catalog[shape_index mod family_count]`
      (per-prefix-family, modulo) against the two ground-truth values then
      available (shape_index=48/55) and got real, reproducible mismatches
      under BOTH schemes - a fair test at the time, given what was known.
      It did not think to try the off-by-one sentinel adjustment, which
      turned out to be the entire fix for layer0. The `shape_index=55 ->
      El Diablo` value used in that original test was itself wrong (see
      above) - once layer0's formula was proven on 192/192 entries and then
      independently reproduced on layer1 and layer2 with fresh, carefully
      live-diffed data, the single old "El Diablo" sample no longer held
      up and the simpler one-formula-for-all-layers explanation won.
      Recorded here so a future pass sees the full arc, not just the
      current answer.
    seq:
      - id: shape_index
        type: u1
        doc: "Byte 0 (top byte) of shape_word. For layer0 SOLVED: 0=\"None\", N in [1,192] -> the retail disc's 192-entry emblem name catalog at [N-1] - see this type's doc for the full formula and research/notes/2026-08-20-emblem-shape-catalog.tsv for the complete table."
      - id: rotation
        type: u1
        doc: "Byte 1 of shape_word. CONFIRMED 2026-08-20 as a real, live field (not static) via a controlled edit: byte moved 0x00 (never touched) -> 0x83 (a ~180-degree/\"upside downish\" rotation, human-confirmed) -> 0x01 (after an in-game \"reset to default\", not confirmed bit-exact - the UI reset may not be perfectly precise). Exact byte->degree scale NOT pinned (0-255 wrapping to 0-360 is plausible given the one confirmed sample, not proven)."
      - id: scale
        type: u1
        doc: "Byte 2 of shape_word. CONFIRMED 2026-08-20 via a controlled edit: 0xff (default/untouched value in every capture before this test) -> 0x00 after \"scaled it down\" (a large slider move, human-confirmed) -> back to 0xff after reset. 0xff plausibly = maximum/default size, 0x00 = minimum - exact scale factor not pinned, only the direction and the two endpoints."
      - id: shape_word_unknown_byte3
        type: u1
        doc: "Byte 3 of shape_word. Untouched across every controlled edit performed so far (shape, rotation, scale, and multiple color/opacity changes) - genuinely static in every sample; meaning unknown."
      - id: color_index
        type: u1
        doc: "Byte 0 (top byte) of color_word. CONFIRMED 2026-08-20: the in-game colour picker is a plain 8x8 grid (64 swatches, no names, no per-swatch DC hash resolution found), and color_index = row*8 + column (0-indexed, row-major) - proven at both the top-left (row0,col0 -> index 0, a white swatch) and bottom-right (row7,col7 -> index 63) corners via controlled edits, not just one sample. What each numbered swatch actually LOOKS like (an RGB/palette value) is not resolved - only the grid-position formula is."
      - id: opacity
        type: u1
        doc: "Byte 1 of color_word. CONFIRMED 2026-08-20 via a controlled edit, same pattern as scale: 0xff (default/untouched in every capture before this test) -> 0x00 after setting opacity to \"the other side of the slider\" (human-confirmed, i.e. the transparent/invisible extreme) -> back to 0xff after resetting to \"visible\". 0xff = fully visible, 0x00 = invisible; exact intermediate scale not pinned, only the two endpoints and direction."
      - id: color_word_unknown_bytes
        type: u2
        doc: "Bytes 2-3 of color_word. Untouched across every controlled edit performed so far; meaning unknown."
  loadout_mode:
    doc: "One custom loadout mode = 14 u32 item/skill slots (kLoadoutSize). 0 = default."
    seq:
      - id: slot
        type: u4
        repeat: expr
        repeat-expr: 14
        doc: "14 item/skill slot ids."
