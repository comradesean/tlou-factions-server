meta:
  id: facebook_line
  title: facebook-server line protocol (post-hello plaintext)
  license: CC0-1.0
  encoding: ASCII
doc: |
  Direction: client-to-server (requests), server-to-client ('+'-prefixed replies)

  The custom ND `facebook-server` sub-protocol - maps PSN NpIds <-> Facebook ids
  for friend presence/linking (NOT Facebook OAuth; the Graph API calls are a
  separate HTTP path, server/facebook_graph.py). Member of the 0x11
  sibling-server family: same connect + 88-byte hello carrying "facebook-server"
  + 8-byte 0x22 reply (see 0x11_facebook_server_hello.ksy / _response.ksy), same
  ip:port as ticket-server. AFTER the hello every payload rides the shared
  encrypt-then-MAC 0x33 frame (see docs/protocol/0x11_ticket_server_hello.md,
  server/lib/ticket_cipher.py); confirmed live (frames decrypt tag_ok during a
  working Facebook connect). THIS spec models the DECRYPTED PLAINTEXT lines.
  Requests are single ASCII lines, space-delimited (server parses via
  strip().split(" ")).

  REQUESTS (client->server):
    facebook-set <npid:str> <fbid:u64>            (report own NpId<->fbid map)
    facebook-get-fid  <npid0> <npid1> ...         (resolve NpIds -> fbid/online; <=127/batch)
    facebook-get-npid <fbid0> <fbid1> ...         (resolve fbids -> NpIds;      <=32/batch)
  Format/verb strings: "facebook-set %s %llu" @ file 0xec6f40; "facebook-get-fid"
  @ 0xe6a0d0; "facebook-get-npid " @ 0xec6f58 (trailing space); "facebook-server"
  @ 0xe6a0c0. get-fid/get-npid append their id list after the verb (strncat loop).

  RESPONSES (server->client), '+'-prefixed, '\n'-delimited, NUL-terminated:
    facebook-set:       reply ignored by client (single bounded recv); server acks "+0\n".
    facebook-get-fid:   one "+<fid>\n" per queried NpId; single numeric field
                        (fbid / online flag), 0 = not linked / offline.
    facebook-get-npid:  "+<npid>\n" per RESOLVED fbid (0..N lines, NpId string);
                        no match = no line. WARNING: fabricated NpIds crash the
                        client Presence Thread (sceNpLookup -> jump to 0x30303030
                        access violation) - the server must return real or none.

  Evidence: strings_ascii.txt 0xec6f40 / 0xe6a0d0 / 0xec6f58 / 0xe6a0c0; Ghidra
  FUN_003538c0 (get-fid presence, call 0x00353a68) + FUN_00ac17b0 (get-npid
  resolve, call 0x00ac1828); server/ticket_server.py (facebook-server handling);
  research/notes/2026-08-17-facebook-connect-flow.md.
doc-ref: ../docs/protocol/0x11_sibling_servers_family.md
seq:
  - id: request
    type: str
    terminator: 0
    eos-error: false
    doc: |
      One facebook verb line. Token[0] = verb. facebook-set: token[1]=npid,
      token[2]=fbid (decimal u64). facebook-get-fid: token[1:] = NpIds.
      facebook-get-npid: token[1:] = fbids (decimal). Space-delimited ASCII.
