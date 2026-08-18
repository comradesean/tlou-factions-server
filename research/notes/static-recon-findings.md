# Static Recon Findings (initial pass)

Source: `strings -n 6 -t x EBOOT.elf` (40,923 lines, `research/strings/strings_ascii.txt`) and a full `powerpc64-linux-gnu-objdump -d` (144MB, gitignored — regenerate via the command in `docs/tooling.md` if needed). UTF-16BE pass (`strings_utf16be.txt`) came back with only 61 lines, nothing relevant (checked, not worth a separate writeup).

## Source file map (`game/net/`)

36 `.cpp` files under `game/net/` survive as assert/debug strings, giving a near-complete map of the netcode module without any disassembly:

`custom-player-manager.cpp`, `flow.cpp`, `in-game-commerce.cpp`, `lobby-flow.cpp`, `net-anim-command-generator.cpp`, `net-booster-manager.cpp`, `net-buff-manager.cpp`, `net-character-animate.cpp`, `net-character-death.cpp`, `net-character-event-handler.cpp`, `net-character-fire-animation.cpp`, `net-character-reaction.cpp`, `net-character.cpp`, `net-clan-manager.cpp`, `net-clip-pages.cpp`, `net-email.cpp`, `net-event.cpp`, `net-event/net-event-breakable.cpp`, `net-event/net-event-carry-object.cpp`, `net-event/net-event-character-move.cpp`, `net-event/net-event-npc.cpp`, `net-event/net-event-pickup.cpp`, `net-event/net-event-player.cpp`, `net-event/net-event-weapon.cpp`, `net-game-manager.cpp`, `net-info.cpp`, `net-interactable-manager.cpp`, `net-invite.cpp`, `net-late-join.cpp`, `net-matchmaking.cpp`, `net-menu-host.cpp`, `net-menu.cpp`, `net-np-message.cpp`, `net-player-data.cpp`, `net-player-tracker.cpp`, `net-script-funcs.cpp`, `net-snapshot.cpp`, `net-stats.cpp`, `net-tus-variable.cpp`, `net.cpp`, `task-manager-online.cpp`.

Also relevant, under `ndlib/` (engine-level, not game-specific): `ndlib/net/net-phase-snapshot.cpp`, `ndlib/net/net-simple-snapshot.cpp`, `ndlib/util/bitstream.cpp`.

Full address-range dump of this region of the string table (offsets ~0xe69000-0xe71000): `research/notes/net_module_string_range.txt` (972 lines).

## Matchmaking/session layer: confirmed to be Sony's sceNpMatching2

Strings directly reference `sceNpMatching2CreateJoinRoom`, `sceNpMatching2JoinRoom`, `sceNpMatching2GetEventData`, alongside `sceNpManagerRegisterCallback`, `sceNpManagerRequestTicket2`, `sceNpBasicAddFriend`, `sceNpBasicGetFriendPresenceByNpId`, etc. See `docs/glossary.md` for what this implies (RPCN already reimplements this layer — see `research/prior-art.md`).

## Custom transport layer: sequenced/acked, bit-packed

- `"notify->packetSequenceNumber == m_highestAckedSequence + i + 1"` (offset `0xec7d40`, `ndlib/net/net-phase-snapshot.cpp`) — confirms a reliable sequence-number/ack scheme above whatever raw socket carries gameplay traffic. This is the strongest lead for `protos/common/packet_header.ksy`'s `sequence_number` field, though its exact wire width/position is still a guess.
- `ndlib/util/bitstream.cpp` — a custom bitstream serializer exists, meaning fields in `NetEvent*` payloads are plausibly bit-packed rather than byte-aligned. Kaitai supports bit-sized fields (`type: b3` etc.) natively, so this is representable once confirmed — just don't assume byte alignment when eventually parsing real capture bytes.
- `"The buffer passed in to read the string from the packet is too small to fit the string in the packet"` — confirms a bounds-checked packet-reader abstraction with (at least) a length-prefixed string type.

## Opcode dispatch: bounds-checked, but numeric range not yet recovered

Three format strings strongly suggest a central dispatch with bounds checking:
- `"%p:%3u - UNKNOWN OPCODE"` (offset `0xeb9368`)
- `"%s(%d) : Out of range Opcode type of 0x%X."` (offset `0xef4ca8`)
- `"%s(%d) : Unimplemented Opcode type of 0x%X."` (offset `0xef4cd8`)

Attempted to find what code references these three string addresses via `grep` over the full objdump text dump — **came up empty**. This is expected, not a dead end: PS3/PPC64 code loads string addresses via multi-instruction TOC-relative (`r2`-based) or `lis`+`ori` sequences that never appear as a single flat address literal in a linear disassembly, so grepping for the hex offset directly doesn't work. Recovering the actual dispatch function (and therefore the real numeric opcode range) needs either Ghidra's decompiler (which resolves TOC-relative addressing automatically — see `docs/ghidra-setup.md`) or a scripted Capstone dataflow pass. Flagged as the top target for the next Ghidra session.

## NetEvent* / NET_SM_* catalogs

116 `NetEvent*` names and 38 `NET_SM_*` names extracted and catalogued — catalogued in `protos/common/opcodes.ksy` and `protos/pending/net_sm_states_catalog.md`. Raw lists: `research/notes/netevent_names.txt`, `research/notes/net_sm_states.txt`.

## Non-game-server hosts found (patch/config/analytics infra, not gameplay servers)

`t1.patch.s3.amazonaws.com`, `t1.campaign.config.s3.amazonaws.com`, `compile19-dog:9001` / `compile20-dog.naughtydog.com` / `mysql-dog.naughtydog.com` / `postal-dog.naughtydog.com` (internal Naughty Dog build infra, dead ends), `graph.facebook.com`/`api.facebook.com` (social sharing feature), `gdata.youtube.com` (video upload feature), `www.google-analytics.com`. None of these are the actual multiplayer game server — no distinct gameplay-server hostname/IP turned up in the ASCII string pass. It may be resolved dynamically (e.g. via `sceNpMatching2` room data, or a config fetched from one of the S3 config endpoints above) rather than hardcoded — worth checking `t1.campaign.config.s3.amazonaws.com/campaign.config.txt.crypt` if it's ever reachable/archived, since it's encrypted config that could plausibly carry environment-specific server info. No IPs found beyond loopback/private-range placeholders (`127.0.0.1`, `1.2.3.0`, `150.0.0.60` — none look like real production addresses).

## objdump quality note

11,176 of ~3.7M disassembled lines (~0.3%) came back as unrecognized (`.long`/bad). Consistent with the documented Ghidra/binutils gap around Cell-specific Altivec instructions (`lvlx` etc.) — see `docs/ghidra-setup.md`.
