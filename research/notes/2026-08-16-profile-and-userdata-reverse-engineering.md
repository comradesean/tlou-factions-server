# `profile.21` and `userdata/<npid>.txt.crypt`: the HTTP player-persistence layer

Reverse-engineering pass on the two S3 objects the client GETs on a loop
(`captures/*.log`, `catch_http-run.log`): what is in them, which direction
they flow, and what crypto wraps them. Headline results, all evidence-first:

1. **`profile.21` is the entire player-progression record** — a fixed
   **0x5028-byte (20,520)** in-memory struct (`NetPlayerData::m_tusData`),
   Blowfish-encrypted + HMAC-SHA1-signed with **the two keys this project
   already solved**, then **LZF**-compressed. Rank/XP, all four custom
   loadouts, the clan/journey counters and the clan survivor name seeds all
   live in it.
2. **It is READ-WRITE.** The client has a full AWS S3 client (GET/PUT/DELETE,
   SigV2) with **hardcoded AWS credentials in the EBOOT**, and a dedicated
   `NetPlayerData Publish Thread` that S3-**PUT**s the record after every
   progression change (17 call sites). We have never seen a PUT for one
   reason only: **PUT uses path-style addressing against the bare host
   `s3.amazonaws.com`, which is not in RPCS3's IP-swap list.** Adding it
   turns this whole problem from "generate a profile from scratch" into
   "round-trip the client's own uploads".
3. **`userdata/<npid>.txt.crypt` is not progression data.** It rides the
   generic content-delivery downloader alongside `build/<user>/actor%i` and
   `build/<user>/text1/%i.networking` developer-override assets, and its
   decrypted body is handed to a generic text-config loader. Same
   `.crypt` = same Blowfish container already solved in
   `2026-08-14-blowfish-psarc-solve.md`.

Address convention throughout: **VMA = file offset + 0x10000** (both LOAD
segments). Every address below was read off raw
`powerpc64-linux-gnu-objdump` disassembly and/or a Ghidra decompile that was
then cross-checked against the disassembly; the decompile-only claims are
flagged. Ghidra dumps from this pass:
`research/ghidra/profile_userdata_decomp.txt`, `profile_batch2.txt` …
`profile_batch8.txt`.

---

## 1. The owning module: `game/net/net-player-data.cpp`

String cluster at `0x00e7df40`-`0x00e7e1ff` (dumped verbatim):

```
0x00e7df40  game/net/net-player-data.cpp
0x00e7df60  %s/lan-profiles-%d
0x00e7df78  NetPlayerData
0x00e7df88  GetNpId(&npId)
0x00e7df98  profiles/%s/profile.%d
0x00e7dfb0  %s/lan-profiles-%d/%s
0x00e7dfc8  len == sizeof(m_tusData)
0x00e7dfe8  sizeof(NetPlayerData) <= Memory::GetSize(ALLOCATION_NET_PLAYER_DATA)
0x00e7e030  %s/lan-profiles-%d/
0x00e7e048  dataName >= 0 && dataName < kLoadoutSize
0x00e7e078  loadoutNum >= 0 && loadoutNum < kNumCustomLoadoutsPerMode
0x00e7e0b8  pFirstNames
0x00e7e0c8  pLastNames
0x00e7e0d8  NetPlayerData Publish Thread
0x00e7e0f8  sys_ppu_thread_create(&m_threadId, _RunPublishThread, (uint64_t)this, 1001, 20384, 0, "NetPlayerData Publish Thread")
0x00e7e170  NetPlayerData Connect Thread
0x00e7e190  sys_ppu_thread_create(&m_threadId, _RunConnectThread, (uint64_t)this, 1001, 20384, 0, "NetPlayerData Connect Thread")
```

`"TUS"` here is Naughty Dog's own name for this record, **not** Sony's
`sceNpTus` — consistent with `clan-tus-commerce-findings.md`, which proved
no `sceNpTus*` NID is imported anywhere. It is ND's own S3-backed storage.

### The `NetPlayerData` singleton's layout (offsets used in code)

| offset | meaning | evidence |
|---|---|---|
| `+0x00C8` | **live** `m_tusData` (0x5028 bytes) — what all gameplay code reads | `FUN_003cb89c` returns `this+200`; `FUN_003cc824` memcpys `0x5028` into it |
| `+0x0498` | publish counter, `++` on every Publish | `0x3cd0f4`-ish, `FUN_003cd0ac` |
| `+0x50F0` | S3 staging copy of `m_tusData` | `FUN_003cc128` / `FUN_003cc5c8` |
| `+0xA118` | LAN/local-file staging copy | `FUN_003cc354` / `FUN_003cc75c` |
| `+0xF140` | publish state (0 = ok, 1 = in-flight, 2 = failed) | `FUN_003cd0ac`, `FUN_003cc438` |
| `+0xF144` | load state (1 = connecting, 2 = defaults, 3 = loaded) | `FUN_003cd388`, `FUN_003cc824` |
| `+0xF148` | worker `sys_ppu_thread_t` | both thread creators |
| `+0xF150` | "publish pending" flag | `FUN_003cd0ac` |
| `+0xF154` | local-player / mode index | `FUN_003cbe3c`, `FUN_003ccb88` |

