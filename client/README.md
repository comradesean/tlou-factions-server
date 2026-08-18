# Client setup (RPCS3 side)

To play against the self-hosted backend you need three things on the RPCS3 side:
an RPCN instance, the game's hosts redirected to your backend machine, and the
game patches installed.

## 1. RPCN (NP authentication)

Stock RPCN works unchanged — **no fork needed** (verified). Either:

- use the public service (`np.rpcs3.net`), or
- self-host [RipleyTom/rpcn](https://github.com/RipleyTom/rpcn) for a stable local
  instance: `cargo run --release` (listens on `:31313` by default), then point
  RPCS3's `rpcn.yml` `Host` at that machine. Setting `Verbosity=Trace` in
  `rpcn.cfg` gives full server-side protocol visibility for debugging.

## 2. Run the backend

From the repo root: `docker compose up` (or `sudo ./run.sh`) — see the top-level
README. Note the backend machine's **LAN IP**; RPCS3 must be able to reach it
there (from every client machine).

## 3. Redirect the game's hosts (RPCS3 → Configuration → Network → IP/Hosts switches)

The game reaches its content/social backends by hostname (and a few hardcoded
IPs); redirect those to your backend's IP so `http_gateway` (:80) and the
Facebook stand-in answer them. The copy-pasteable IP/Hosts string — a minimal
log-verified set plus optional belt-and-suspenders extras — is in the
**[top-level README, step 3](../README.md#3-point-rpcs3-at-your-backend)**; paste
it into the IP/Hosts switches field and replace the placeholder IP with your
backend's LAN IP.

Hosts involved (the switch matches **hostnames only** — it hooks DNS resolution):

- **S3 content + Naughty Dog** (`*naughtydog.com`, `*naughty-dog.com`,
  `t1.patch.s3.amazonaws.com`, `t1.campaign.config.s3.amazonaws.com`,
  `t1.final.*.s3.amazonaws.com`, `s3.amazonaws.com`) — served by `http_gateway`.
- **Facebook** (`graph.facebook.com`, `api.facebook.com`, `graph-video.facebook.com`).

The ticket/matchmaking server is **not** redirected here — its address is a
literal IP baked into `net1.bin` that the game connects to directly (no DNS
lookup), so no IP/Hosts entry can reach it. That redirect happens at the content
layer instead: `http_gateway` serves an IP-patched `net1.bin.psarc.crypt` (see
the top-level README step 2). Never put IP addresses in the IP/Hosts field.

Entries are `hostname=ip` joined by `&&`, the hostname side a whole-string regex
(`*` → `.*`, `.` → literal dot); **never prefix a scheme** like `http://`, or the
match silently fails. The DNS-hook mechanics are detailed in
**[docs/capture-howto.md](../docs/capture-howto.md)**.

## 4. Install the game patches

Copy the `patch.yml` files from **[patches/](patches/)** into RPCS3's `patches/`
folder and enable them (RPCS3 → right-click the game → Manage Game Patches).
See **[patches/README.md](patches/README.md)** for what each does and how to
verify:

- `facebook_stub_patch.yml` — makes the "Connect to Facebook" flow succeed
  offline and routes the Graph calls to the local stand-in.
- `minplayers_patch.yml` — lowers the find-match minimum (2-client dev testing).
