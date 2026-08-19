# How game versions are segregated: the netN.bin config bundle

Question: the server accepts any client. Does anything on the wire identify the
game VERSION, and how did retail keep patch levels apart?

Answer: **nothing in the game protocol carries a version.** The only version
signal that exists anywhere is WHICH CONFIG BUNDLE the client asks the CDN for,
and each build hardcodes its own bundle name.

## No version in the protocol

- `0x12d` ClientHello is 48 bytes, every field tied to a store instruction:
  opcode, a constant zero, the 36-byte SceNpId, 4 bytes of padding. No version,
  no title, no build.
- The 0x11 sibling hellos are opcode, reserved0/1, client_nonce, a 16-byte
  leaked-stack gap, and the service name. No version.
- The ticket (port 7320) carries the PSN service id `UP9000-BCUS98174_00` and a
  ticket-FORMAT version (`21 01` = 2.1), plus serial, issue/expiry, online id
  and `RPCN` as issuer. `_00` is part of the service id, not a patch level - the
  ticket identifies the TITLE, never the build.

This is why a 1.11 client worked against a server developed against 1.00 with no
changes at all: the wire format is version-agnostic.

## The version signal: netN.bin

The EBOOT builds its CDN requests as `http://%s.s3.amazonaws.com` (VMA 0xe6a280)
with the bucket from a small fixed set - `t1.final.dev` (0xe69c10),
`t1.final.prod` (0xe69c20), and the shared-ndlib leftover `u3.beta.prod`
(0xe6a210). The bucket is dev-vs-prod, NOT per patch.

The version discriminator is the config bundle name, and it is a per-build
literal, not a template:

    e6a2b0  net1.bin
    e6a2c0  net5-beta.bin

DECISIVE EVIDENCE: `net10.bin` appears NOWHERE in the 1.00 EBOOT strings, yet a
live client requested `GET /net10.bin.psarc.crypt` with
`Host: t1.final.prod.s3.amazonaws.com`. A build whose EBOOT does not contain the
string cannot have asked for it - so that client was a different build, naming
its own bundle. Both bundles are real and distinct: decrypted they are valid
PSARCs with 7 entries each, `net1.bin` 65141 bytes and `net10.bin` 102391 bytes.

## Why this is the segregation mechanism

The service table the client resolves server host:port from lives INSIDE this
bundle (`cfg+0x5c` for the session manager, `cfg+0x4c` and `cfg+0x58` for
siblings - see 2026-08-18-session-manager-connect-and-reconnect.md). So the
bundle a build fetches determines which servers it talks to. That gives the
operator per-version control without any protocol support: point a version at
different endpoints by editing its bundle, or retire a version entirely by
removing the bundle from the bucket.

## What this means for the server

- **Version gating at the protocol level is impossible.** No message identifies
  the build. A server cannot tell 1.00 from 1.11 from anything it receives on
  7314 or 7320.
- **The HTTP gateway is the only place a version is visible**, as the requested
  bundle name. If version gating is ever wanted, that is the sole hook.
- **We currently serve every version transparently.** The gateway live-fetches
  an unknown bundle from real S3 and caches it, which is precisely why a 1.11
  client worked untouched - it received its own config without anyone noticing.
- **Our own version fragility is separate and narrow.** Two hardcoded client
  addresses, `ROOM_PTR = 0x01383bd8` and `PARTY_ROOM_PTR = 0x01387f58`, are
  compared by equality in two BEHAVIOURAL decisions: the unique-party-id mint
  and the solo-keepalive skip. A build that relocates either global would make
  both silently stop firing, resurfacing the Join Party host-lookup collision
  and the party re-broadcast churn with no error. Only those two values have
  ever been observed (331 frames). `session_manager.py` now emits a loud
  UNKNOWN room_ptr warning for anything else, so a build change cannot regress
  those fixes silently.

## Open follow-up

Diff the service tables inside `net1.bin` and `net10.bin`. If the endpoints
differ, that shows retail really did steer versions at different server pools
rather than merely versioning content - and it would tell us what a 1.11 client
expects to connect to. Both bundles are cached under
`server/data/served_content/` and decrypt with `server/lib/psarc_crypt.py`
(`decrypt_crypt_file` then `parse_psarc`).