---

## 2. `m_tusData` — the 0x5028-byte container

`FUN_003cb818` (the "reset to defaults" initialiser, decompiled) is the
cleanest statement of the layout:

```c
void FUN_003cb818(u8 *rec) {
    rec[3] = 0x15;  rec[0] = rec[1] = rec[2] = 0;   // BE u32 version = 21
    rec[4] = rec[5] = rec[6] = rec[7] = 0;          // BE u32 encrypted length = 0
    memset(rec + 8,      0, 0x5000);                // payload
    memset(rec + 0x5008, 0, 0x20);                  // signature + slack
}
```

| offset | size | field |
|---|---|---|
| `0x0000` | 4 | **BE u32 schema version = 21** — this is the `21` in `profile.21` |
| `0x0004` | 4 | **BE u32 encrypted-blob length**, always `0x5018` in practice |
| `0x0008` | `0x5018` | Blowfish-ECB ciphertext (see §3) |
| `0x5020` | 8 | unused slack |

Confirmations:

* `FUN_003cc5c8` (download) asserts `len == sizeof(m_tusData)` after
  decompression and requires `*(u32*)(rec) == 0x15` before accepting the
  record — otherwise it calls `FUN_003cb818` and the player starts fresh.
  Both are on-screen-verifiable behaviours.
* `FUN_003cc128` (upload) compresses **exactly `0x5028` (`li r4,20520`
  @ `0x3cc208`)** bytes from `this+0x50F0` (`addi r3,r26,20720` @
  `0x3cc1f4`).

---

## 3. Crypto — SAME keys as `2026-08-14-blowfish-psarc-solve.md`, nothing new

**No new cipher had to be derived.** The record is protected by
`ndlib/net/net-drm.cpp`, which uses the identical key pair already solved
for `net1.bin.psarc.crypt`.

Both keys are literally adjacent pointers in one struct at `0x01243A60`
(verified by dereferencing):

```
0x01243A60 -> 0x00ED7DD0  "xM;6X%/p^L/:}-5QoA+K8:F*M!~sb(WK<E%6sW_un0a[7Gm6,()kHoXY+yI/s;Ba"   (64-byte HMAC-SHA1 key)
0x01243A64 -> 0x00E5A748  "(SH[@2>r62%5+QKpy|g6"                                                (Blowfish key)
```

`0x00ED7DD0` sits inside the `net-drm.cpp` string block
(`0x00ED7DB0 = "ndlib/net/net-drm.cpp"`, `0x00ED7DA0 = "len >= 20"`,
`0x00ED7DC8 = "len > 0"`). The same Blowfish key pointer also appears at
`0x01253CFC`, in the raw-HTTP downloader's table — i.e. **one key serves the
`.crypt` content-delivery files, the PS3 save-games, and this profile
record**.

### Sign+encrypt: `FUN_00ace0f0(data, len)` — called as `FUN_00ace0f0(rec+8, 0x5000)`

```
total = (len + 0x1b) & ~7                              // = round_up(len + 20, 8) = 0x5018
memset(data + len, 0, total - len)                     // zero the pad + digest area
key = *(char**)0x01243A60                              // net-drm HMAC key
FUN_00ac2680(key, strlen(key), data, total - 0x14, dg) // HMAC-SHA1 over data[0 .. total-0x14)
memcpy(data + total - 0x14, dg, 0x14)                  // digest at data+0x5004
for (i = 0; i < ((len + 0x1b) >> 3); i++)              // 0xA03 = 2563 blocks = 0x5018 bytes
    blowfish_encrypt_block(ctx, &data[i*8], &data[i*8+4]);
return total;                                          // stored as the BE u32 at rec+4
```

`FUN_003cc938` is the thin wrapper that calls it and writes the returned
`0x5018` into `rec[4..7]` as a big-endian u32 (byte-by-byte stores at
`0x3cc95c`-`0x3cc974`).

### Verify+decrypt: `FUN_00acdf40(data, len)` — called from `FUN_003cc534(rec)`

```
if (len < 0x14) assert("len >= 20", net-drm.cpp);
for (i = 0; i < (len >> 3); i++)
    blowfish_decrypt_block(ctx, &data[i*8], &data[i*8+4]);
FUN_00ac2680(key, strlen(key), data, len - 0x14, dg);
return memcmp(dg, data + len - 0x14, 0x14) == 0 ? len - 0x14 : -1;
```

`FUN_003cc534` reads the length as an unaligned BE u32 from `rec[4..7]`,
calls the above on `rec+8`, and on **any** failure calls `FUN_003cb818` —
i.e. a bad HMAC silently wipes the player's profile back to defaults rather
than erroring. That is the single most important failure mode to get right
when generating a profile.

**Plaintext layout inside the encrypted blob** (`P` = `rec`, so payload byte
`k` is at `P + 8 + k`):

```
P+0x0008 .. P+0x5007   0x5000 bytes of game data
P+0x5008 .. P+0x500B   4 zero pad bytes
P+0x500C .. P+0x501F   20-byte HMAC-SHA1 over the 0x5004 bytes before it
```

