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
import os
import socket
import sqlite3
import sys
import datetime
import threading

sys.path.insert(0, ".")
import ticket_cipher

CANDIDATE_KEY = bytes.fromhex("78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89".replace(" ", ""))

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7320
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/mnt/f/ClaudeHole/tlou_factions/captures/tcp_catch.log"

# Persistent leaderboard score store (see research/notes/
# 2026-08-17-leaderboard-server-protocol.md). leaderboard-server multiplexes on
# THIS listener (same 0x11 sibling family / same ip:port as ticket-server); the
# client sends its four verbs as ordinary post-hello encrypted frames, which the
# existing frame path already decrypts. We only need to parse the verb and answer
# with real '+'-prefixed rows instead of the zero placeholder.
LEADERBOARD_DB = os.environ.get(
    "TLOU_LEADERBOARD_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaderboard_scores.sqlite"))


class ScoreStore:
    """Tiny thread-safe score store keyed by (board_id, player). One row per
    player per board; leaderboard-update upserts, get/range read back."""

    def __init__(self, path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS scores ("
            " board_id INTEGER NOT NULL,"
            " player   TEXT    NOT NULL,"
            " score    INTEGER NOT NULL,"
            " blob     TEXT    NOT NULL DEFAULT '',"
            " PRIMARY KEY (board_id, player))")
        self._db.commit()

    def update(self, board_id, player, score, blob):
        with self._lock:
            self._db.execute(
                "INSERT INTO scores (board_id, player, score, blob) VALUES (?,?,?,?) "
                "ON CONFLICT(board_id, player) DO UPDATE SET score=excluded.score, "
                "blob=excluded.blob",
                (board_id, player, score, blob))
            self._db.commit()

    def lookup(self, board_id, player):
        """Return (rank0, score, blob) for one player, or None if absent.
        rank0 is 0-based (count of strictly-higher scores) because the GET
        parser stores rank = atoi(<wire>) + 1."""
        with self._lock:
            row = self._db.execute(
                "SELECT score, blob FROM scores WHERE board_id=? AND player=?",
                (board_id, player)).fetchone()
            if row is None:
                return None
            score, blob = row
            rank0 = self._db.execute(
                "SELECT COUNT(*) FROM scores WHERE board_id=? AND score>?",
                (board_id, score)).fetchone()[0]
            return rank0, score, blob

    def total(self, board_id):
        with self._lock:
            return self._db.execute(
                "SELECT COUNT(*) FROM scores WHERE board_id=?", (board_id,)).fetchone()[0]

    def page(self, board_id, start, end):
        """Rows [start, end] inclusive, ranked by score desc. Returns list of
        (player, score, blob)."""
        if end < start:
            return []
        with self._lock:
            return self._db.execute(
                "SELECT player, score, blob FROM scores WHERE board_id=? "
                "ORDER BY score DESC, player ASC LIMIT ? OFFSET ?",
                (board_id, end - start + 1, start)).fetchall()


STORE = ScoreStore(LEADERBOARD_DB)


def build_leaderboard_response(cmd):
    """Map one decoded leaderboard command line to the ASCII response the client
    parses. Response lines are space-separated, '+'-prefixed, '\\n'-terminated
    (see the protocol note §2-§3). Returns (response_str, log_note)."""
    tokens = cmd.strip().split(" ")
    verb = tokens[0] if tokens else ""

    if verb == "leaderboard-update":
        # leaderboard-update <board> <npid> <score:s64> <base64-blob>
        # Reply body is ignored by the client (single bounded recv); it only
        # needs some bytes. Persist the score.
        try:
            board = int(tokens[1]); npid = tokens[2]; score = int(tokens[3])
            blob = tokens[4] if len(tokens) > 4 else ""
            STORE.update(board, npid, score, blob)
            return "+0\n", f"stored board={board} {npid!r} score={score}"
        except (IndexError, ValueError) as e:
            return "+0\n", f"malformed update ({e})"

    if verb == "leaderboard-get":
        # leaderboard-get <board> 1 <name0> <name1> ...
        try:
            board = int(tokens[1])
        except (IndexError, ValueError):
            return "", "malformed get"
        names = tokens[3:]  # tokens[2] is the constant version flag "1"
        lines = []
        found = 0
        for name in names:
            row = STORE.lookup(board, name)
            if row is not None:
                rank0, score, blob = row
                lines.append(f"+{rank0} {name} {score} {blob}\n")
                found += 1
        return "".join(lines), f"get board={board} names={len(names)} found={found}"

    if verb == "leaderboard-range":
        # leaderboard-range <board> <start> <end> 1
        try:
            board = int(tokens[1]); start = int(tokens[2]); end = int(tokens[3])
        except (IndexError, ValueError):
            return "+0\n", "malformed range"
        total = STORE.total(board)
        # Clan/aggregate variant issues "range <board> 0 1": it only wants the
        # board total (a lone "+<total>"). The blob-page variant asks for a real
        # window and parses "+<name> <score> <b64>" rows + a "+<total>".
        if start == 0 and end == 1:
            return f"+{total}\n", f"range(clan) board={board} total={total}"
        rows = STORE.page(board, start, end)
        out = "".join(f"+{name} {score} {blob}\n" for (name, score, blob) in rows)
        out += f"+{total}\n"
        return out, f"range(blob) board={board} [{start},{end}] rows={len(rows)} total={total}"

    # Unknown verb: send a benign empty-board answer rather than hang.
    return "+0\n", f"unknown verb {verb!r}"


def handle_leaderboard(conn, session_token, client_nonce, log_append):
    """Post-hello loop for a leaderboard-server connection. Commands arrive as
    ordinary encrypted frames (same layer as ticket message C), keyed by an
    inbound counter starting at session_token; our replies are keyed by an
    outbound counter starting at client_nonce (same direction convention as the
    ticket handshake's message D). Client sends one verb per connection in
    practice, but we loop so a pipelined connection also works."""
    # The client opens ONE connection per command (get / range / update each
    # arrive on their own connection, live-confirmed) and treats the connection
    # CLOSE (EOF) as end-of-response - the leaderboard read loop re-packs lines
    # until the socket closes. So we must answer the one command and close
    # promptly; holding the socket open makes the leaderboard screen spin until
    # the client times out and drops PSN. Handle exactly one command, then close.
    in_ctr = session_token
    out_ctr = client_nonce
    conn.settimeout(10)
    try:
        header = recv_exact(conn, 20)
    except (ConnectionError, socket.timeout, OSError):
        log_append("  (leaderboard client closed before command)\n")
        return
    plen = int.from_bytes(header[2:4], "big")
    pad = header[1]
    try:
        ciphertext = recv_exact(conn, plen + pad)
    except (ConnectionError, socket.timeout, OSError) as e:
        log_append(f"  (leaderboard truncated frame: {e})\n")
        return
    frame = header + ciphertext
    plaintext, tag_ok, in_ctr, _, _ = ticket_cipher.decrypt_frame(
        CANDIDATE_KEY, in_ctr, frame)
    cmd = plaintext.decode("ascii", "replace")
    log_append(f"-- leaderboard cmd (tag_ok={tag_ok}): {cmd!r}\n")
    response, note = build_leaderboard_response(cmd)
    frame_out, out_ctr = ticket_cipher.encrypt_frame(
        CANDIDATE_KEY, out_ctr, response.encode("ascii", "replace"))
    conn.sendall(frame_out)
    # Signal end-of-response by half-closing our send side (the leaderboard read
    # loop treats connection-close as "response complete"), THEN drain the
    # client's side to a clean FIN/FIN shutdown. A bare close() with the client's
    # own FIN (or any trailing bytes) still unread emits a TCP RST, which the game
    # reads as an abnormal game-server drop -> "You have been disconnected from
    # the game servers." Consuming to EOF first guarantees a graceful close.
    drained = "clean"
    try:
        conn.shutdown(socket.SHUT_WR)
        conn.settimeout(3)
        while conn.recv(256):
            pass
    except socket.timeout:
        drained = "drain-timeout"
    except OSError:
        drained = "peer-reset"
    log_append(f"   -> {note}; replied {len(response)} bytes "
               f"({len(frame_out)}-byte frame); close={drained}")


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

        # leaderboard-server multiplexes on this same listener but speaks the
        # leaderboard line protocol after the hello (not the ticket message-C/D
        # exchange). Branch here; everything above (hello + 8-byte reply) is shared.
        if service_name == "leaderboard-server":
            # Serialize appends into `entry` via a closure so the leaderboard
            # loop's log lines land in the same connection block.
            box = {"entry": entry}
            def log_append(s):
                box["entry"] += s
            handle_leaderboard(conn, session_token, client_nonce, log_append)
            entry = box["entry"]
            return

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
