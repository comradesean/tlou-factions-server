meta:
  id: netmatchmaking_client_hello
  endian: be
  license: CC0-1.0
  imports:
    - common/np_id
doc: |
  Direction: client-to-server

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
  - id: reserved_4
    type: u4
    doc: "Offset 4:8. Constant 0. RESOLVED 2026-08-18: register r25 is defined only by `li r25,0` @ 0xad7270 before its single buffer store `stw r25,156(r1)` @ 0xad74ac (buffer base r1+0x98 = 152, so 156 = wire 4); the same r25 also drives the cursor reset `*(param_1+0x24054)=0`. Value known, purpose unknown - do not attribute meaning."
  - id: np_id
    type: np_id
    doc: "Offset 8:44. The local player's own 36-byte SceNpId (see common/np_id.ksy), a verbatim copy of this connection object's fields at +4..+0x24, which FUN_003557a8 populates from sceNpManagerGetNpId's output before calling Init(). The first 16 bytes are the online-id handle (visible as \"comradesean\" in captures); the rest is the SceNpId term/opt/reserved tail."
  - id: pad_2c
    size: 4
    doc: "Offset 44:48. Trailing padding. DEFINITION: the unused final 4 bytes of the 48-byte hello. REASON: the builder FUN_00ad71a0's buffer stores are exactly 152/156/160-192(r1) (wire 0..43); there is no store to 196(r1) (wire 44), so it is left as stack and just fills the message to 48 bytes. Send 0. (Was `uninitialised_2c` / earlier `trailing_unconfirmed`.)"