**Blowfish details are unchanged from the psarc solve**: standard Feistel
core, key schedule seeded from the custom 4168-byte `BLOWFISH_KEY_DATA`
table (`tools/blowfish_key_data.py`), ECB, no IV, trailing partial block
untouched. `tools/psarc_crypt.py`'s `blowfish_encrypt()` /
`blowfish_decrypt()` work on this data **unmodified** — `0x5018` is a
multiple of 8 so the partial-block case never arises.

### Compression: LZF (liblzf), not zlib

`FUN_00923304` (compress) / `FUN_00923888` (decompress) are a byte-exact
liblzf implementation — 13-bit window (`0x2000`), 3-byte minimum match,
16384-entry hash table allocated by `FUN_00915a30(0x10000, ..., 8)`.
Decoder, ported straight from `FUN_00923888`'s disassembly:

```
ctrl = *src++
if ctrl < 32:                     # literal run
    copy ctrl+1 bytes src -> dst
else:                             # back-reference
    len = ctrl >> 5
    if len == 7: len = *src++ + 7
    ref = dst_cur - ((ctrl & 0x1f) << 8) - 1 - *src++
    copy len+2 bytes from ref
```

**A literal-only stream is legal and trivially generated** (control byte
`n-1` followed by `n <= 32` literal bytes), which is all a server needs.
0x5028 bytes encodes to 21,162 bytes — comfortably inside the client's
0x8000 download buffer.

### The `profile.21` file body, end to end

```
LZF( [BE u32 21][BE u32 0x5018][ Blowfish( plain[0x5000] || 0x00*4 || HMAC-SHA1 ) ][8 zero bytes] )
```

Validated by a full round-trip in Python against a faithful port of
`FUN_00923888` + `FUN_00acdf40`: LZF decode is byte-exact, decrypt recovers
the plaintext, and the HMAC verifies. (Self-consistent; **not yet confirmed
live against the game** — see §8.)

---

## 4. READ **and** WRITE: the S3 client, its credentials, and why we never saw a PUT

### The AWS credentials are in the EBOOT, in the clear

```
0x00E7CFF0  [REDACTED-AWS-SECRET-KEY]     (secret access key)
0x00E7D020  [REDACTED-AWS-ACCESS-KEY-ID]                          (access key id)
```
Pointer pair at `0x012241A0` / `0x012241A4`; both sit in the
`game/net/net-info.cpp` string block. Long revoked — probing the real bucket
today returns `403` for both objects — but they prove the client is a
**writing** S3 client, not a read-only downloader.

### `FUN_00ac60a0` — the SigV2 request builder (`ndlib/net/http.cpp`)

Method selector is `obj[1]` (`obj+4`). Templates resolved from the r2→anchor
chain:

| slot | string |
|---|---|
| `0x01297244` | `%s.s3.amazonaws.com` |
| `0x01297248` | `/%s` |
| `0x0129724C` | `GET\n\n\n%s\n/%s/%s` |
| `0x01297250` | `s3.amazonaws.com` |
| `0x01297254` | `/%s/%s` |
| `0x01297258` | `PUT\n\n%s\n%s\n/%s/%s` |
| `0x0129725C` | `DELETE\n\n\n%s\n/%s/%s` |
| `0x01297260` | `AWS %s:%s` |

* **method 1 = GET**: `Host = "<bucket>.s3.amazonaws.com"`, path `/<key>` —
  **virtual-hosted style**. Exactly the
  `t1.final.prod.s3.amazonaws.com/profiles/comradesean/profile.21` we see.
* **method 4 = PUT**: `Host = "s3.amazonaws.com"` (literal), path
  `/<bucket>/<key>` — **path style**. StringToSign gains a content-type
  (from `obj->vtable[0x10]()`) and a Content-MD5 slot.
* **method 5 = DELETE**.

Signature is `FUN_00ac43a0` → HMAC-SHA1(secret, StringToSign) → base64
(`FUN_0001fd54`), emitted as `Authorization: AWS <keyid>:<sig>`, with the
date from `sceNpManagerGetNetworkTime` + `cellRtcFormatRfc2822`.

Verb wrappers, confirmed from raw disassembly:

```
00ac6308:  li r0,4 ; stw r0,116(r1)  ->  PUT   (also stores data ptr @+4992, length @+4988)
00ac6378:  li r0,1 ; stw r0,116(r1)  ->  GET
```

### The two worker threads

**`FUN_003cc824` = `_RunConnectThread`** (started by `FUN_003cd388`):
retries `FUN_003cc5c8` up to 5×, then
`memcpy(this+200, this+0x50F0, 0x5028)` and sets load state 3.

**`FUN_003cc5c8`** — the download:
```
sprintf(path, "profiles/%s/profile.%d", online_id, 21)     // li r6,21 @ 0x3cc198
n = FUN_00ac6378(bucket, path, scratch, 0x8000)            // S3 GET
if (n > 0) {
    if (FUN_00923888(scratch, n, this+0x50F0, 0x5028) != 0x5028) assert("len == sizeof(m_tusData)");
    if (*(u32*)(this+0x50F0) == 0x15) { FUN_003cc534(this+0x50F0); return 0; }
}
... 3 attempts ...
FUN_003cb818(this+0x50F0);      // defaults
```

