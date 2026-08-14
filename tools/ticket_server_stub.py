#!/usr/bin/env python3
"""Stateful ticket-server stub for TLOU Factions' NetInit handshake (port 7320).

Implements the 4-message handshake reversed via Ghidra decompilation - see
protos/0x11_ticket_server_*.ksy and docs/protocol/0x11_ticket_server_hello.md
for the full evidence trail. Response CONTENT beyond the required 0x22 magic
byte is UNCONFIRMED - this is a best-guess (zero-filled) placeholder
implementation for live testing, not a verified-correct server. The point is
to get past the client's hard "abort unless first response byte is 0x22"
check and observe what it does next, iterating on real client reactions.
"""
import socket
import sys
import datetime
import threading

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7320
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/tcp_catch.log"


def hexdump(data):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"  {i:08x}  {hexpart:<48}  {asciipart}")
    return "\n".join(lines)


def recv_exact(conn, n, timeout=10):
    conn.settimeout(timeout)
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError(f"peer closed after {len(data)}/{n} bytes (wanted {n})")
        data += chunk
    return data


def handle(conn, addr, log_lock, log):
    ts = datetime.datetime.now().isoformat()
    entry = f"==== {ts} connection from {addr[0]}:{addr[1]} ====\n"
    try:
        # Message 1: 88-byte hello (protos/0x11_ticket_server_hello.ksy)
        hello = recv_exact(conn, 88)
        entry += f"-- recv hello (88 bytes) --\n{hexdump(hello)}\n"
        opcode = hello[0]
        client_nonce = int.from_bytes(hello[4:8], "big")
        service_name = hello[24:88].split(b"\x00", 1)[0].decode("ascii", "replace")
        entry += f"   opcode=0x{opcode:02x} client_nonce=0x{client_nonce:08x} service_name={service_name!r}\n"

        # Message 2: our 8-byte response (0x22_ticket_server_hello_response.ksy)
        # ack_magic MUST be 0x22 or the client aborts immediately - confirmed.
        # unknown1(3) + session_token(4): content unconfirmed, zero placeholder.
        resp1 = bytes([0x22, 0x00, 0x00, 0x00]) + (0).to_bytes(4, "big")
        conn.sendall(resp1)
        entry += f"-- sent hello_response (8 bytes) --\n{hexdump(resp1)}\n"

        # Message 3: diagnostic-first. Don't assume the 2-byte-length-prefix schema
        # yet - do a raw, unstructured recv with a generous timeout and log exactly
        # what arrives, so a wrong assumption here is visible instead of silently
        # causing a 10s stall (as it did the first time this was tried: parsed
        # "ticket_length=13058" from what should have been a ~248-byte NP ticket).
        conn.settimeout(15)
        raw3 = conn.recv(65536)
        entry += f"-- recv message 3, raw, unstructured ({len(raw3)} bytes) --\n{hexdump(raw3)}\n"
        if len(raw3) >= 2:
            as_be16 = int.from_bytes(raw3[:2], "big")
            entry += f"   first 2 bytes as BE u16 = {as_be16} (sanity check against the ticket_length hypothesis)\n"
        ticket_data = raw3

        # Message 4: our 16-byte response (ticket_server_ticket_submit_response.ksy)
        # Content fully unconfirmed - zero placeholder.
        resp2 = b"\x00" * 16
        conn.sendall(resp2)
        entry += f"-- sent ticket_submit_response (16 bytes) --\n{hexdump(resp2)}\n"

        # Handshake complete per current understanding - watch for anything further
        # (a 5th message would mean our understanding is incomplete).
        conn.settimeout(10)
        while True:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                entry += "  (10s idle after handshake, closing)\n"
                break
            if not chunk:
                entry += "  (connection closed by peer after handshake)\n"
                break
            entry += f"-- UNEXPECTED extra data after handshake ({len(chunk)} bytes) --\n{hexdump(chunk)}\n"
    except (ConnectionError, socket.timeout, OSError) as e:
        entry += f"  (error/early close: {e})\n"
    finally:
        conn.close()
        with log_lock:
            print(entry, flush=True)
            log.write(entry + "\n")
            log.flush()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Stateful ticket-server stub listening on 0.0.0.0:{PORT}, logging to {LOG_PATH}", flush=True)

    log_lock = threading.Lock()
    with open(LOG_PATH, "a", buffering=1) as log:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
