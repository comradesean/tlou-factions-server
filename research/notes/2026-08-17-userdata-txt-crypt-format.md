# `userdata/<online_id>.txt.crypt`: the reader's expected format, field by field

Sibling to `2026-08-16-profile-and-userdata-reverse-engineering.md`. That note
mapped the plumbing (§7) and characterised this object as a "generic
text/config loader" rideralong, medium-confidence "developer override", without
decoding the parser or the plaintext structure. **This note closes that gap:**
it decodes the loader (`FUN_00ada3ac`), proves the container against a real
sibling sample, recovers the exact plaintext grammar and the key-hash algorithm,
and pins down that the retail client reads **exactly one key** out of this file.

Bottom line up front:

* **Container = the already-solved Blowfish+HMAC `.crypt` wrapper**
  (`[BE u32 len][20-byte HMAC-SHA1][Blowfish-ECB body]`, same keys) - **no PSARC,
  no LZF inside**. The body decrypts straight to text. Proven, not assumed:
  `tools/psarc_crypt.py` decrypts the real `campaign2/3.config.txt.crypt`
  siblings with **HMAC OK** and rebuilds them **byte-for-byte**.
* **Plaintext = whitespace-delimited `key value` pairs**, one per line
  (`\n` or `\r\n`). Real content confirmed from the sibling samples.
* Keys are matched **by CRC-32/MPEG-2 hash**, never by string compare.
* **The client reads one key from `userdata/<id>.txt`** (hash `0x8EFC1478`),
  hashes its *value* string, and stores it in the NetInfo singleton at `+0x80`.
  Everything else in the file is ignored.

## HOW MANY key/value pairs does the file contain?

**Unknown for the userdata file specifically — and the reader imposes no fixed
count.** The parser (`FUN_00ada3ac`, §1) does a two-pass tokenize: pass 1
*counts* however many whitespace-delimited pairs are present, `malloc(count*8)`,
pass 2 fills the table. So a real `userdata/<id>.txt` may hold anywhere from
zero to many pairs; the client just hash-indexes the table and currently queries
only one hash (`0x8EFC1478`). "Reads one" ≠ "contains one" — the count is
whatever the writer put there, and we have **never obtained a real userdata
sample** (the S3 buckets 403 anonymously, so this format was reversed from the
reader + the sibling config files, not from a real `comradesean.txt`).

**Grammar evidence from the real siblings** (same container + grammar, decrypted
from `ref/ps3/t1.campaign.config.s3.amazonaws.com/`):
- `campaign2.config.txt.crypt` → **4 pairs**: `queue-server-addr 50.18.47.114`,
  `queue-server-port 7320`, `interval 10`, `enable 1`.
- `campaign3.config.txt.crypt` → **6 pairs**: the same four plus
  `enable-dlc-facebook 1`, `enable-dlc-facebook-text 0`.

So files of this grammar in the wild carry a small handful of pairs. A real
userdata file most likely does too, but its exact set is unrecovered — the one
key we know it's read for (`0x8EFC1478`) may sit alongside others whose purpose
we can't see until we get a real sample or a DC key-name dump. Worth keeping the
"hidden meaning" open: `NetInfo+0x80` has no active retail *reader* found, but
that is an absence-of-evidence, not proof it is inert.

