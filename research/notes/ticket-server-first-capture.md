# First "ticket-server" Protocol Capture

Via the `net1.bin` hex-patch (redirecting the dead fallback server `50.18.104.153:7320` to our own machine) + `tools/catch_tcp.py` listening on `7320`. Confirms and closes the loop on the very first symptom of this whole investigation ("Error connecting to authentication server") - the server the client calls internally is literally named `ticket-server`, and this is what that error was always actually about, gated behind the entire RPCN-ticket + Content-Delivery chain.

## Raw capture (identical across two separate connection attempts)

```
00000000  11 00 00 00 27 ab 50 86 00 00 00 00 43 0a cd 88   ....'.P.....C...
00000010  00 00 00 00 d0 0f 78 80 74 69 63 6b 65 74 2d 73   ......x.ticket-s
00000020  65 72 76 65 72 00 35 c0 00 00 00 00 01 25 be 1c   erver.5......%..
00000030  00 00 00 00 d0 0f 79 44 00 00 00 00 d0 0f 78 80   ......yD......x.
00000040  00 00 00 00 00 00 00 00 00 00 00 00 00 ac c6 8c   ................
00000050  00 00 00 00 00 00 00 00                           ........
```

88 bytes total. The client sends this single message and does not wait indefinitely for a response - one capture shows the client closing its side immediately after sending, the other shows it holding the socket open until our 10s idle timeout fired (our catcher never replies - not yet a real server for this protocol).

## Initial read (unconfirmed, first pass only)

- `11 00 00 00` (u32 LE = 17) at offset 0 - plausible packet type/opcode or length field. Worth checking against a broader capture set once we can generate more packet types.
- ASCII `"ticket-server\0"` at offset `0x1d` - a service-name string, presumably identifying which backend service this connection is meant to reach (implies a shared connection protocol/multiplexer keyed by service name, rather than one dedicated port per service).
- Several 4-byte values matching the `d0 0f xx xx` pattern seen throughout RPCS3's own log as PPU stack addresses (e.g. `d00f7908`, `d00f7c10` from the `sceNpManagerRequestTicket2` call) - `d0 0f 78 80` (appears twice) and `d0 0f 79 44`. **Byte-identical across both captures**, taken minutes apart - consistent with these being deterministic per-process stack addresses (RPCS3's PPU stack layout is stable across NetInit retries within the same run) rather than random session nonces. Could be intentional opaque client-side handles echoed to the server, or could be an unintentional memory-disclosure artifact (raw stack bytes serialized into the packet by mistake) - not yet determined which.
- Other values (`27ab5086`, `430acd88`, `35c00000`, `0125be1c`, `00acc68c`) not yet identified - candidates: checksums, a client version/build identifier, a session/ticket-related value carried over from the RPCN ticket already obtained, or further stack-adjacent data.

## Not yet done

- No structural parsing/opcode-table work done on this yet - this is one packet, one opcode (whatever `0x11` means), from one specific request. Needs more samples (does the field at offset 0 vary if we can get the client to send a different request type here?) before drawing conclusions about wire format.
- Haven't attempted a response - the client's behavior if we reply with something (even a garbage/malformed response) vs. staying silent is worth observing next, since real protocol behavior after a response could reveal a lot (does it retry, does it proceed past NetInit, does it error immediately on a bad response format?).
