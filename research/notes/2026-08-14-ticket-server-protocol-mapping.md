# Ticket-server handshake mapped: 4 messages, one wire format each

Follow-up to `research/notes/ticket-server-first-capture.md`, which had one
raw 88-byte capture and no idea what any of it meant beyond "opcode maybe 0,
service name string visible." This session traced the client-side code that
builds, sends, and validates that packet - and found it's actually one leg
of a 4-message handshake on a single TCP connection, not a standalone
message. Full field-by-field evidence and the four `.ksy` schemas are in
`docs/protocol/0x11_ticket_server_hello.md` / `protos/0x11_ticket_server_*.ksy`;
this note is the narrative summary.

## Headline results

1. **The 88-byte packet is fully explained.** It's built by `FUN_00acc424`
   (`0x00acc424`) right after a low-level TCP connect succeeds. Every byte is
   accounted for:
   - `[0]` = `0x11` (opcode, literal, confirmed via `li r0,17; stb`)
   - `[1]` = `0x00` (reserved, literal)
   - `[2:4]` = `0x0000` (reserved, literal)
   - `[4:8]` = a 30-bit output of the client's own local PRNG (`FUN_00e408d8`),
     also cached in the connection object at `+0x4c`
   - `[8:24]` = **proven uninitialized stack memory** - a genuine
     memory-disclosure bug in the client, not a protocol field
   - `[24:88]` = a 64-byte buffer holding the NUL-terminated service name
     (`"ticket-server"`), copied via a `strcpy`-equivalent with **no
     zero-fill**, so bytes after the NUL are more uninitialized garbage
2. **This directly resolves the "pointer-looking values" question from the
   original capture note and from this session's briefing.** They are not
   session tokens, not derived from the RPCN ticket, not encrypted/HMAC'd
   data - they're leftover stack contents, confirmed by the simple fact that
   no instruction anywhere in the sending function's disassembly writes to
   that stack range before it gets copied into the packet. Trying the known
   `.crypt` Blowfish/HMAC-SHA1 keys against these bytes (suggested this
   session) is therefore moot - there's no derived data there to key-match
   against.
3. **The client expects an 8-byte response and validates exactly one byte of
   it**: byte 0 must equal `0x22` (`'"'`) or the client aborts the connection
   immediately. This is *why* every prior capture attempt failed past this
   point - our stand-in TCP catcher never sent back anything matching this
   shape, so the real client always bailed right here, producing the
   previously-mysterious `ERROR NET INIT ffffffff` / connection-reset
   symptom. That symptom is now fully explained, not just worked around.
4. **This is not the whole handshake - there's more, on the same
   connection.** If the 8-byte response passes, the client immediately sends
   a second message: the RPCN-issued NP ticket (248 bytes, already confirmed
   working against RPCN), prefixed with its own 2-byte big-endian length.
   Then it expects a 16-byte response before closing the connection and
   continuing NetInit. This was previously completely unknown - the original
   capture note only saw the first message because the connection died
   before the client ever got here.
5. **RPCN has no equivalent of this protocol** - grepped `backend/rpcn/` for
   `ticket-server`, `7320`, and all four sibling service names found this
   session; zero matches. This really is new server-side surface we need to
   build from scratch, not something to route into an existing RPCN
   endpoint.
6. **Likely a shared pattern across several backend services**, not just
   this one: `FUN_00acc424` takes the service name as a plain argument, and
   the EBOOT's string table has siblings - `single-player-server`,
   `facebook-server`, `heartbeat-server`, `invite-server`,
   `leaderboard-server` - none individually confirmed this session, but the
   generic implementation makes it a reasonable bet that at least messages A
   and B of this handshake generalize to all of them.

## What's still open

- **Message B's `session_token` (response bytes 4-7, stored at `conn+0x50`)
  and message D's entire 16-byte payload** - both confirmed to exist and be
  read/stored by the client, but this pass didn't trace their downstream
  consumer inside the ~2500-line `FUN_003557a8` orchestrator. Needs either a
  narrower Ghidra decompile pass or a live RPCS3 debugger session (the same
  technique that cracked the `.crypt` HMAC key in
  `2026-08-14-repack-rejection-investigation.md` would work here too).
- **Whether `client_nonce` (message A) needs to be echoed back by the
  server** in any form - not confirmed either way.
- **The sibling service names** (`heartbeat-server` etc.) - not individually
  decompiled; the "shared handshake" claim above is a hypothesis, not yet
  confirmed against a second call site.

## Next steps, prioritized

1. Trace `conn+0x50` and the message-D consumer (see above) - the last real
   gap in a *confirmed* schema for this handshake.
2. Build a minimal fake ticket-server that speaks messages A-D per the
   confirmed schemas and test it live against RPCS3 + our RPCN fork - this
   is the first real chance to see client behavior *past* this handshake
   since the investigation started.
3. Confirm the shared-handshake hypothesis against one sibling service
   (cheap: one more Ghidra call-site decompile).

## Deliverables from this session

- `protos/0x11_ticket_server_hello.ksy` - message A, confirmed high
  confidence, compiles clean (`ksc --outdir ... --target python`).
- `protos/0x11_ticket_server_hello_response.ksy` - message B, structure
  confirmed / content partial, compiles clean.
- `protos/0x11_ticket_server_ticket_submit.ksy` - message C, confirmed high
  confidence, compiles clean.
- `protos/0x11_ticket_server_ticket_submit_response.ksy` - message D, size
  only confirmed, compiles clean.
- `docs/protocol/0x11_ticket_server_hello.md` - full evidence log (decompile
  excerpts, raw disassembly, confidence table) for all four messages.
- `docs/protocol/README.md` - added a table for this opcode family, noted
  explicitly as a separate namespace from `net_event_type`.
- Ghidra decompile dumps backing this note:
  `research/ghidra/socket_wrapper_family_decomp.txt` (the connect/init/close
  helper family: `FUN_00acc668`, `FUN_00acc424`, `FUN_00acd5f8`,
  `FUN_00acd568`, `FUN_00acbad0`) and
  `research/ghidra/response_and_helpers_decomp.txt` (the lower-level
  send/recv/PRNG/strcpy/strlen helpers: `FUN_00acb93c`, `FUN_00acbd98`,
  `FUN_00e408d8`, `FUN_00e45b10`, `FUN_00e40ad8`, `FUN_00acb6fc`,
  `FUN_00acbb90`, `FUN_00acbf90`).
