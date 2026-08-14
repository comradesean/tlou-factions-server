meta:
  id: opcodes
  license: CC0-1.0
doc: |
  Opcode id -> name enum. STATUS: empty / pending.

  Static string recon (this session) recovered opcode *names* but not numeric
  IDs or dispatch field width - see protos/pending/netevent_catalog.md (116
  NetEvent* names, very likely the real gameplay opcode set) and
  protos/pending/net_sm_states_catalog.md (38 NET_SM_* state names, probably
  client-side match-flow states rather than wire opcodes).

  Do not add entries here from a guess. An entry only belongs in this enum
  once its numeric id is confirmed via decompiled dispatch logic (see
  docs/ghidra-setup.md) and/or direct evidence from a live capture.
doc-ref: ../../docs/protocol/README.md
enums:
  net_event_type: {}
