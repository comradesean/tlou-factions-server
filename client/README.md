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

The game reaches its content/social backends by hostname; redirect those to your
backend's IP so `http_gateway` (:80) and the Facebook stand-in answer them. At
minimum (`&&&`-separated):

- S3 content: `t1.final.prod.s3.amazonaws.com`, `t1.patch.s3.amazonaws.com`,
  `s3.amazonaws.com`, `t1.campaign.config.s3.amazonaws.com` → `<backend-ip>`
- Facebook: `graph.facebook.com` (+ optionally `api.facebook.com`,
  `graph-video.facebook.com`) → `<backend-ip>`

The sibling services (`ticket`/`leaderboard`/`facebook-server` :7320,
`session_manager` :7314, `location` :7312, `voice` :7313) come from `net1.bin` as
literal IPs, which this build already points at the backend host. The full,
authoritative host list and the RPCS3 DNS-hook details are in
**[docs/capture-howto.md](../docs/capture-howto.md)**.

## 4. Install the game patches

Copy the `patch.yml` files from **[patches/](patches/)** into RPCS3's `patches/`
folder and enable them (RPCS3 → right-click the game → Manage Game Patches).
See **[patches/README.md](patches/README.md)** for what each does and how to
verify:

- `facebook_stub_patch.yml` — makes the "Connect to Facebook" flow succeed
  offline and routes the Graph calls to the local stand-in.
- `minplayers_patch.yml` — lowers the find-match minimum (2-client dev testing).
