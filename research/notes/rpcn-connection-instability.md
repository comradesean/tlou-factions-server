# RPCN Connection Instability (not an auth failure)

Found in `log/RPCS3.log` (RPCS3 install dir - not committed, this file lives in the local RPCS3 install and can be large/rotate; note the finding here instead).

## What's actually happening

This is **not** a credential/config/auth problem. The pattern, repeated **77 times** across one RPCS3 run:

```
rpcn: connect: Attempting to connect
rpcn: connect: Connection successful
rpcn: connect: Handshake successful
rpcn: connect: Waiting for protocol version
rpcn: connect: Protocol version matches
rpcn: Attempting to login!
rpcn: You are now logged in RPCN(comradesean | comradesean)!    <- succeeds every time
  ... (anywhere from ~1 second to ~37 minutes later) ...
rpcn: recv failed: connection reset by server   (72 occurrences)
  -or-
rpcn: Recvn was forcefully aborted              (4 occurrences)
rpcn: Disconnected
  -> auto-reconnects, repeats from the top
```

`sceNpManagerRequestTicket2` -> `SCE_NP_MANAGER_EVENT_GOT_TICKET` also succeeds cleanly every cycle. The only real *errors* logged (`SCE_NP_SIGNALING_ERROR_CTX_NOT_FOUND`, `SCE_NP_BASIC_ERROR_NOT_REGISTERED`) are teardown/cleanup failures that happen *because* the connection was just reset mid-connection - consequences, not causes.

**Conclusion:** the public RPCN service (`np.rpcs3.net`) is resetting this client's connection repeatedly and at irregular intervals (no fixed period - ranges from ~1s to ~37min between reset events, inconsistent with a simple NAT/keepalive timeout). This looks like public-server-side instability, not a local misconfiguration - the NPID (`comradesean`) authenticates successfully every single time before being dropped.

## Log timestamp note

`RPCS3.log` timestamps (`H:MM:SS.ffffff`) are **elapsed time since RPCS3 launch**, not wall-clock time - don't try to correlate them directly against a Wireshark capture's absolute timestamps without converting.

## Implication for capture runs

Live capture attempts against the public RPCN service may need multiple tries / a longer capture window to land inside a stable-enough connection stretch, purely due to this instability - not a sign anything in our setup is wrong. If this becomes a recurring blocker for getting clean captures, revisit the earlier "public vs self-hosted RPCN" decision (`docs/capture-howto.md`) - a self-hosted local RPCN instance would remove this variable entirely for testing purposes, even though the public service is what real players actually hit.