**`FUN_003cc438` = `_RunPublishThread`** (started by `FUN_003cd0ac`):
calls `FUN_003cc128` (S3) then `FUN_003cc354` (local mirror).

**`FUN_003cc128`** — the upload, verified instruction by instruction:
```
0x3cc198  li  r6,21                    ; sprintf(path,"profiles/%s/profile.%d", id, 21)
0x3cc1f4  addi r3,r26,20720            ; src  = this+0x50F0  (m_tusData staging copy)
0x3cc208  li  r4,20520                 ; srclen = 0x5028
0x3cc20c  bl  0x923304                 ; LZF compress -> scratch (0x8000 cap)
0x3cc240  bl  0xac6308                 ; S3 PUT(bucket, path, scratch, complen)
```

**`FUN_003cd0ac` = `NetPlayerData::Publish()`** — gated on load-state 3;
copies the live record `this+200` into the staging buffer, runs
`FUN_003cc938` (sign+encrypt), then spawns the publish thread. **17 call
sites**, spanning `net-clan-manager.cpp`, `task-manager-online.cpp` and the
menu/loadout units (`0x3440d4`, `0x3489ac`, `0x348de4`, `0x34a094`,
`0x34d1ac`, `0x34d4d0`, `0x34d660`, `0x350538`, `0x35f2a0`, `0x37ac80`,
`0x37b9f4`, `0x3c64c8`, `0x3c67b0`, `0x3c6978`, `0x3f0f18`, `0x3f2204`,
`0x3f3130`).

### Why zero PUTs appear in `captures/*.log` — and the fix

`config/custom_configs/config_BCUS98174.yml:142`:

```
IP swap list: "*naughtydog.com=192.168.1.100&&*naughty-dog.com=192.168.1.100&&
t1.patch.s3.amazonaws.com=192.168.1.100&&t1.campaign.config.s3.amazonaws.com=192.168.1.100&&
t1.final.*.s3.amazonaws.com=192.168.1.100&&50.18.104.153=…&&50.18.47.114=…&&174.129.210.135=…"
```

`t1.final.*.s3.amazonaws.com` catches the **virtual-hosted GET**. The
**path-style PUT goes to the bare host `s3.amazonaws.com`**, which is *not*
in the list — so every upload leaves the machine, hits real AWS, and dies on
the revoked credentials. Our catcher never sees it, and
`tools/catch_http.py` only special-cases `GET` anyway.

> **Highest-value next action.** Append `s3.amazonaws.com=192.168.1.100` to
> the IP-swap list and teach the catcher to accept `PUT` and write the body
> to `served_content/<bucket>/<key>`. The client will then upload its own
> real, correctly-signed profile after the very first match, and the revival
> server can simply serve it back — no profile generation needed at all.
> The stub must reply `200 OK` (empty body is fine); `FUN_003cc128` only
> checks the return code.

---

## 5. What is actually inside the 0x5000-byte plaintext

`FUN_003cb89c(this) -> this + 200` is the universal accessor — **436 call
sites**. Everything reads the record as unaligned **big-endian u32s**
(`lbz`×4 + `sldi`/`or` sequences), so the record is effectively a flat u32
array.

### Confirmed fields

| offset in `P` (= `rec`) | payload off | field | evidence |
|---|---|---|---|
| `P+0x0000` | — | u32 version `21` | §2 |
| `P+0x0004` | — | u32 encrypted length | §2 |
| `P+0x0008 .. P+0x00E7` | `0x000` | **custom loadouts: `u32 slot[4][14]`** | `FUN_003ccb88` (set) / `FUN_003cccd8` (get): `*(u32*)(P + (loadoutNum*14 + dataName)*4 + 8)`, asserts `dataName < kLoadoutSize (=14)` and `loadoutNum < kNumCustomLoadoutsPerMode (=4)` |
| `P+0x0300` | `0x2F8` | u32 whose **low byte is the lobby title/badge index** | `lbz r0,771(r3)` @ `0x3b16e8` → blob[9]; also read at `0x3bfe58`, `0x3bff38`, `0x40b63c` |
| `P+0x0654` | `0x64C` | u32 copied verbatim into the member blob and read by the lobby roster formatter | `0x3b1714` (blob[18..21]); `0x3be860` in `FUN_003be4e4`, the unit that builds `\|@Cff7cce96\|%s` and `[%s] %s` |
| `P+0x0A3C + i*8` | `0xA34` | **array of u64 IDs — the clan survivor name seeds** | `FUN_003ccdf8`: reads `*(u64*)(P + i*8 + 0xA3C)`, looks it up in the friend table (`FUN_00ac0194`) to use a real name, else splits the u64 and indexes the DC arrays `pFirstNames` (hash `0x86D55E98`) and `pLastNames` (`0xE51B3086`) modulo their counts, then `sprintf("%s %s", first, last)` |
| `P+0x1E28` | `0x1E20` | u32 "clan started" flag — set to 1 if zero | `0x37e6b8`, `net-clan-manager.cpp` |
| `P+0x1E34` | `0x1E2C` | **u32 matches played, game mode A** — `++` at end of match | `0x3f2598` in `FUN_003f208c` (`task-manager-online.cpp`), guarded by `FUN_003a3d40(...) == 2` |
| `P+0x1E38` | `0x1E30` | **u32 matches played, game mode B** — `++` | `0x3f2654`, guarded by `== 3` |
| `P+0x1E44` | `0x1E3C` | **u32 journeys completed** — `++` | `0x37e6f4`, `net-clan-manager.cpp` |
| `P+0x1E4C` | `0x1E44` | u32 wins, mode A | `0x3f25f8`, gated on team + result `== 3` |
| `P+0x1E50` | `0x1E48` | u32 wins, mode B | `0x3f26b4` |

