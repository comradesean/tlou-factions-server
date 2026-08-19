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
import base64
import os
import socket
import sqlite3
import struct
import sys
import datetime
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_LOGS = os.path.join(_HERE, "logs")
sys.path.insert(0, os.path.join(_HERE, "lib"))
import ticket_cipher

CANDIDATE_KEY = bytes.fromhex("78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89".replace(" ", ""))

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7320
os.makedirs(_LOGS, exist_ok=True)
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "ticket_server.log")

# Persistent leaderboard score store (see research/notes/
# 2026-08-17-leaderboard-server-protocol.md). leaderboard-server multiplexes on
# THIS listener (same 0x11 sibling family / same ip:port as ticket-server); the
# client sends its four verbs as ordinary post-hello encrypted frames, which the
# existing frame path already decrypts. We only need to parse the verb and answer
# with real '+'-prefixed rows instead of the zero placeholder.
LEADERBOARD_DB = os.environ.get(
    "TLOU_LEADERBOARD_DB", os.path.join(_DATA, "leaderboard_scores.sqlite"))


# The leaderboard "blob" (the <base64-metadata> in leaderboard-update / the
# trailing field of each reply row) is NOT opaque: it is a 5-field big-endian
# u32 struct, trailing-zero-truncated on the wire (the client keeps >=1 byte).
# Fields, verified against the on-screen Supply Raid columns (board 406; board
# 404 shares the layout; the clan board 405 reuses the slots but leaves the
# stats zero, its score being MAX CLAN SIZE):
#   [0] best_game  [1] time_played_sec  [2] executions  [3] deaths  [4] rank
# So we decode it into named columns and re-encode on read. We serve the FULL
# 5-field struct (see encode_blob) rather than reproducing the client's
# trailing-zero truncation, so the `rank` field is always present - otherwise a
# rank-0 player's blob has no rank and a peer's Friends-filter view falls back to
# showing their standing instead of 0. `extra` carries any bytes beyond the 5
# fields (none observed) so an unexpected longer blob still survives round-trip.
BLOB_FIELDS = ("best_game", "time_played_sec", "executions", "deaths", "rank")


def decode_blob(b64):
    """base64 blob -> ({field: u32, ...}, extra_bytes). Missing trailing fields
    read back as 0 (the client inflates a memset-0 struct the same way)."""
    try:
        raw = base64.b64decode(b64) if b64 else b""
    except (ValueError, TypeError):
        raw = b""
    extra = raw[20:]
    vals = struct.unpack(">IIIII", raw.ljust(20, b"\x00")[:20])
    return dict(zip(BLOB_FIELDS, vals)), extra


def encode_blob(fields, extra=b""):
    """Named fields -> wire blob. We emit the FULL 5-field struct (we deliberately
    do NOT reproduce the client's trailing-zero truncation), so the `rank` field
    is always present.

    Why: a client trailing-zero-truncates its blob when it submits, so a rank-0
    player ships only 4 fields (no rank). If we re-served that truncated form, a
    PEER's Friends-filter view - whose leaderboard-get reply carries its own rank
    field - finds no rank in the blob and falls back to showing that player's
    leaderboard STANDING instead of their real rank, while the Global view
    (leaderboard-range, no such field) correctly shows 0. Emitting rank=0
    explicitly puts the field back so both views read the real, decoded rank.
    This changes no stat value; it just serves the fully-decoded record rather
    than the client's compressed wire form."""
    raw = struct.pack(">IIIII", *(int(fields.get(k, 0)) for k in BLOB_FIELDS)) + extra
    return base64.b64encode(raw).decode("ascii")