**Container wrinkle:** the *base* `campaign.config.txt.crypt` (no digit) does
NOT decrypt with the standard `.crypt` wrapper — its plaintext-header magic is
`0x919f968d`, a THIRD framing (distinct from both this file's Blowfish+HMAC
wrapper and profile.21's `0x69c6d35c` LZF container). Only `campaign2` and
`campaign3` share the userdata grammar/container; the base file is a different
beast and was not the validation basis.
* **We can synthesize an accepted file without a real sample** - `psarc_crypt`
  already builds a byte-valid container, and `tools/userdata_crypt.py` wraps it
  for this file's grammar. The one caveat is that the *meaningful* key's
  plaintext name is unrecovered (CRC is one-way; the string is not in the
  EBOOT), so we can produce a valid file but not deliberately set that one
  setting without a real sample or the name.

Address convention: **VMA = file offset + 0x10000**. Every address below was
read off `powerpc64-linux-gnu-objdump` disassembly of the decrypted EBOOT
(`.../The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf`). Global-reaching
idioms resolved with `tools/eboot_analysis/` (`r2 = 0x01305870`).

---

## 0. The client really does fetch this, live

`captures/http_catch.log` shows the client GETting
`/userdata/comradesean.txt.crypt` from `t1.final.prod.s3.amazonaws.com`
repeatedly (lines 856, 925, 1030, 1099, …), interleaved with
`campaign.config.txt.crypt` and the `profile.21` GETs. The stub currently
answers `200 OK` with an empty body ("live fetch … failed"), and the game
proceeds normally - already-valid behaviour, explained in §5.

We have **no real `userdata` sample** (bucket 403s), but we DO have real
siblings that go through the identical loader and container:
`ref/ps3/t1.campaign.config.s3.amazonaws.com/campaign{,2,3}.config.txt.crypt`.
These are the ground truth this note leans on.

---

## 1. Download + load sequence (`FUN_003b117c`, the content sequencer)

`FUN_003b117c` (reached from `0x00356830`) fetches the per-developer/per-user
override assets in one pass. String table (anchor-resolved, `r30 = 0x1271abc`):

```
slot r30-32724 -> 0x00E7D330  "userdata/%s.txt"
slot r30-32716 -> 0x00E5DC80  "%s/%s"
```

The userdata leg, verified instruction-by-instruction (`0x3b13d0`-`0x3b1468`):

```
0x3b13d0  li   r0,31              ; progress state 31
0x3b13d4  lwz  r4, -32724(r30)    ; "userdata/%s.txt"
0x3b13d8  addi r5, r31,32         ; local player's online id
0x3b13e4  bl   0xe46670           ; sprintf(path, "userdata/%s.txt", id)
0x3b1400  bl   0x387368           ; download  (appends ".crypt", fetches+decrypts)
0x3b140c  cmpwi r3,0 ; bge 0x3b1434 ; r3 < 0  -> skip load entirely (no error)
0x3b1440  bl   0x7edc2c           ; resolve local content dir
0x3b1458  bl   0xe46670           ; sprintf(path2, "%s/%s", dir, "userdata/<id>.txt")
0x3b1460  lwz  r3, -32712(r30)    ; the userdata config object (BSS 0x014DB2AC)
0x3b1468  bl   0xada7b8           ; -> FUN_00ada3ac : parse the file into that object
```

* `FUN_00387368` is the same downloader used for `net1.bin.psarc.crypt` etc.;
  its own string pool holds `"%s/%s.crypt"` (`0x00E7B898`) - that is where the
  observed `.txt.crypt` URL suffix comes from. It fetches and **decrypts the
  container**; the HMAC is enforced (per `2026-08-14-repack-rejection-…`).
* A **failed** download (`r3 < 0`) simply skips the parse - userdata is optional.
* On success the file is parsed into the BSS global object at **`0x014DB2AC`**
  (call it `g_userdataCfg`), a 12-byte struct `{char* text; u32 count; Pair* arr}`.

`FUN_00ada7b8` is a thin shim: it stacks a heap-tag word (`= 28`) and tail-calls
`FUN_00ada3ac(g_userdataCfg, path, &tag)`.

---

## 2. The parser: `FUN_00ada3ac` - a whitespace key/value tokenizer

Decoded from raw disassembly (`0xada3ac`-`0xada7b4`). Arguments
`r3 = out (g_userdataCfg)`, `r4 = filepath`, `r5 = &heap-tag`.

1. **Open + size** (`bl 0xe56a2c`); on `< 0` return (file absent → object left
   whatever it was, i.e. empty).
2. **`out->text = malloc(filesize + 1)`** (`0x915a30`, tagged 28), then
   open/read/close the whole file into it (`0xe569ec`, `0xe5698c`, `0xe5692c`)
   and NUL-terminate (`buf[filesize] = 0`). `out->count = 0`.
3. **Two-pass tokenizer.** It walks the buffer with a **ctype table** at
   `-32768(r30)` of the tokenizer's CU, testing `table[c] & 0x144` to decide
   "is separator" (space/tab/CR/LF/control). Pass 1 counts pairs; then it
   `malloc(count * 8)` for `out->arr` and re-walks. For each `key value` pair it
   stores an 8-byte record:

   ```
   arr[i].hash   = <converter>(key)      // CRC-32/MPEG-2 of the key token (see §3)
   arr[i].value  = &value_token          // pointer into out->text (NUL-terminated)
   ```

   Separators in `text` are overwritten with NULs in place, so `arr[i].value`
   points at a normal C string.

So the object ends up as: the file text (tokenised in place) + a flat array of
`{CRC32(key), char* value}`, one per whitespace-delimited pair. This is a
**line/space-oriented `key value` config**, exactly matching the real samples:

```
queue-server-addr 50.18.47.114
queue-server-port 7320
interval 10
enable 1
```

(A stray odd token with no following value is harmless - it just never becomes a
lookupable pair.)

### Lookup: `FUN_00ada358(obj, hash)`

```
for i in 0 .. obj->count-1:
    if obj->arr[i].hash == hash: return obj->arr[i].value   // char* to value
return 0
```

Pure hash match - **the literal key string is never compared**. Callers get back
a pointer to the value string (or NULL) and interpret it (atoi / first-char /
re-hash) as they see fit.

---

## 3. The key hash is CRC-32/MPEG-2

The converter that produces `arr[i].hash` is a virtual call landing in
`FUN_0090aee4`, a table-driven hash:

```
h = 0
for each byte c of the string:
    h = ((h << 8) ^ table[((h >> 24) ^ c) & 0xFF]) & 0xFFFFFFFF
```

The 256-entry `table` (`0x00EB4DE0`) begins `0x00000000, 0x04C11DB7, …` - the
standard **CRC-32 polynomial 0x04C11DB7, MSB-first, init 0, no reflection, no
final XOR** = **CRC-32/MPEG-2**. Confirmed exactly against the four key hashes
the EBOOT bakes into the campaign-config reader (`FUN` at `0x7f16e0`):

| key                 | EBOOT immediate | CRC-32/MPEG-2 |
|---------------------|-----------------|---------------|
| `queue-server-addr` | `0xCF0AD2C7`    | `0xCF0AD2C7` ✓ |
| `queue-server-port` | `0x07DE9D65`    | `0x07DE9D65` ✓ |
| `interval`          | `0xE6ACEEFC`    | `0xE6ACEEFC` ✓ |
| `enable`            | `0x8516DACD`    | `0x8516DACD` ✓ |

`tools/userdata_crypt.py:crc32_mpeg2()` is this hash; it reproduces all four.

---

## 4. What the client reads OUT of `userdata/<id>.txt`: one key

`g_userdataCfg` (`0x014DB2AC`) is referenced by only **two** code sites in the
whole binary: the loader call in §1, and a single consumer at **`0x003568ec`**
(inside the online-init function `FUN_003557a8`):

```
0x3568e8  li   r4, 5240           ; 0x00001478   (low half)
0x3568f0  oris r4, r4, 36604      ; 0x8EFC0000   -> r4 = 0x8EFC1478  (key hash)
0x3568ec  lwz  r3, -30868(r30)    ; g_userdataCfg
0x3568f4  bl   0xada358           ; value = lookup(g_userdataCfg, 0x8EFC1478)
0x356900  if value == NULL     -> store 0 at NetInfo+0x80
0x356904  if *value == '\0'    -> store 0 at NetInfo+0x80
          else                 -> store  CRC32/MPEG-2(value)  at NetInfo+0x80
0x35694c  stw  r0, 128(r9)        ; r9 = NetInfo singleton 0x013835C0
```

So the *entire* effect of the userdata file on the retail client is: look up one
key (hash `0x8EFC1478`), hash its value string, and drop that u32 into the
online/NetInfo singleton at `+0x80`. The value being re-hashed (not atoi'd)
means the setting is an **enum / named value**, not a number.

**The plaintext name behind `0x8EFC1478` was not recovered.** CRC-32 is not
invertible, the string is not present in the EBOOT (DC config keys are hashed at
build time), and ~110k dictionary/compound candidates did not hit it. It will
fall out immediately from a single real `userdata` sample, or from a DC-symbol
dump.

**`NetInfo+0x80` has no clearly-active retail reader.** The only non-stack access
to offset `0x80` in the net compilation unit (`0x340000`-`0x360000`) besides this
write is `lbz r0,128(r9)` at `0x34e778`, and there `r9` is a *different* global
(`-32548(r30)`, not the NetInfo singleton). No pointer-table slot targets
`NetInfo+0x80` directly. Consistent with a dev/QA hook that is inert in this
shipped build - which matches the sibling note's "developer override"
characterisation. **Confidence: high that only this one key is read and where it
is stored; medium that `+0x80` is effectively inert at retail** (a cross-CU
reader reached via one of the 186 other anchor slots for this singleton can't be
fully excluded without a live trace).

---

## 5. Container - proven against real siblings

`campaign.config.txt.crypt` in `ref/ps3/` is stored **decrypted** (plaintext
`queue-server-addr …`), evidently a prior tool's in-place decrypt; ignore it for
container work. `campaign2` and `campaign3` are **genuine encrypted objects**:

```
campaign2.config.txt.crypt : 112 bytes = [4 len=0x51][20 HMAC][88 Blowfish body]
campaign3.config.txt.crypt : 152 bytes = [4 len=0x7C][20 HMAC][128 Blowfish body]
```

Tells that nail the framing before any code is read: the body length is a
multiple of 8 only after subtracting **24** (4+20), and the two files **share
identical 16-byte ciphertext blocks** (`4e16 e498 0801 44c6 34ed 3c82 …`) - the
signature of **ECB with a shared key on a shared plaintext block**
(`interval `…). `tools/psarc_crypt.py`:

```
campaign2: decrypt -> HMAC OK, plaintext = "queue-server-addr 50.18.47.114\r\n…enable 1\r\n\r\n"
campaign3: decrypt -> HMAC OK, plaintext = "queue-server-addr 50.18.47.114\n…enable-dlc-facebook-text 0\n"
rebuild(plaintext) == original file : byte-for-byte, both.
```

So the container is **exactly** `encrypt_crypt_file()` from `psarc_crypt.py`:

```
pad body to a multiple of 8 (zeros)
digest      = HMAC-SHA1(HMAC_KEY, padded_body)         # 20 bytes, plaintext
file        = BE_u32(len(plaintext)) || digest || Blowfish_ECB(padded_body)
```

Keys: Blowfish `"(SH[@2>r62%5+QKpy|g6"`, HMAC-SHA1
`"xM;6X%/p^L/:}-5QoA+K8:F*M!~sb(WK<E%6sW_un0a[7Gm6,()kHoXY+yI/s;Ba"`
(the project's already-solved pair). **No LZF** on these files - the profile.21
LZF layer does *not* apply here.

---

## 6. Synthesizing a valid `userdata/<id>.txt.crypt`

Yes, without a real sample:

* **Minimal accepted file:** any valid container. An **empty body** is valid and
  already works live (§0/§1: absent or empty → no key → `NetInfo+0x80 = 0`,
  which is also the not-present default). The existing empty-`200` stub is
  correct and needs no change.
* **A populated, still-accepted file:** valid container over
  `key value\n` lines. `tools/userdata_crypt.py build out.txt.crypt k=v …`
  produces one; round-trip and HMAC verified.
* **Deliberately setting the one meaningful key:** blocked only by the unknown
  plaintext name behind hash `0x8EFC1478`. If a real sample or DC-symbol dump
  ever names it, put `<name> <value>` in the file - nothing else is required.
  (Its retail effect is unclear anyway - see §4.)

`tools/userdata_crypt.py`:

```
build   out.txt.crypt key1=val1 key2=val2 …   # or  --from pairs.txt
build   out.txt.crypt                          # empty (minimal-valid) file
decode  in.txt.crypt                           # plaintext + pairs + each key's CRC
keyhash <name> …                               # CRC-32/MPEG-2 of a key name
```

`decode` flags any pair whose key hashes to `0x8EFC1478` as the one the client
reads.

---

## 7. Confidence

**High** (real-sample proof and/or verified disassembly + validated Python):
* Container = `[BE u32 len][20-byte HMAC-SHA1][Blowfish-ECB body]`, same keys,
  **no LZF** - decrypts real `campaign2/3` with HMAC OK and rebuilds them
  byte-for-byte.
* Plaintext grammar = whitespace-delimited `key value` pairs (`\n`/`\r\n`).
* Loader `FUN_00ada3ac` builds `{CRC32(key), char* value}` records; lookup
  `FUN_00ada358` is pure hash match.
* Key hash = CRC-32/MPEG-2 (matches four EBOOT-baked campaign key hashes).
* The client reads exactly one key from `userdata/<id>.txt` (hash `0x8EFC1478`,
  `0x3568e8`) and stores `CRC32(value)` (or 0) at `NetInfo(0x013835C0)+0x80`.
* A synthesized file (incl. empty) is accepted; the empty-`200` stub is valid.

**Medium:**
* `NetInfo+0x80` is effectively inert in the retail build (no active reader
  found in the net CU; a cross-CU reader via one of the singleton's 186 anchor
  slots is not fully excluded without a live trace).
* This being a developer/QA override channel (purpose inferred from its
  `build/<user>/…` neighbours and the single dev-style setting).

**Not established:**
* The plaintext key string behind `0x8EFC1478` (CRC is one-way; not in EBOOT).
* Any second consumer of the file (none exists in this build by static search).

## Deliverables

* This note.
* `tools/userdata_crypt.py` - build/decode/keyhash for `.txt.crypt` config files,
  wrapping `tools/psarc_crypt.py`'s container.