Densely-populated u32 regions found by the same scan (each a distinct stat
counter, most reached through the `net-tus-variable.cpp` named-variable
layer rather than a literal displacement, so not individually named here):
`0x02D0-0x0383`, `0x0654-0x068F`, `0x07E8`, `0x0808`, `0x0A1C-0x0A3B`,
`0x1A48`, `0x1AD4-0x1ADF`, `0x1BB8-0x1BF3`, `0x1CF8-0x1D13`,
`0x1DF4-0x1DFB`, `0x1E20-0x1E57`.

### Not in the record

The four equipped loadout item-ids the lobby shows come from a **live
global (`0x01382082`)**, not from the profile — see §6.

---

## 6. The 32-byte member data blob, decoded field by field

Companion to `2026-08-17-member-data-blob-rank-and-0x142-hostrank.md`
(parallel workstream); see also `docs/factions-metagame-reference.md` for the
game-design meaning of the counters these fields carry. That note establishes the transport (`0x13a` →
`0x13b`/Member, `FUN_00ad2650`'s `len == 32` gate). This section adds the
**producer's exact byte-by-byte sources**, read off `FUN_003b15bc`'s raw
disassembly (`0x3b15bc`-`0x3b17f8`). Stack buffer base is `r1+120`.

| blob | width | written at | source | meaning |
|---|---|---|---|---|
| `0..7` | 8 | `std r7,120(r1)` @ `0x3b17c8` | `*(u64*)(party_room+0x10)` if `FUN_00ad0fd0() > 1` and `party_room+0xB8 != 0`, else `0` | party grouping id |
| `8` | 1 | `stb r0,128(r1)` @ `0x3b15e8` | low byte of `*(u32*)(0x01459260 + 0x0C)` | a live session boolean; AND-reduced across members at `0xad2b6c` |
| `9` | 1 | `stb r0,129(r1)` @ `0x3b16f0` | `*(u8*)(P + 0x303)` — **profile field**, `0` if `FUN_0003b584()` returns non-zero | title / badge index (used as `value-1` into a name lookup at `0x3c2ad0`) |
| `10..13` | 4 | `stb`×4 @ `0x3b17b8`-`0x3b17c4` | 4 bytes copied from **global `0x01382082`** | equipped loadout item-ids, `0xFF` = unset. **Live selection, NOT read from the profile here** |
| `14..15` | 2 | `sth r3,134(r1)` @ `0x3b16ac` | `FUN_00323818(a, b)` = `min(a,999) + min(b,9)*1000`, `a = (P[0x1E34] + P[0x1E38]) / 7`, `b = P[0x1E44]` | **profile-derived**: `weeks_survived + journeys*1000`. `/7` = matches→in-game weeks |
| `16..17` | 2 | `sth r3,136(r1)` @ `0x3b16bc` | `FUN_003c8e30()` — returns `*(int*)(g+0x78) - 1` if non-zero, else the first satisfying bracket index in DC table `0xC85E199D` | **rank / tier index**, computed live from a DC threshold table, not stored |
| `18..21` | 4 | `stb`×4 @ `0x3b1744`-`0x3b175c` | `P + 0x654` BE u32, copied verbatim | two more UI u16 stats |
| `22..31` | 10 | **never written** | uninitialised stack | garbage — live captures show `0x0137D700` (player-array base) and `0x01305870` (TOC) leaking here |

Sent to both room objects via `FUN_00ad1fc0(room, r1+120, 32)` at `0x3b17cc`
(party room, slot `-32764`) and `0x3b17e0` (game room, slot `-32740`).

### Decoding the live captures

The UI reads `*(u16*)(blob + 14 + index*2)` where `index` is a UI-supplied
byte (`0x3c27a0`), so indices 0..3 map to blob `14/16/18/20`.

**Party-room capture** (`00 00 01 3a 20 3a e1 48 …`):

```
blob = 00 00 00 00 00 00 00 00 | 00 | 00 | ff ff ff ff | 00 00 | 00 00 | 00 00 00 00 | de 50 00 00 00 00 01 26 e0 0c
        [0..7] party id = 0      [8]=0 [9]=0  [10..13] no loadout   [14]  [16]  [18..21]   [22..31] stack junk
```
* `[0..7] = 0` — not grouped as a party by the producer's own test.
* `[9] = 0` — no title.
* `[10..13] = ff ff ff ff` — no loadout selected (party lobby). Matches the
  producer: it copies whatever the live global holds, and nothing is equipped.
* `[14..15] = 0x0000` → weeks = 0, journeys = 0 → **a brand-new profile**.
  This is exactly what an empty `profile.21` produces.
* `[16..17] = 0x0000` → rank/tier bracket 0.
* `[18..21] = 00 00 00 00` → `P+0x654` is zero.
* `[22..31] = de 50 00 00 00 00 01 26 e0 0c` — **uninitialised stack**, and
  `0x0126E00C` is a data address, which is the proof.

**In-game-room capture** (`… 00 0e ff ff …`):

```
blob = 00 00 00 00 00 00 00 00 | 00 | 00 | 00 0e ff ff | 00 00 | 00 00 | 00 00 00 01 | 00 00 00 00 01 37 d7 00
```
* `[10..13] = 00 0e ff ff` — loadout slot0 = item `0x00`, slot1 = item
  `0x0E`, slots 2-3 empty.
* `[18..21] = 00 00 00 01` → `P+0x654 == 1`, i.e. UI stat index 3 = 1.
* `[28..31] = 01 37 d7 00` = `0x0137D700`, the player-array base — junk.

Third capture differs only in `[18..21] = 00 00 00 0e` and
`[28..31] = 00 00 00 04`.

### The `0x13a` wire frame itself (`0xad6250`-`0xad629c`, raw disassembly)

```
ad6250:  li  r0,314        ; 0x13a
ad6260:  stw r0,112(r1)    ; wire[0..3]  = opcode          (buffer base = r1+112)
ad6268:  stb r31,116(r1)   ; wire[4]     = blob length (32)
                           ; wire[5..7]  = NEVER WRITTEN
ad6264:  std r9,120(r1)    ; wire[8..15] = room_id, ONE 8-byte value (= *(u64*)(room_obj+0x10))
ad625c:  addi r3,r1,128
ad626c:  bl  0xe3e064      ; memcpy(wire+16, blob, 32)     -> wire[16..47]
                           ; wire[48..79] = NEVER WRITTEN
ad6294:  li  r5,80         ; total frame = 80 bytes
ad629c:  bl  0xacb93c      ; send
```

**Wire bytes 5..7** (`3a e1 48` / `27 0e 9c` / `3e 6d 94`): the sender writes
only byte 4 (`0x20` = length). Bytes 5..7 are **uninitialised stack in the
send buffer** — the same pattern the sibling note documents for
`0x140`/`0x142` offset 6:7 and `0x13e` offset 6:7. Not a checksum, not a
sequence number. Treat as don't-care; a relay must not attempt to reproduce
or validate them. Bytes 48..79 of the 80-byte frame are junk for the same
reason.

**Correction to an earlier framing**: wire `[8:12]` is not
a correlation id and `[12:16]` is not a separate room pointer — a single
`std` writes `[8:16]` as one big-endian u64 room id. In the captures that
u64 is `0x00000000_01387f58` (party) and `0x012723d8_01383bd8` (game); its
low half being the room-object address is a property of the ids the stub
hands out, not of the protocol.

**The item-id table for `blob[10..13]`**: those four bytes are indices into
a DC (data-compiler) script array, not an EBOOT enum — `FUN_003a2310` loops
`k = 0..3` over `blob[10+k]`, comparing each against entries and subtracting
a cost (`0x3a262c`-`0x3a2664`), which is the loadout point-budget check. The
name table itself lives in the game's `.pak`/DC modules, so no string list
exists in the EBOOT to enumerate. **Not resolved this pass.**

### Bottom line on the blob

Only **22 of 32 bytes are meaningful**; `[22..31]` are leaked stack and must
never be interpreted. Of the 22, exactly **three fields come from the
profile** (`[9]` ← `P+0x303`, `[14..15]` ← `P+0x1E34/0x1E38/0x1E44`,
`[18..21]` ← `P+0x654`); `[0..7]`, `[8]`, `[10..13]` and `[16..17]` are all
computed live. **So serving a populated `profile.21` directly changes what
`[9]`, `[14..15]` and `[18..21]` carry**, and hence what the lobby shows for
that player once the relay-length fix in the sibling note is applied.

---

## 7. `userdata/<npid>.txt.crypt` — a developer-override channel, not player data

`FUN_003b117c` (reached from `0x00356830`) is a content-download sequencer.
Its string set, resolved through the anchor chain, is the whole story:

```
0x00E7D2E0  %s/%s-1.psarc
0x00E7D2F0  %s-1
0x00E7D2F8  build/%s/actor%i
0x00E7D310  build/%s/text1/%i.networking
0x00E7D330  userdata/%s.txt
```

`build/<user>/…` are **per-developer asset overrides**. `userdata/%s.txt`
is fetched by the same function, in the same pass, into the same place:

```
0x3b13d0  li  r0,31           ; progress state 31
0x3b13d4  lwz r4,-32724(r30)  ; "userdata/%s.txt"
0x3b13d8  addi r5,r31,32      ; the local player's online id
0x3b13e4  bl  0xe46670        ; sprintf
0x3b1400  bl  0x387368        ; download
0x3b1440  bl  0x7edc2c        ; resolve local content dir
0x3b1458  bl  0xe46670        ; sprintf(path, "%s/%s", dir, "userdata/<id>.txt")
0x3b1468  bl  0xada7b8        ; -> FUN_00ada3ac : generic text/config loader
```

`FUN_00387368` is the downloader that appends the suffix — its own string
table contains **`%s/%s.crypt`** (`0x00E7B898`), which is where the observed
`.txt.crypt` URL comes from. That is the *same* content-delivery path as
`net1.bin.psarc.crypt` and `campaign.config.txt.crypt`, so **the container is
the one already solved**: `[BE u32 length][20-byte HMAC-SHA1][Blowfish ECB
body]`, per `2026-08-14-blowfish-psarc-solve.md` — `tools/psarc_crypt.py
decrypt/encrypt` handles it directly. The plaintext is a `.txt`, i.e. a
line-oriented config, not a PSARC.

**Verdict: `userdata/<npid>.txt.crypt` holds no rank, gear, clan or journey
state.** Nothing in `net-player-data.cpp` touches it, and the profile
loader never reads it. It is a per-PSN-account override/config file ND used
internally. Serving `200 OK` empty (today's behaviour) is correct and
should be left alone. **Confidence: high on the plumbing, medium on the
"developer override" characterisation** — no real body has ever been
observed, and the real bucket now returns `403`.

### Bonus, relevant to any `.crypt` we serve

The raw-socket HTTP client `FUN_00021210` parses these response headers:
`HTTP/1.x 200 OK`, `Content-Length: `, **`x-amz-meta-len: `**, and
**`x-amz-meta-sig: `**. A global flag (`*(u8*)(*g + 0x0C)`) selects whether
the expected body length comes from `Content-Length` or `x-amz-meta-len`;
when set, it also HMAC-SHA1s the received body with the **same net-drm key**,
base64s it, and `strcmp`s the result against `x-amz-meta-sig`, returning
`-2` on mismatch. Our stub has never needed to send those headers (the
`net1.bin.psarc.crypt` serve worked without them), so the flag is evidently
clear in this build — but if a `.crypt` download ever starts failing with no
other explanation, this is the check to emulate.

---

## 8. What the revival server must do

### Preferred: round-trip, don't generate

1. Add `s3.amazonaws.com=192.168.1.100` to the RPCS3 IP-swap list.
2. Teach `tools/catch_http.py` to handle `PUT`: write the body to
   `SERVED_DIR/<path>` (the path-style URL already contains the bucket, so
   `PUT /t1.final.prod/profiles/<id>/profile.21` and
   `GET /profiles/<id>/profile.21` on the virtual-host must be mapped to the
   same file), reply `200 OK`, empty body. *(Sketch only — `catch_http.py` is
   running against live tests; not edited by this pass.)*

   ```python
   # in build_response(), before the GET-only bail-out:
   if parts[0] == "PUT":
       raw_path = parts[1].split("?", 1)[0].lstrip("/")
       # path-style PUT: "<bucket>/<key>"  ->  store under the key alone,
       # so the virtual-hosted GET ("<key>") finds it.
       key = raw_path.split("/", 1)[1] if raw_path.startswith("t1.") else raw_path
       body = text_body_bytes            # everything after the blank line
       dest = os.path.join(SERVED_DIR, key)
       os.makedirs(os.path.dirname(dest), exist_ok=True)
       with open(dest, "wb") as f:
           f.write(body)
       return b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", ...
   ```
3. Play one match. The client publishes on every progression event, so a
   real, self-signed profile lands on disk immediately, and every later boot
   loads it. **Progression then persists with zero format knowledge needed.**

### Fallback / bootstrapping: generate one

Everything needed is in this note; the codec below round-trips against a
faithful port of the client's own decoder. Not committed as a tool this pass
(nothing under `tools/` was touched) — drop it in as `tools/profile_codec.py`.

```python
import hmac, hashlib, struct, sys
sys.path.insert(0, "tools")
import psarc_crypt as pc                        # Blowfish + the 4168-byte key table

NET_DRM_KEY = b"xM;6X%/p^L/:}-5QoA+K8:F*M!~sb(WK<E%6sW_un0a[7Gm6,()kHoXY+yI/s;Ba"
PLAIN_LEN, REC_LEN = 0x5000, 0x5028

def lzf_literal(data):                          # legal LZF, zero compression
    out = bytearray(); i = 0
    while i < len(data):
        n = min(32, len(data) - i)
        out.append(n - 1); out += data[i:i+n]; i += n
    return bytes(out)

def build_profile_21(plain):                    # plain: exactly 0x5000 bytes
    assert len(plain) == PLAIN_LEN
    total = (PLAIN_LEN + 0x1b) & ~7             # 0x5018
    buf = bytearray(total); buf[0:PLAIN_LEN] = plain
    buf[total-0x14:total] = hmac.new(NET_DRM_KEY, bytes(buf[0:total-0x14]),
                                     hashlib.sha1).digest()
    pc.blowfish_init_key(pc.SECRET_KEY)
    rec = bytearray(REC_LEN)
    rec[0:4] = struct.pack(">I", 21)
    rec[4:8] = struct.pack(">I", total)
    rec[8:8+total] = pc.blowfish_encrypt(bytes(buf))
    return lzf_literal(bytes(rec))              # <- this is the profile.21 body

def set_u32(plain, P_off, value):               # P_off is the P+0x…. offset
    struct.pack_into(">I", plain, P_off - 8, value)

# A profile that gives the player a populated clan and four loadout slots:
p = bytearray(PLAIN_LEN)
for slot in range(4):                           # loadouts: P+8 + (slot*14 + name)*4
    for name in range(14):
        struct.pack_into(">I", p, (slot*14 + name)*4, 0)    # 0 = default item id
set_u32(p, 0x1E34, 84)      # 84 matches in mode A  -> 12 weeks
set_u32(p, 0x1E38, 0)
set_u32(p, 0x1E44, 2)       # 2 journeys completed  -> blob[14] = 12 + 2*1000 = 2012
set_u32(p, 0x1E28, 1)       # clan started
set_u32(p, 0x0300, 5)       # lobby title index 5
open("profiles/<npid>/profile.21", "wb").write(build_profile_21(bytes(p)))
```

Serve that at `GET /profiles/<online_id>/profile.21` from the
`t1.final.prod.s3.amazonaws.com` vhost (already redirected) — the existing
`served_content/` file-serving branch in `catch_http.py` needs no change,
just the file on disk.

### What still gates the visible symptoms

* **Rank never progresses** — the client already *computes* rank/weeks
  correctly from the record; the record has always been all-zero because
  every GET returns empty *and* every PUT is lost to real AWS. Both fixes
  above address this. The rank *widget* additionally needs the
  `0x13a`→`0x13b` 32-byte relay fix from the sibling note for **remote**
  players; the local player renders from `room_obj+0x19FC` regardless.
* **Gear appears randomized** — for remote players this is
  `FUN_00ad2650` returning `NULL` (sibling note §3d), leaving stale
  selections; `blob[10..13]` is a *live* global, not a profile field, so
  serving a profile alone will not fix remote loadout display. The relay fix
  is the necessary and sufficient change there.

---

## 9. Confidence

**High** (raw disassembly + string evidence + a validated Python round-trip):
* `m_tusData` = 0x5028 bytes, `[version=21][len][blowfish body]`, version and
  length checks, the `len == sizeof(m_tusData)` assert.
* Sign+encrypt / verify+decrypt algorithms and the fact that both keys are
  the already-solved ones (dereferenced from `0x01243A60`/`0x01243A64`).
* LZF as the compressor, and that a literal-only stream is legal.
* GET is virtual-hosted, PUT is path-style against bare `s3.amazonaws.com`,
  and that host is absent from the IP-swap list.
* The loadout accessor formula and its two asserts.
* The 32-byte blob's per-byte producer sources, including which 10 bytes are
  uninitialised.
* `userdata/*.txt.crypt` rides the generic `.crypt` downloader and is not
  read by `net-player-data.cpp`.

**High, on independent corroboration**:
* `P+0x1E34`/`P+0x1E38` = matches played (= in-game *days*) per game mode,
  and `blob[14..15]` = `weeks_survived + journeys*1000`. The code gives
  `(P[0x1E34] + P[0x1E38]) / 7` capped at 999, plus `P[0x1E44]` capped at 9;
  `docs/factions-metagame-reference.md` independently establishes from
  external sources that **one completed match = one in-game day, 7 days = 1
  week, and a Journey is 12 weeks = 84 matches**. The `/7` and the two caps
  are exactly that rule, arrived at from opposite directions.

**Medium**:
* Whether the mode split is specifically Supply Raid vs. Survivors — the
  guards are `FUN_003a3d40(...) == 2` and `== 3`, and that enum was not
  resolved this pass.
* `P+0x0A3C+i*8` as the clan **survivor** roster seeds specifically (it is
  definitely a u64-keyed name lookup with a first/last-name procedural
  fallback; whether the index space is survivors or some other roster is not
  proven).
* `userdata/*.txt.crypt` being a *developer* override file — the plumbing is
  certain, the purpose is inferred from its neighbours (`build/<user>/…`).

**Not established**:
* The DC item-id table behind `blob[10..13]` (lives in `.pak`, not the EBOOT).
* Named field map for the rest of the 0x5000-byte payload — most of it is
  reached through the `net-tus-variable.cpp` named-variable indirection
  rather than literal displacements, so recovering names needs the DC
  modules, not more EBOOT work.
* Live acceptance of a generated `profile.21` by the game. The codec is
  self-consistent against a faithful port of the client's decoder, but has
  never been served to RPCS3.
* Whether the real bucket ever serves anything again — both objects return
  `403` today, so no ground-truth sample exists.

## Deliverables

* This note.
* `research/ghidra/profile_userdata_decomp.txt`, `profile_batch2.txt`,
  `profile_batch3.txt`, `profile_batch4.txt`, `profile_batch5.txt`,
  `profile_batch6.txt`, `profile_batch7.txt`, `profile_batch8.txt` —
  decompiles backing every claim above.
