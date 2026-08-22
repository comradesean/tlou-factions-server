meta:
  id: report_line
  title: report-server line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server (request) and server-to-client (response).

  The custom ND `report-server` sub-protocol, a member of the 0x11
  sibling-server family: same connect + 88-byte hello carrying the service name
  "report-server" + 8-byte reply whose byte[0] is 0x22 (see the sibling
  *_server_hello.ksy pair, which is byte-identical across services apart from
  the name), on the same ip:port as ticket-server. AFTER the hello the payload
  is wrapped in the shared encrypt-then-MAC 0x33 frame (magic 0x33, pad, BE u16
  plaintext_len, 16-byte tag, ciphertext - see
  docs/protocol/0x11_ticket_server_hello.md and server/lib/ticket_cipher.py).
  THIS spec models the DECRYPTED PLAINTEXT of the REQUEST; the RESPONSE
  grammar is documented in prose below and, for its one structured case, as
  the `ban_reply_row` type (it is otherwise a variable-token / often-absent
  line, not a fixed struct - see "RESPONSE GRAMMAR, FULLY RESOLVED" below).

  BUILD SCOPE: report-server is 01.11-ONLY. A byte search of both EBOOTs finds
  neither "report-server" nor "is-banned" anywhere in 01.00; both strings exist
  only in 01.11. Every VMA below is therefore an 01.11 address
  (VMA = file offset + 0x10000), unlike the rest of this family's notes which
  are keyed to 01.00.

  DEFINITION / PURPOSE: a player-standing / ban check. Before admitting an
  account to online play the client asks the backend whether that account is
  banned. The administrative reason it exists is enforcement: the ban list
  lives server-side, and the "report" family name indicates this is the same
  backend that receives player reports. The client's own debug line for the
  reply is "ban response: '%s'\n" @ 0xeacde0.

  REQUEST (client->server, one ASCII line), LIVE-CAPTURED:
    is-banned <online_id>\n
  Format string "is-banned %s\n" @ 0xeacdd0 (adjacent to "report-server" @
  0xeacdc0). The '\n' is part of the FORMAT, which is why the captured
  plaintext is exactly 22 bytes for an 11-character id. Sender and parser are
  inline in the big NetInit function, code range 0x36e1fc-0x36e390.

  ALWAYS A SELF-CHECK (corrects the earlier "unobserved" note): nine captured
  connections across five sessions and two accounts in
  server/logs/ticket_server.log, and every one comes from the querying
  console's OWN address naming that console's OWN account - 192.168.1.100 ->
  `is-banned comradesean\n`, 192.168.1.121 -> `is-banned mgnomad2\n`. No frame
  has ever queried a third party.

  RESPONSE (server->client), DERIVED FROM THE BINARY 2026-08-19. Grammar:

    +<decimal int><space-or-newline><name-token>

  The parser, instruction-verified against the 01.11 ELF rather than taken from
  decompiler output:

    0x36e1a8  stw -1,916(g_net)   g_net = 0x13ba5a0; +916 is the ban INDEX and
                                  its default is -1 = NOT BANNED
    0x36e1fc  connect("report-server"); a failed connect skips everything
    0x36e25c  sprintf(buf, "is-banned %s\n", online_id); strlen; send
    0x36e28c  li r5,256           ONE bounded recv of up to 256 bytes...
    0x36e290  bl 0xafacf8         ...poll+recv, returning on the FIRST
                                  successful read; the caller then closes. This
                                  is the heartbeat single-round-trip shape, NOT
                                  the leaderboard NUL-sentinel accumulator, so
                                  the entire reply must arrive in ONE frame.
    0x36e298  cmpwi cr7,r3,0
    0x36e29c  ble 0x36e384        n <= 0                    -> not banned
    0x36e2ac  stb r28,0x388(r9)   buf[n] = 0 - the client NUL-terminates at the
                                  recv LENGTH; it does not require a NUL from
                                  the server
    0x36e2b8  log "ban response: '%s'\n"
    0x36e2c8  lbz r0,0x388(r1)    buf[0]
    0x36e2cc  cmpwi cr7,r0,43     ...must be '+'
    0x36e2d0  bne 0x36e388        not '+'                   -> not banned
    0x36e2dc  addi r3,r1,0x389    tokenising starts at buf+1
    0x36e2ec  bl 0xe72d80         strtok_r(buf+1, " \n")  -> token1
              bl 0xe75d78         strtol(token1, NULL, 10) -> g_net+920
              bl 0xe72d80         strtok_r(NULL, " \n")   -> token2
              loop i over pReportArray: strcmp(token2, entry[i].name); on a
              match store the integer at g_net+920 and the index i at g_net+916

  Delimiter set is " \n" (@ 0xea7e90) - space and newline only.

  THERE IS NO 0/1 BOOLEAN, which is why the earlier "+0 / +1 / +true" guesses
  were all wrong. The account is BANNED iff the reply starts with '+' AND its
  second token strcmp-matches an entry name in pReportArray. Every other path -
  connect failure, n<=0, missing '+', missing token1, missing token2, an
  unmatched name - leaves the index at -1. The whole check is FAIL-OPEN at
  every branch.

  pReportArray is resolved at runtime by data-compiler symbol hash 0xFFAC56F2;
  the identifying literal "pReportArray" is at 0xeb05f0, beside
  "game/net/net-menu.cpp" @ 0xeb0588. Entries are 12 bytes: [+4] = message
  StringId, [+8] = const char* name. Two consumers (0x36c250 and 0x37450c) skip
  everything while g_net+916 < 0, then format the message via 0x3dbdc0 (which
  passes g_net+920 as an argument and reads the entry's StringId) and switch on
  the index: 1 and 2 take different UI paths, 2 also sets g_net+876 = 1.

  STILL UNKNOWN, and both immaterial to answering "not banned" - NOTHING NEEDS
  DOING about either unless this project ever wants to deliberately BAN an
  account, because our empty reply fails the '+' test at 0x36e2cc and the ban
  index at g_net+916 keeps its -1 default, so the check is fail-open no matter
  what the table holds. Tracked as TODO(pReportArray) / TODO(g_net+920) in
  server/ticket_server.py and in docs/OPEN-QUESTIONS.md, where the
  instruction-level 2026-08-19 re-verification of the -1 default and the '+'
  test against the 01.11 ELF is recorded:
    * the literal entry NAMES in pReportArray - they live in the data-compiler
      payload, not the EBOOT, so a static search cannot recover them. Needs a
      DC/.psarc dump or a runtime read. The table's SHAPE is high confidence;
      the strings are unknown.
    * the meaning of the integer at g_net+920. It is formatted into the ban
      message; duration / expiry / days is a guess and is not made here. Its
      format-string pointer is 0x1530d90, which is bss/runtime and unreadable
      statically.

  RESPONSE GRAMMAR, FULLY RESOLVED (2026-08-21 re-verification, addresses
  above re-checked instruction-by-instruction against a fresh objdump of the
  same 01.11 ELF - every citation above matched byte-for-byte, nothing
  revised). Two questions remained after the 2026-08-19 pass and are now
  closed:

  1. "Is there a second report-server request verb (a real player-REPORT,
     as opposed to the ban SELF-check)?" NO - confirmed by exhaustive search,
     not by absence of a lead. `research/tools/eboot_analysis/scan_bl.py`
     against `0xaf9bb4` (the family's shared connect+hello function, the
     same one every 0x11 sibling server uses) finds exactly 12 call sites in
     the whole 01.11 text segment. Reading each site's `r6` argument (the
     service-name string pointer) shows 12 distinct displacements off the
     per-function `r30` anchor - no two call sites load the same service
     name, and only ONE (`0x36e220`, displacement `-30712(r30)`, resolving
     to slot `0x129a3c8`, i.e. the "report-server" string) is report-server's.
     A second grammar would need a second connect call passing
     "report-server" as the service name; there isn't one. The three
     strings adjacent to the "report-server" slot are exactly the three
     already documented above - "report-server" @0xeacdc0, "is-banned %s\n"
     @0xeacdd0, "ban response: '%s'\n" @0xeacde0 - and nothing else sits in
     that neighborhood (`0xeacc00`-`0xeacf00` scanned by hand: sound/analytics
     strings before it, `NetInit Done`/`!m_rBuffer`/commerce-cpp strings
     after). CONCLUSION: the "report" in the service name is a naming
     artifact of the shared backend (the same service that would receive
     player reports server-side, per the family doc), not a second
     client-side grammar. This project's client never sends a report; it
     only ever asks "is-banned <my own online-id>".

  2. "What is the response grammar precisely, token by token?" Already
     correct in the trace above; the ONLY thing worth adding is that the
     parser is strictly POSITIONAL and SINGLE-PASS, not a repeating "one row
     per line" reader like some other family members use for lists: exactly
     one `strtok_r`/`strtol`/`strtok_r`/`strcmp`-loop sequence runs per
     reply, there is no outer loop that re-scans the buffer for a second
     `'+'` line, and any bytes after the second token (including a second
     "+..." row, were the server to send one) are silently ignored. So the
     full grammar, modeled as `ban_reply_row` below, is a single optional
     row, never a list:
       `'+' <ban_index:[0-9]+> (' '|'\n') <name:[^ \n]+> <anything, ignored>`
     - `ban_index` is decimal-only (`strtol(..., 10)`); a malformed digit
       string yields `strtol`'s own default of 0, which is a normal (if
       inert) *matched* index, not a parse failure - only a genuinely empty
       token1 (immediately-adjacent delimiters, e.g. "+ x\n") fails via
       `strtok_r` returning NULL. `name` is compared with plain `strcmp`
       (case-sensitive, exact match) against each `pReportArray` entry's
       name field.
     Nothing in this file is left as an opaque blob: `ban_reply_row` names
     every byte the client's parser actually inspects (sigil, both tokens);
     the "anything, ignored" tail is documented as ignored by ACTUAL PARSER
     BEHAVIOUR (dead past the second `strtok_r`), not left unnamed for lack
     of a static answer.

  LIVE-CAPTURE VALUE: none identified beyond what's already known. This is
  documentation completeness only - the fail-open conclusion (empty body
  never bans) was already correctness-verified on 2026-08-19 and is
  unaffected by anything found in this pass. A capture could only add the
  literal `pReportArray` entry strings (data-compiler payload, not in the
  EBOOT - see TODO(pReportArray) below) or observe a real ban row, neither
  of which this project needs to deliberately trigger.

  SERVER BEHAVIOUR (server/ticket_server.py handle_report / build_report_
  response, implemented 2026-08-19): report-server now has a dedicated handler
  in LINE_SERVICE_HANDLERS and answers "not banned" for every account with an
  EMPTY body plus the family's NUL sentinel, holding the socket until the
  client closes. buf[0] is then 0x00, the '+' test at 0x36e2cc fails, and the
  ban index stays -1. An empty answer is also what the family means elsewhere -
  '+' lines are RESULT ROWS and facebook-get-npid already answers "no matches"
  with an empty response - and it reproduces the payload shape that has been
  live-accepted nine times: before this handler existed these connections fell
  through to the generic ticket path and were answered with a
  ticket_submit_response frame whose plaintext is 16 NULs, after which both
  accounts went on to matchmake and play. A "+0 none" row is deliberately NOT
  emitted: that is a ban row whose name merely happens not to match, and it
  would become a real ban the day "none" collided with a pReportArray entry,
  which cannot be checked from the EBOOT.
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: verb
    type: str
    terminator: 0x20
    eos-error: false
    doc: "The literal ASCII verb \"is-banned\" followed by one space. Live-captured; from the format string \"is-banned %s\\n\" @ 0xeacdd0 (01.11)."
  - id: online_id
    type: str
    terminator: 0x0a
    eos-error: false
    doc: |
      The account being checked: a PSN online-id (account handle), terminated
      by the '\n' that is part of the format string itself. Live-verified
      values "comradesean" and "mgnomad2". Across nine captured frames this is
      always the SENDING console's own account, so the line is a self
      standing-check, never a lookup of a reported opponent.
