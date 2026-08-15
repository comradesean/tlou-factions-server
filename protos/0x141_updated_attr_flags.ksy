meta:
  id: updated_attr_flags
  endian: be
  license: CC0-1.0
doc: |
  NetMatchmakingUpdatedAttrFlags - server -> client reply to SetAttrFlags
  (0x140), over the Session Manager connection (port 7314). IS one of the
  11 opcodes the client's own receive-dispatch (FUN_00ad7604) already has a
  case for (unlike 0x140, 0x142, 0x143) - a classic "client sets X, server
  confirms updated X" pair.

  STATUS: 16 bytes, matching SetAttrFlags' own size. tools/session_manager_
  stub.py (SET_ATTR_FLAGS_OPCODE handler) sends this by echoing SetAttrFlags'
  own flags value and room_id straight back - untested against live client
  behavior at time of writing (this reply's actual field requirements have
  not been independently traced from the receive-dispatch decompile).
doc-ref: ../docs/protocol/session_manager_and_matchmaking.md
seq:
  - id: opcode
    type: u4
    doc: "Fixed 0x141 (321 decimal)."
  - id: flags
    size: 4
    doc: "Offset 4:8. Echo of the corresponding SetAttrFlags' own flags field - untested whether the client's receive-dispatch actually requires an exact echo vs. some other value."
  - id: room_id
    size: 8
    doc: "Offset 8:16. Echo of the corresponding SetAttrFlags' own room_id field, matching the general room_id-echo pattern used throughout this protocol."