class ScoreStore:
    """Thread-safe leaderboard store keyed by (board_id, player). One row per
    player per board, holding the score plus the blob's DECODED named fields
    (best_game / time_played_sec / executions / deaths / rank) - no opaque blob.
    leaderboard-update decodes into these columns; get/range re-encode the exact
    wire blob from them."""

    _COLS = BLOB_FIELDS + ("extra",)

    def __init__(self, path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS scores ("
            " board_id INTEGER NOT NULL,"
            " player   TEXT    NOT NULL,"
            " score    INTEGER NOT NULL,"
            " best_game       INTEGER NOT NULL DEFAULT 0,"
            " time_played_sec INTEGER NOT NULL DEFAULT 0,"
            " executions      INTEGER NOT NULL DEFAULT 0,"
            " deaths          INTEGER NOT NULL DEFAULT 0,"
            " rank            INTEGER NOT NULL DEFAULT 0,"
            " extra    TEXT    NOT NULL DEFAULT '',"
            " PRIMARY KEY (board_id, player))")
        self._migrate()
        self._db.commit()

    def _migrate(self):
        """Upgrade a pre-existing opaque-`blob` table: add the named columns and
        backfill them by decoding each stored blob. Idempotent; the old `blob`
        column is left in place (SQLite can't drop it) but no longer read."""
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(scores)")}
        for name, decl in (("best_game", "INTEGER NOT NULL DEFAULT 0"),
                           ("time_played_sec", "INTEGER NOT NULL DEFAULT 0"),
                           ("executions", "INTEGER NOT NULL DEFAULT 0"),
                           ("deaths", "INTEGER NOT NULL DEFAULT 0"),
                           ("rank", "INTEGER NOT NULL DEFAULT 0"),
                           ("extra", "TEXT NOT NULL DEFAULT ''")):
            if name not in cols:
                self._db.execute(f"ALTER TABLE scores ADD COLUMN {name} {decl}")
        if "blob" in cols:
            for board, player, blob in self._db.execute(
                    "SELECT board_id, player, blob FROM scores").fetchall():
                f, extra = decode_blob(blob)
                self._db.execute(
                    "UPDATE scores SET best_game=?, time_played_sec=?, executions=?, "
                    "deaths=?, rank=?, extra=? WHERE board_id=? AND player=?",
                    (f["best_game"], f["time_played_sec"], f["executions"],
                     f["deaths"], f["rank"], base64.b64encode(extra).decode("ascii"),
                     board, player))

    def update(self, board_id, player, score, blob):
        f, extra = decode_blob(blob)
        with self._lock:
            self._db.execute(
                "INSERT INTO scores (board_id, player, score, best_game, "
                "time_played_sec, executions, deaths, rank, extra) "
                "VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(board_id, player) DO UPDATE SET score=excluded.score, "
                "best_game=excluded.best_game, time_played_sec=excluded.time_played_sec, "
                "executions=excluded.executions, deaths=excluded.deaths, "
                "rank=excluded.rank, extra=excluded.extra",
                (board_id, player, score, f["best_game"], f["time_played_sec"],
                 f["executions"], f["deaths"], f["rank"],
                 base64.b64encode(extra).decode("ascii")))
            self._db.commit()

    def _blob_of(self, row):
        """Re-encode the exact wire blob from a (best_game..rank, extra) row."""
        f = dict(zip(BLOB_FIELDS, row[:5]))
        extra = base64.b64decode(row[5]) if row[5] else b""
        return encode_blob(f, extra)

    def lookup(self, board_id, player):
        """Return (rank0, score, blob) for one player, or None if absent.
        rank0 is 0-based (count of strictly-higher scores) because the GET
        parser stores rank = atoi(<wire>) + 1."""
        with self._lock:
            row = self._db.execute(
                "SELECT score, best_game, time_played_sec, executions, deaths, "
                "rank, extra FROM scores WHERE board_id=? AND player=?",
                (board_id, player)).fetchone()
            if row is None:
                return None
            score = row[0]
            blob = self._blob_of(row[1:])
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
            rows = self._db.execute(
                "SELECT player, score, best_game, time_played_sec, executions, "
                "deaths, rank, extra FROM scores WHERE board_id=? "
                "ORDER BY score DESC, player ASC LIMIT ? OFFSET ?",
                (board_id, end - start + 1, start)).fetchall()
        return [(player, score, self._blob_of(rest))
                for (player, score, *rest) in rows]


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
        # Total first, then rows (protocol note §7). Entry ranks are positional
        # (start+index+1) so the lone-total line's position doesn't affect them,
        # but total-first matches the recommended/likely-retail order.
        out = f"+{total}\n"
        out += "".join(f"+{name} {score} {blob}\n" for (name, score, blob) in rows)
        return out, f"range(blob) board={board} [{start},{end}] rows={len(rows)} total={total}"

    # Unknown verb: send a benign empty-board answer rather than hang.
    return "+0\n", f"unknown verb {verb!r}"


def handle_line_service(conn, session_token, client_nonce, log_append,
                        label, builder):
    """Post-hello loop shared by every 0x11 sibling LINE service (leaderboard,
    facebook, heartbeat, report).

    Commands arrive as ordinary encrypted frames (same layer as ticket message
    C), keyed by an inbound counter starting at session_token; our replies are
    keyed by an outbound counter starting at client_nonce (the same direction
    convention as the ticket handshake's message D).

    Two rules, both live-derived and both non-negotiable for this family:

      * every reply body is terminated by a NUL - the end-of-response
        sentinel. Live-derived 2026-08-17 from three behaviours: NUL-only
        placeholder replies -> the client closes clean; '+'-rows WITHOUT a NUL
        plus a prompt EOF -> the rows RENDER but the EOF raises Error 9
        ("disconnected from game servers"); rows without a NUL and no EOF ->
        the screen spins forever. So the client parses until the NUL (its own
        send side is strlen/NUL-terminated ASCII too), then closes;
      * the SERVER NEVER CLOSES FIRST. LIVE-DISPROVED 2026-08-17: half-closing
        after the reply made the client report "recv() failed (errno=0)" ->
        "Error 9" -> "You have been disconnected from the game servers". So we
        reply and then hold the socket open until the client closes (or goes
        idle for 30 s).

    `builder(cmd) -> (response_str, log_note)` supplies the service-specific
    grammar; everything else is identical across services.
    """
    in_ctr = session_token
    out_ctr = client_nonce
    served = 0
    while True:
        try:
            header = recv_exact(conn, 20, timeout=30)
        except socket.timeout:
            log_append(f"  ({label} idle 30s after {served} command(s), closing)\n")
            return
        except (ConnectionError, OSError):
            if served == 0:
                log_append(f"  ({label} client closed before command)\n")
            else:
                log_append(f"  ({label} client closed after {served} command(s))\n")
            return
        plen = int.from_bytes(header[2:4], "big")
        pad = header[1]
        try:
            ciphertext = recv_exact(conn, plen + pad)
        except (ConnectionError, socket.timeout, OSError) as e:
            log_append(f"  ({label} truncated frame: {e})\n")
            return
        frame = header + ciphertext
        plaintext, tag_ok, in_ctr, _, _ = ticket_cipher.decrypt_frame(
            CANDIDATE_KEY, in_ctr, frame)
        cmd = plaintext.decode("ascii", "replace")
        log_append(f"-- {label} cmd (tag_ok={tag_ok}): {cmd!r}\n")
        # Strip any trailing NUL before parsing. Every captured request line so
        # far ends at its '\n' with no NUL inside the frame (e.g. the 22-byte
        # 'heartbeat comradesean\n'), but the client's send side is
        # strlen/NUL-terminated ASCII, so a NUL landing inside the frame is a
        # legal shape - and it would otherwise be glued onto the LAST token
        # (the online id, or the leaderboard blob) and silently corrupt it.
        response, note = builder(cmd.rstrip("\x00"))
        frame_out, out_ctr = ticket_cipher.encrypt_frame(
            CANDIDATE_KEY, out_ctr, response.encode("ascii", "replace") + b"\x00")
        conn.sendall(frame_out)
        served += 1
        log_append(f"   -> {note}; replied {len(response)} bytes "
                   f"({len(frame_out)}-byte frame); holding for client close\n")


def handle_leaderboard(conn, session_token, client_nonce, log_append):
    """leaderboard-server post-hello loop. See handle_line_service for the
    frame/keying/NUL-sentinel/hold-for-client-close discipline, all of which was
    first derived here (2026-08-17): '+'-rows without a trailing NUL render but
    then hang, and a server-initiated EOF raises the client's "recv() failed
    (errno=0)" -> "Error 9" -> "You have been disconnected from the game
    servers" the instant the leaderboard screen is opened."""
    handle_line_service(conn, session_token, client_nonce, log_append,
                        "leaderboard", build_leaderboard_response)


def build_facebook_response(cmd):
    """Map one decoded facebook-server command to the ASCII '+'-line response the
    client parses. facebook-server maps PSN NpIds <-> Facebook ids for friend
    presence (facebook.cpp FUN_00ac17b0 / FUN_003538c0); this stub keeps no real
    mappings, so it answers 'not linked' for every query - semantically correct
    locally (no PSN friend is Facebook-linked here) and, crucially, a well-formed
    reply so the CLIENT closes first (a server-initiated EOF raises the same
    Error 9 as leaderboard - see handle_facebook). Returns (response_str, note)."""
    tokens = cmd.strip().split(" ")
    verb = tokens[0] if tokens else ""

    if verb == "facebook-set":
        # facebook-set <npid> <fbid>: client reports its own NpId<->fbid mapping.
        # Client does one bounded recv; it only needs some bytes. Ack.
        return "+0\n", f"set {' '.join(tokens[1:])!r} (ack)"

    if verb == "facebook-get-fid":
        # facebook-get-fid <npid0> <npid1> ...: one '+'-line per queried NpId
        # (single numeric field = fbid/online flag). 0 = not linked / offline.
        npids = tokens[1:]
        return "".join("+0\n" for _ in npids), f"get-fid n={len(npids)} (all unlinked)"

    if verb == "facebook-get-npid":
        # facebook-get-npid <fbid0> ...: resolve FB ids -> PSN NpIds. We answer
        # NO matches (empty). DO NOT hand back fabricated NpIds: the client feeds
        # each resolved id into the real NP/presence machinery (sceNpLookup + the
        # Presence Thread), and a non-existent account crashes it - observed as a
        # jump to 0x30303030 ("0000", bytes of a fake "fbf000...0" id) -> access
        # violation. "No matches" is the safe, non-crashing answer (no FB friend
        # maps to a PSN player here). See research/notes/2026-08-17-facebook-connect-flow.md.
        fbids = tokens[1:]
        return "", f"get-npid n={len(fbids)} (no matches - fake NpIds crash the Presence Thread)"

    # Unknown facebook verb: benign ack rather than hang/close.
    return "+0\n", f"unknown facebook verb {verb!r}"


# ---------------------------------------------------------------------------
# heartbeat-server (2026-08-19)
# ---------------------------------------------------------------------------
# The most-used sibling service by volume: 258 of the 452 captured hellos.
# Request grammar is LIVE-CONFIRMED (protos/0x11_heartbeat_line.ksy): one line,
#   heartbeat <online_id>\n
# built by FUN_00353cd8 from the one-field format string "heartbeat %s" at VMA
# 0xe7a100, whose single %s argument is the global at 0x13835e0 (= the
# matchmaking singleton 0x13835c0 + 0x20, the local SceNpId online-id handle).
# Captured plaintext: 'heartbeat comradesean\n'.
#
# WHAT IT IS FOR: a liveness beacon. The client periodically tells the
# matchmaking backend that this account is still online so the backend can keep
# it in its presence tables and time out stale sessions. So the handler's real
# job is to KEEP THAT RECORD, which is what PRESENCE below is.
#
# RESPONSE: the client does ONE bounded 256-byte recv and never parses the
# result (no response-parse loop anywhere in FUN_00353cd8), so any bytes
# satisfy it. We answer in the family's shape anyway - a '+'-prefixed line plus
# the NUL sentinel - because that is what every other sibling reader expects and
# it costs nothing to stay consistent.
PRESENCE_LOCK = threading.Lock()
# online_id -> {"first_seen": epoch, "last_seen": epoch, "beats": int}
PRESENCE = {}


def record_presence(online_id, now=None):
    """Refresh (or create) one account's presence/liveness record. In-memory
    only: presence is by definition ephemeral, and nothing else in the server
    reads it across restarts. Returns the updated record."""
    now = time.time() if now is None else now
    with PRESENCE_LOCK:
        rec = PRESENCE.get(online_id)
        if rec is None:
            rec = {"first_seen": now, "last_seen": now, "beats": 0}
            PRESENCE[online_id] = rec
        rec["last_seen"] = now
        rec["beats"] += 1
        return dict(rec)


def build_heartbeat_response(cmd):
    """Map one decoded heartbeat-server line to a reply. Returns (response, note).

    The only verb is `heartbeat <online_id>`. The client ignores the body, so
    the reply is a bare family-shaped ack; the useful work is updating the
    presence record."""
    tokens = cmd.strip().split(" ")
    verb = tokens[0] if tokens else ""

    if verb == "heartbeat" and len(tokens) >= 2:
        online_id = tokens[1]
        rec = record_presence(online_id)
        age = rec["last_seen"] - rec["first_seen"]
        return "+0\n", (f"presence refreshed for {online_id!r} "
                        f"(beat #{rec['beats']}, online {age:.0f}s)")

    if verb == "heartbeat":
        # Verb with no id: nothing to key a presence record on. Still ack, so
        # the client's bounded recv is satisfied and it closes cleanly.
        return "+0\n", "heartbeat with no online_id - acked, nothing recorded"

    return "+0\n", f"unknown heartbeat verb {verb!r} - acked"


def handle_heartbeat(conn, session_token, client_nonce, log_append):
    """heartbeat-server post-hello loop. Same frame layer, NUL sentinel and
    hold-for-client-close discipline as every sibling line service (see
    handle_line_service). This is the lowest-risk service in the family: the
    client does not parse the reply at all."""
    handle_line_service(conn, session_token, client_nonce, log_append,
                        "heartbeat", build_heartbeat_response)


def handle_facebook(conn, session_token, client_nonce, log_append):
    """facebook-server post-hello loop. Same encrypted-frame layer and
    NUL-sentinel / hold-for-client-close discipline as every sibling line
    service (see handle_line_service): a server-initiated EOF here triggers the
    client's 'recv() failed (errno=0)' -> Error 9 disconnect, seen in TTY.log
    during a Facebook connect."""
    handle_line_service(conn, session_token, client_nonce, log_append,
                        "facebook", build_facebook_response)


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


# Service-name -> post-hello handler for the 0x11 sibling LINE services. Names
# are read verbatim out of the 88-byte hello (bytes 24:88, NUL-terminated).
# Six services have been observed live; single-player-server has never opened a
# connection, and ticket-server itself uses the message-C/D handshake below
# rather than a line protocol, so neither appears here.
LINE_SERVICE_HANDLERS = {
    "leaderboard-server": handle_leaderboard,
    "facebook-server": handle_facebook,
    "heartbeat-server": handle_heartbeat,
}


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

        # Several 0x11 siblings multiplex on THIS listener but speak the
        # line protocol after the hello, not the ticket message-C/D exchange.
        # Branch here; everything above (hello + 8-byte reply) is shared. Every
        # one of them must hold the socket open until the CLIENT closes - a
        # server-initiated EOF is the client's error path (Error 9 /
        # "disconnected from the game servers"). See handle_line_service.
        handler = LINE_SERVICE_HANDLERS.get(service_name)
        if handler is not None:
            # Serialize appends into `entry` via a closure so the service
            # loop's log lines land in the same connection block.
            box = {"entry": entry}

            def log_append(text):
                box["entry"] += text

            handler(conn, session_token, client_nonce, log_append)
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