types:
  ban_reply_row:
    doc: |
      NOT part of `seq` above - this type models the server->client RESPONSE,
      which is a SEPARATE plaintext frame the client reads with one bounded
      256-byte recv (0x36e28c/0x36e290) after sending the request. It is
      OPTIONAL in the strongest sense: an empty reply, a reply not starting
      with '+', or any recv <= 0 byte all skip this structure entirely and
      resolve to "not banned" - see the doc block above ("RESPONSE GRAMMAR,
      FULLY RESOLVED"). Parse this type only when byte[0] of the reply is
      0x2b ('+'); otherwise there is nothing to decode.

      Verified 2026-08-21 against the 01.11 ELF (SHA256
      241e2b1bca43c97431a1aa7acd1b29a20d292bec7263ab8ca318b8a03538e592) with a
      fresh objdump of 0x36e1fc-0x36e390 - every instruction address below
      re-checked, none revised from the 2026-08-19 pass.

      Single-pass, non-repeating: the client's tokenizer runs this sequence
      exactly ONCE per reply (strtok_r, strtol, strtok_r, then a strcmp loop
      over pReportArray). There is no outer loop for multiple rows, unlike
      list-shaped replies elsewhere in this family. Any bytes after
      `name_token` are read into the buffer but never inspected again.
    seq:
      - id: sigil
        contents: [0x2b]
        doc: "Literal '+', tested at 0x36e2cc (`cmpwi cr7,r0,43`). Anything else -> not banned, parsing stops before this type would apply."
      - id: ban_index_token
        type: str
        terminator: 0x20
        eos-error: false
        doc: |
          ASCII decimal digits, tokenized by `strtok_r(buf+1, " \n")` @
          0x36e2ec then converted by `strtol(token1, NULL, 10)` @ 0x36e30c
          (base 10 explicitly - `li r5,10` @ 0x36e300). Modeled here with a
          space terminator (the common-case layout "+<n> <name>\n"); the
          real delimiter set is " \n" (@ 0xea7e90) - either byte ends the
          token, so a reply shaped "+<n>\n<name>" would tokenize identically
          from the client's perspective, even though that never happens for
          an is-banned reply.
          On success this integer is stored to g_net+920 (g_net = 0x13ba5a0)
          - see the still-unknown note on that field's meaning below. An
          empty token (delimiters immediately adjacent, e.g. "+ x") makes
          `strtok_r` return NULL, which aborts the whole match (not
          modeled as a separate field - see the type-level doc).
      - id: name_token
        type: str
        terminator: 0x0a
        eos-error: false
        doc: |
          The ban-reason name, tokenized by a second `strtok_r(NULL, " \n")`
          @ 0x36e324 and matched with plain case-sensitive `strcmp` (@
          0xe778e4) against each `pReportArray[i].name` (entry stride 12
          bytes, name at entry+8; loop @ 0x36e33c-0x36e384). On the first
          matching entry, i is stored to g_net+916 (the ban INDEX, default
          -1 = not banned) alongside the index integer above. The entry
          NAMES themselves are a data-compiler payload, not present in the
          EBOOT - see TODO(pReportArray) in the doc block above.
