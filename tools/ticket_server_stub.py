#!/usr/bin/env python3
"""Stateful ticket-server stub for TLOU Factions' NetInit handshake (port 7320).

Implements the 4-message handshake reversed via Ghidra decompilation - see
protos/0x11_ticket_server_*.ksy and docs/protocol/0x11_ticket_server_hello.md
for the full evidence trail. Messages C and D are real, verified encrypted
frames now (tools/ticket_cipher.py - key confirmed live via debugger, cipher
bug found and fixed, decrypt confirmed against a real captured NP ticket
containing "comradesean" / "UP9000-BCUS98174_00"). The only remaining
unknown is message D's *content* (never observed) - still a zero-filled
placeholder, but now wrapped in a real, correctly-tagged encrypted frame the
client should actually accept, instead of raw unencrypted zero bytes.
"""
import socket
import sys
import datetime
import threading

sys.path.insert(0, ".")
import ticket_cipher

CANDIDATE_KEY = bytes.fromhex("78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89".replace(" ", ""))

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
        # session_token: this becomes the counter that keys the client's message-C
        # encryption (confirmed - see decrypt_frame below). Using 0, matching the
        # value verified live via debugger and used in the confirmed-working decrypt.
        session_token = 0
        resp1 = bytes([0x22, 0x00, 0x00, 0x00]) + session_token.to_bytes(4, "big")
        conn.sendall(resp1)
        entry += f"-- sent hello_response (8 bytes, session_token={session_token}) --\n{hexdump(resp1)}\n"

        # Message 3: an encrypted frame (see docs/protocol/0x11_ticket_server_hello.md's
        # "Encrypted frame layer" section) - [0x33][pad][BE u16 plaintext_len][16B
        # auth_tag][ciphertext]. Read the fixed 20-byte header first to know exactly
        # how many more bytes to expect, rather than guessing a buffer size.
        header = recv_exact(conn, 20)
        plen = int.from_bytes(header[2:4], "big")
        pad = header[1]
        ciphertext = recv_exact(conn, plen + pad)
        raw3 = header + ciphertext
        entry += f"-- recv message 3, encrypted frame ({len(raw3)} bytes) --\n{hexdump(raw3)}\n"

        plaintext, tag_ok, _, computed_tag, embedded_tag = ticket_cipher.decrypt_frame(
            CANDIDATE_KEY, session_token, raw3)
        entry += f"   tag_ok={tag_ok} computed_tag={computed_tag.hex()} embedded_tag={embedded_tag.hex()}\n"
        entry += f"   decrypted plaintext ({len(plaintext)} bytes): {plaintext!r}\n"
        ticket_data = plaintext

        # Message 4: a real encrypted frame, keyed by client_nonce (the client's
        # receive-side counter, confirmed - see decrypt_frame's docstring/the
        # companion doc). Content is still an unconfirmed placeholder (16 zero
        # bytes) - only the crypto wrapper is verified, not what should be inside.
        frame_d, _ = ticket_cipher.encrypt_frame(CANDIDATE_KEY, client_nonce, b"\x00" * 16)
        conn.sendall(frame_d)
        entry += f"-- sent ticket_submit_response, encrypted frame ({len(frame_d)} bytes) --\n{hexdump(frame_d)}\n"

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
