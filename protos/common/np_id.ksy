meta:
  id: np_id
  endian: be
  license: CC0-1.0
doc: |
  Sony's public 36-byte `SceNpId` structure, as it appears verbatim on the
  wire in several Session Manager messages (netmatchmaking_client_hello,
  0x131 Member roster entries, 0x132 RoomJoined). The FIRST 16 BYTES are the
  player's online-id handle and are the confirmed dedupe / signaling key:
  `_opd_FUN_00e459bc` compares them as a NUL-terminated string (word-wise
  0x7f7f7f7f NUL scan @ 0xe459dc-0xe45a34 then a byte tail), and the
  non-local member-registration branch feeds the same 16 bytes to the NP
  signaling-connection resolve (0x00ad34a4).

  The remaining 20 bytes follow Sony's documented SceNpId layout
  (SceNpOnlineId's terminator+dummy, then opt[8], reserved[8]). They are
  copied through verbatim by the client; their individual readers past the
  16-byte handle are not traced, so the sub-field names below are structural
  (from the public struct) rather than behaviourally confirmed - do not rely
  on opt/reserved carrying game-specific meaning without further evidence.
seq:
  - id: online_id
    type: strz
    size: 16
    encoding: ASCII
    doc: "SceNpOnlineId.data - the ASCII handle (e.g. \"comradesean\"), NUL-padded within 16 bytes. The dedupe / signaling key."
  - id: online_id_term
    size: 1
    doc: "SceNpOnlineId.term - the handle's NUL terminator byte."
  - id: online_id_dummy
    size: 3
    doc: "SceNpOnlineId.dummy[3] - Sony reserved padding."
  - id: opt
    size: 8
    doc: "SceNpId.opt[8] - Sony's opaque option bytes; copied through verbatim, readers past the handle untraced."
  - id: reserved
    size: 8
    doc: "SceNpId.reserved[8] - Sony reserved; copied through verbatim, readers past the handle untraced."
