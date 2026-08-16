meta:
  id: netmatchmaking_client_hello
  endian: be
  license: CC0-1.0
doc: |
  First message sent on the "Session Manager" connection - a brand-new raw TCP
  connection `g_pSessionManager::Init()` (FUN_00ad71a0 @ 0x00ad71a0) opens
  during NetInit, immediately after the ticket-server handshake completes but
  otherwise completely independent of it (does not read anything from the
  ticket-server connection object). Live-confirmed target in this build's
  redirected setup: same host as ticket-server (192.168.1.100) but port 7314,
  not 7320. Fixed size, 0x30 (48) bytes.

  STATUS: opcode field confirmed via explicit literal store; the remaining
  44 bytes are a verbatim copy of this connection object's own fields at
  +4..+0x24, which are themselves a copy of the local player's SceNpId (see
  doc-ref for the full copy-chain evidence back to sceNpManagerGetNpId).
  Byte order confirmed plain big-endian throughout - see
  research/notes/2026-08-15-byteswap-helper-is-a-noop.md: the call this
  project previously flagged as a possible byte-swap (`FUN_00a0e324`) is a
  confirmed no-op (single `blr` instruction, decompiled and disassembled),
  so nothing on this connection is ever runtime-byte-swapped.

  This opcode namespace (0x12d-0x148 range) is UNRELATED to both
  protos/common/opcodes.ksy's net_event_type enum and the 0x11 ticket-server
  control-channel family - a third, independent opcode space, confirmed via a
  mechanically cross-checked switch statement (see doc-ref).
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed literal 0x12d (301 decimal) = NetMatchmakingClientHello's own numeric ID in the 28-entry NetMatchmaking opcode table. Explicit `li r0,0x12d; li r3,0x12d` then stored, plain big-endian - the call this project previously described as a byte-swap (FUN_00a0e324) is a confirmed no-op, see research/notes/2026-08-15-byteswap-helper-is-a-noop.md."
  - id: unknown_field
    type: u4
    doc: "A second Init()-local u32 (register r25 in the disassembly). Source register's own load site was outside this pass's disassembly window - not traced. Do not assume any particular meaning."
  - id: np_id
    size: 36
    doc: "Verbatim copy of this connection object's own fields at offset +4 through +0x24, which FUN_003557a8 (the caller) populates, just before calling Init(), from the SAME 36-byte NpId-derived block it copies at its own function entry from sceNpManagerGetNpId's output. In other words: this is the local player's own SceNpId (their PSN online ID + Sony's reserved padding), not anything session-manager-specific. Sony's internal SceNpId sub-field layout was not independently re-derived in this pass - treat this as one opaque 36-byte blob to copy through verbatim in a stub implementation, not as something to parse."
  - id: trailing_unconfirmed
    size: 4
    doc: "Final 4 bytes of the 48-byte message. Not captured in this pass's disassembly window (the raw disasm excerpt examined started at the first store into this buffer and covered offsets 0-43; offset 44-47's producing instruction(s) were not located). Genuinely unconfirmed, not a placeholder guess."
