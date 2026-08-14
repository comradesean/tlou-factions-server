# net1.bin: Confirmed Server List (All Dead)

Full pipeline now confirmed working end-to-end: RPCS3 DNS-hook redirects `t1.final.prod.s3.amazonaws.com` to our catcher -> catcher serves the real `net1.bin.psarc.crypt` (65,160 bytes, user-supplied, saved at `tools/served_content/net1.bin.psarc.crypt`, gitignored) -> game decrypts/extracts it to `net1.bin` (283,870 bytes, plain, `research/net1bin/net1.bin`, gitignored - see below) -> game reads it and attempts `connect to 50.18.104.153:7320`.

## Contents

`net1.bin` has no readable global strings pattern (`strings` finds nothing useful) - it's a large blob of mostly non-text data, but a `grep -a` for IP-address patterns finds exactly one small string cluster at offset `0x3fab2`:

```
174.129.210.135\0
50.18.104.153\0
50.18.47.114\0
>>>>>>>>>>> 25% or more of the population is already sick; preventing downward spiral!\0
>>>>>>>>>>> Player has a supply surplus, no one dies on this day!  Surplus is: %f \n\0
>>>>>>>>>>>>>> More than 10 clan members died today, clamping deaths to 10!\0
```

Three null-terminated IP strings sitting directly next to **unrelated campaign-mode debug text** (survivor-camp population/supply/clan mechanics). This strongly suggests `net1.bin` is a general debug/log string table shared across subsystems, not a purpose-built network config file - the three IPs are most likely **hardcoded fallback server addresses** compiled in as literal debug strings, not a structured server-list format.

Port `7320` (matching the `connect to 50.18.104.153:7320` log line) was not found as an adjacent string or an obvious packed value near the IP cluster - likely a separate hardcoded constant elsewhere (not chased further this session).

## All three confirmed dead

| IP | Reverse DNS | Status |
|---|---|---|
| `174.129.210.135` | `prdrelayb.collaboratemd.com` | **Reassigned to an unrelated company** - definitively not the game server anymore |
| `50.18.104.153` | `ec2-50-18-104-153.us-west-1.compute.amazonaws.com` | Unallocated/generic EC2 reverse DNS, unreachable |
| `50.18.47.114` | `ec2-50-18-47-114.us-west-1.compute.amazonaws.com` | Same - unallocated EC2, unreachable |

All three were almost certainly real Naughty Dog game-server addresses (AWS EC2, `us-west-1`) at some point - now fully decommissioned/recycled. No live target to connect to or capture against here.

## Files (not committed - gitignored)

- `tools/served_content/net1.bin.psarc.crypt` - the real encrypted file the user supplied, now served by `tools/catch_http.py`.
- `research/net1bin/net1.bin` - the decrypted/extracted plain file, pulled from RPCS3's `dev_hdd0/game/BCUS98174DATA2/USRDIR/net1.bin`.

Both are extracted game content (copyrighted), same reasoning as never committing `EBOOT.elf` itself - kept locally only.

## Possible next step (not yet done - worth deciding on deliberately, not unprompted)

Since `net1.bin` is now sitting decrypted on disk in RPCS3's own virtual filesystem, and `"50.18.104.153"` and `"192.168.1.100"` are **both exactly 13 ASCII characters** (lucky - a direct same-length string patch, no offset/length restructuring needed), it's technically possible to hex-patch the local decrypted `net1.bin` in place to point the fallback server at our own machine instead, without needing to re-encrypt anything (the encrypted `.crypt` download already succeeded once; if the game doesn't re-download on next launch and just reads the cached local file, our patch would take effect). Untested whether the game re-downloads unconditionally each launch (would overwrite the patch) or uses a cached copy - worth testing deliberately if we want to keep pushing this specific path further, since it would let us actually observe/capture whatever protocol runs on port 7320 by standing up something to listen for it.
