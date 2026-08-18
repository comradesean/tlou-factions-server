meta:
  id: profile_21
  endian: be
  license: CC0-1.0
doc: |
  Direction: client<->server (S3 GET/PUT of profiles/<online_id>/profile.21).

  The ~0x5028-byte NetPlayerData progression record, version 21. This .ksy
  models the DECRYPTED+DECOMPRESSED plaintext. On the wire the file is
  LZF( [u32 ver][u32 enc_len][ Blowfish-ECB( payload || pad || HMAC ) ][8] );
  the container crypto is solved in server/lib/psarc_crypt.py and is out of
  scope for this schema.

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
      title_badge:
        pos: 0x02F8
        type: u4
        doc: "P+0x0300. Low byte = lobby title/badge index (blob[9] source). 0 in both samples."
      member_blob_word:
        pos: 0x064C
        type: u4
        doc: "P+0x0654. Copied verbatim into the member card (member_data card_stat_2/card_stat_3). 0 in both samples."
      total_matches:
        pos: 0x0A14
        type: u4
        doc: "P+0x0A1C. Incremented every match. Cross-checks: == matches_mode_a + matches_mode_b in both samples (11 / 7)."
      total_wins_result3:
        pos: 0x0A18
        type: u4
        doc: "P+0x0A20. Incremented when match result == 3 (win). 10 / 7 in the samples."
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
      pop_highwater_a:
        pos: 0x1BD8
        type: u4
        doc: "P+0x1BE0. Population high-water (written at OnMatchEnd). 81 / 33; equals pop_highwater_menu."
      clan_state:
        pos: 0x1BE8
        type: u4
        doc: "P+0x1BF0. Clan / faction state enum (== 2 in both samples)."
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
      unknown_1e2c:
        pos: 0x1E24
        type: u4
        doc: "P+0x1E2C. Flag (1/0), not pinned to a decompile writer. 1 / 0."
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
      unknown_1e3c:
        pos: 0x1E34
        type: u4
        doc: "P+0x1E3C. Nonzero only in mgnomad2 (0xE0C2); not pinned to a writer."
      flag_1e40:
        pos: 0x1E38
        type: u4
        doc: "P+0x1E40. == 1 in both samples; unresolved flag."
      journeys_completed:
        pos: 0x1E3C
        type: u4
        doc: "P+0x1E44. Incremented per journey at OnMatchEnd. Feeds member_data.rank_value (journeys*1000 + weeks). 0 / 0."
      healthy_count:
        pos: 0x1E40
        type: u4
        doc: "P+0x1E48. Per-player count (menu-written), likely healthy survivors. 4 / 6."
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
  loadout_mode:
    doc: "One custom loadout mode = 14 u32 item/skill slots (kLoadoutSize). 0 = default."
    seq:
      - id: slot
        type: u4
        repeat: expr
        repeat-expr: 14
        doc: "14 item/skill slot ids."
