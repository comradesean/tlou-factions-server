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
from rotating_log import RotatingLog, capped_appender

CANDIDATE_KEY = bytes.fromhex("78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89".replace(" ", ""))

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 7320
os.makedirs(_LOGS, exist_ok=True)
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(_LOGS, "ticket_server.log")

# Ceiling on the per-connection log block held in memory until the connection
# closes. A real handshake (hello + two frames) logs a few kilobytes, and the
# line services log one short command line per request, so this never truncates
# legitimate traffic. Without it, the post-handshake watch loop hexdumps
# everything a peer sends forever: a hello naming a service that is neither
# ticket-server nor in LINE_SERVICE_HANDLERS falls through to that loop, and
# `decrypt_frame`'s tag_ok is recorded but never enforced, so no valid
# encryption is needed to stream unbounded bytes into the block until the
# process is OOM-killed (which takes the whole backend down through run_all's
# die-together supervision). Past the cap only a dropped-byte count is kept.
MAX_LOG_CHARS = int(os.environ.get("TLOU_TICKET_MAX_LOG_CHARS", str(256 * 1024)))

# Cap on concurrent handler threads, gating accept() rather than just the
# thread start: an unaccepted connection holds no file descriptor of ours and
# waits in the kernel's listen backlog instead, so a flood of idle connections
# cannot exhaust this process's fd limit. Same pattern and reasoning as
# http_gateway.py's MAX_CONCURRENT_HANDLERS. Each player holds several
# concurrent sibling-service connections here (ticket, leaderboard, facebook,
# heartbeat, report, gamelist), so this is set well above the per-player count.
MAX_CONCURRENT_HANDLERS = int(os.environ.get("TLOU_TICKET_MAX_HANDLERS", "128"))
_handler_slots = threading.Semaphore(MAX_CONCURRENT_HANDLERS)

# Persistent leaderboard score store (see research/notes/
# 2026-08-17-leaderboard-server-protocol.md). leaderboard-server multiplexes on
# THIS listener (same 0x11 sibling family / same ip:port as ticket-server); the
# client sends its four verbs as ordinary post-hello encrypted frames, which the
# existing frame path already decrypts. We only need to parse the verb and answer
# with real '+'-prefixed rows instead of the zero placeholder.
LEADERBOARD_DB = os.environ.get(
    "TLOU_LEADERBOARD_DB", os.path.join(_DATA, "leaderboard_scores.sqlite"))


# The leaderboard "blob" (the <base64-metadata> in leaderboard-update / the
# trailing field of each reply row) is NOT opaque: it is an array of big-endian
# u32 slots, trailing-zero-truncated on the wire (the client keeps >=1 byte).
# Every blob observed is a whole number of u32s - no partial slot, no remainder.
# Slots, verified against the on-screen Supply Raid columns (board 406; board
# 404 shares the layout; the clan board 405 reuses the slots but leaves the
# stats zero, its score being MAX CLAN SIZE):
#   [0] best_game  [1] time_played_sec  [2] executions  [3] deaths  [4] rank
#   [5..8] MODE-SPECIFIC, semantics unknown. Interrogation (board 407) sends 8-9
#          slots where Supply Raid sends 4-5. Live 2026-08-19:
#            407 comradesean -> (4485, 3607, 42, 17, 2, 0, 5, 1)
#            407 mgnomad2    -> (3740, 3144, 16, 38, 1, 0, 4, 0, 5)
#          Named slot_5..slot_8 and stored as integers, NOT as an opaque tail:
#          every slot the client sends gets its own decoded column. Naming them
#          properly needs a board-407 capture correlated with the on-screen
#          Interrogation columns, the same way 406 was pinned.
# The blob is decomposed on receipt and re-encoded on read; nothing is stored in
# its wire form. (A legacy opaque `blob` column existed until 2026-08-19 and is
# rebuilt away by _migrate - see that method for the damage it caused.)
BLOB_FIELDS = ("best_game", "time_played_sec", "executions", "deaths", "rank")
EXTRA_SLOTS = ("slot_5", "slot_6", "slot_7", "slot_8")
ALL_SLOTS = BLOB_FIELDS + EXTRA_SLOTS
MIN_EMITTED_SLOTS = len(BLOB_FIELDS)


def decode_blob(b64):
    """base64 blob -> {slot_name: u32, ...}.

    Trailing-zero truncation carries NO information: the client simply declines
    to spend bytes on zeros, so a slot the wire omits IS zero. We decode it as 0
    and store 0 - there is no truncated-vs-untruncated distinction to preserve.
    Slots past slot_8 are dropped; none have ever been observed, and a silent
    opaque tail is exactly what this rewrite removed. If one ever appears, widen
    EXTRA_SLOTS rather than reintroducing a catch-all column."""
    try:
        raw = base64.b64decode(b64) if b64 else b""
    except (ValueError, TypeError):
        raw = b""
    usable = min(len(raw) // 4, len(ALL_SLOTS))
    vals = struct.unpack(">%dI" % usable, raw[:usable * 4]) if usable else ()
    fields = dict(zip(ALL_SLOTS, vals))
    for name in ALL_SLOTS:
        fields.setdefault(name, 0)
    return fields


def encode_blob(fields):
    """Named slots -> wire blob. The emitted length is DERIVED from the data:
    enough slots to carry every non-zero value, with a floor of the five
    universally-named ones.

    This is not padding and not a deviation from what the client sent - a slot
    the client truncated away is zero, and we serve it back as zero. The floor
    matters because a peer's Friends-filter view reads `rank` out of the blob;
    if the field is absent it falls back to showing that player's leaderboard
    STANDING instead of their real rank, while the Global view (leaderboard-
    range, which carries no such field) correctly shows 0. Emitting the decoded
    zero puts both views on the same value.

    Every blob whose data reaches slot N rebuilds byte-identically, including
    Interrogation's 8- and 9-slot forms."""
    n = MIN_EMITTED_SLOTS
    for i, name in enumerate(ALL_SLOTS):
        if int(fields.get(name, 0)):
            n = max(n, i + 1)
    return base64.b64encode(
        struct.pack(">%dI" % n, *(int(fields.get(k, 0)) for k in ALL_SLOTS[:n]))
    ).decode("ascii")


class ScoreStore:
    """Thread-safe leaderboard store keyed by (board_id, player). One row per
    player per board, holding the score plus EVERY decoded slot of the wire blob
    (best_game / time_played_sec / executions / deaths / rank / slot_5..slot_8).

    THE BLOB NEVER EXISTS SERVER-SIDE. It is decomposed on receipt and rebuilt
    on read; no column holds wire-form or base64 data. Anything the client sends
    that we cannot name still gets its own integer column - never a catch-all."""

    _SLOT_COLS = ALL_SLOTS

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
            " slot_5          INTEGER NOT NULL DEFAULT 0,"
            " slot_6          INTEGER NOT NULL DEFAULT 0,"
            " slot_7          INTEGER NOT NULL DEFAULT 0,"
            " slot_8          INTEGER NOT NULL DEFAULT 0,"
            " PRIMARY KEY (board_id, player))")
        self._migrate()
        self._db.commit()

    def _migrate(self):
        """One-time rebuild of any older schema into the slot columns, then the
        legacy columns are DROPPED so they can never be read back as truth.

        History (2026-08-19): an earlier schema kept the raw base64 `blob` and an
        opaque `extra` tail alongside the named columns, and re-derived the named
        columns from `blob` on EVERY startup. SQLite cannot drop a column with
        plain ALTER, so the guard `if "blob" in cols` was true forever and the
        backfill ran every restart - wiping the stats of every row written by the
        current code path, whose `blob` was empty. Live symptom: board 407
        (Interrogation) served a correct score with rank/best-game/time-played/
        executions/deaths all 0. This rebuild removes the crutch entirely rather
        than guarding it: decode once, drop the columns, never look at wire form
        again."""
        cols = {r[1] for r in self._db.execute("PRAGMA table_info(scores)")}
        for name in self._SLOT_COLS:
            if name not in cols:
                self._db.execute(
                    f"ALTER TABLE scores ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
        legacy = [c for c in ("blob", "extra") if c in cols]
        if not legacy:
            return
        # Decode each legacy row ONCE. Prefer the stored blob when present; a row
        # written by the newer code has an empty blob but real slot columns, so
        # it must be left exactly as-is.
        if "blob" in cols:
            for board, player, blob in self._db.execute(
                    "SELECT board_id, player, blob FROM scores "
                    "WHERE blob IS NOT NULL AND blob != ''").fetchall():
                fields = decode_blob(blob)
                self._db.execute(
                    "UPDATE scores SET " +
                    ", ".join(f"{c}=?" for c in ALL_SLOTS) +
                    " WHERE board_id=? AND player=?",
                    tuple(fields[c] for c in ALL_SLOTS) + (board, player))
        if "extra" in cols:
            # An intermediate schema kept slots past rank as a base64 `extra`
            # tail. Decode it into the named trailing slots so nothing is lost
            # when the column is dropped - board 407 rows repaired on 2026-08-19
            # carry their 3-4 Interrogation slots here.
            for board, player, extra in self._db.execute(
                    "SELECT board_id, player, extra FROM scores "
                    "WHERE extra IS NOT NULL AND extra != ''").fetchall():
                try:
                    raw = base64.b64decode(extra)
                except (ValueError, TypeError):
                    continue
                n = min(len(raw) // 4, len(EXTRA_SLOTS))
                if not n:
                    continue
                vals = struct.unpack(">%dI" % n, raw[:n * 4])
                self._db.execute(
                    "UPDATE scores SET " +
                    ", ".join(f"{c}=?" for c in EXTRA_SLOTS[:n]) +
                    " WHERE board_id=? AND player=?",
                    vals + (board, player))
        for c in legacy:
            self._db.execute(f"ALTER TABLE scores DROP COLUMN {c}")

    def update(self, board_id, player, score, blob):
        """Decode the wire blob into slot columns. The blob itself is discarded."""
        fields = decode_blob(blob)
        cols = ALL_SLOTS
        vals = tuple(fields[c] for c in ALL_SLOTS)
        with self._lock:
            self._db.execute(
                "INSERT INTO scores (board_id, player, score, " +
                ", ".join(cols) + ") VALUES (?,?,?," +
                ",".join("?" * len(cols)) + ") "
                "ON CONFLICT(board_id, player) DO UPDATE SET score=excluded.score, " +
                ", ".join(f"{c}=excluded.{c}" for c in cols),
                (board_id, player, score) + vals)
            self._db.commit()

    def _blob_of(self, row):
        """Rebuild the wire blob from decoded slot columns."""
        return encode_blob(dict(zip(ALL_SLOTS, row)))

    _SEL = ", ".join(ALL_SLOTS)

    def lookup(self, board_id, player):
        """Return (rank0, score, blob) for one player, or None if absent.
        rank0 is 0-based (count of strictly-higher scores) because the GET
        parser stores rank = atoi(<wire>) + 1."""
        with self._lock:
            row = self._db.execute(
                f"SELECT score, {self._SEL} FROM scores WHERE board_id=? AND player=?",
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
                f"SELECT player, score, {self._SEL} FROM scores WHERE board_id=? "
                "ORDER BY score DESC, player ASC LIMIT ? OFFSET ?",
                (board_id, end - start + 1, start)).fetchall()
        return [(player, score, self._blob_of(rest))
                for player, score, *rest in [(r[0], r[1], *r[2:]) for r in rows]]


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


# ---------------------------------------------------------------------------
# report-server (2026-08-19) - grammar DERIVED FROM THE BINARY
# ---------------------------------------------------------------------------
# A player-standing / ban check, and it exists ONLY IN EBOOT 01.11: neither
# "report-server" nor "is-banned" appears anywhere in 01.00 (byte search of both
# ELFs). All addresses below are 01.11 VMAs (VMA = file offset + 0x10000).
#
# REQUEST - format string "is-banned %s\n" @ 0xeacdd0, adjacent to
# "report-server" @ 0xeacdc0 and the client's own debug line
# "ban response: '%s'\n" @ 0xeacde0. The '\n' is IN the format, which is why the
# captured plaintext is exactly 22 bytes for "comradesean". Sender + parser are
# inline in the big NetInit function, 0x36e1fc-0x36e390.
#
# Live: nine connections over five sessions and two accounts in
# server/logs/ticket_server.log, each from the querying console's own address
# naming its own account (192.168.1.100 -> "is-banned comradesean",
# 192.168.1.121 -> "is-banned mgnomad2"). This is a SELF standing-check, not a
# lookup of a reported opponent.
#
# RESPONSE GRAMMAR, read straight off the parser (each instruction verified
# against the ELF, not just decompiler output):
#
#     +<decimal int><space-or-newline><name-token>
#
#   0x36e1a8  stw -1,916(g_net)    g_net=0x13ba5a0; +916 is the ban index,
#                                  default -1 = NOT banned
#   0x36e28c  li  r5,256           one bounded recv of 256 bytes...
#   0x36e290  bl  0xafacf8         ...which is poll+recv returning on the FIRST
#                                  successful read, then the caller closes. This
#                                  is the heartbeat shape, NOT the leaderboard's
#                                  NUL-sentinel accumulator - so the whole reply
#                                  must arrive in ONE frame.
#   0x36e298  cmpwi cr7,r3,0
#   0x36e29c  ble  0x36e384        n <= 0            -> not banned
#   0x36e2ac  stb  r28,0x388(r9)   buf[n] = 0        (client NUL-terminates at
#                                  the recv length itself; it does NOT require a
#                                  NUL from us)
#   0x36e2c8  lbz  r0,0x388(r1)    buf[0]
#   0x36e2cc  cmpwi cr7,r0,43      ...must be '+'
#   0x36e2d0  bne  0x36e388        not '+'           -> not banned
#   0x36e2dc  addi r3,r1,0x389     strtok_r starts at buf+1
#   0x36e2ec  bl   0xe72d80        strtok_r(buf+1, " \n") -> token1
#             bl   0xe75d78        strtol(token1, 10) -> g_net+920
#             bl   0xe72d80        strtok_r(NULL, " \n")  -> token2
#             loop strcmp(token2, pReportArray[i].name); on a match store the
#             integer at g_net+920 and the matching index i at g_net+916
#
# THERE IS NO 0/1 BOOLEAN. The account is banned IFF the reply starts with '+'
# AND its second token strcmp-matches an entry in the DC-resident pReportArray
# table (resolved by symbol hash 0xFFAC56F2; the literal "pReportArray" sits at
# 0xeb05f0 next to "game/net/net-menu.cpp" @ 0xeb0588). EVERY other path -
# connect failure, n<=0, no '+', no token1, no token2, an unmatched name -
# leaves the index at -1, i.e. FAIL-OPEN, not banned.
#
# So the correct "not banned" answer is any reply that does not present a
# matching ban row, and we send the cleanest such answer: an EMPTY body plus
# this family's NUL sentinel. buf[0] is then 0x00, the '+' test fails, and the
# index stays -1. That is also what the family means elsewhere - '+' lines are
# RESULT ROWS, and facebook-get-npid already answers "no matches" with an empty
# response - and it reproduces the payload shape that has been live-accepted
# nine times (the old fall-through answered these connections with a
# ticket_submit_response frame whose plaintext is 16 NULs, and both accounts
# went on to matchmake and play). We deliberately do NOT emit a "+0 none" row:
# that is a ban row whose name merely happens not to match, and it would become
# a real ban the day "none" collides with a pReportArray entry - and the entry
# names live in the data-compiler payload, not the EBOOT, so we cannot check.
#
# TODO(pReportArray): the literal entry NAMES in the DC-resident pReportArray
# table are unknown. UPDATE 2026-08-19: the "data-compiler payload" isn't the
# unreadable wall this comment used to imply - net10.bin (01.11's DC00 registry,
# server/data/served_content/net10.bin.psarc.crypt, see docs/protocol/dc_table.md
# for the container format) DOES contain the literal hash 0xFFAC56F2 once, at
# file offset 0x148c. Its directory entry decodes (dc_table.ksy's format) as
# {value_ptr -> file-off 0x25314, key_hash=0xFFAC56F2, type_hash=0xF99A36AA};
# the target at 0x25314 is {count=1, array_ptr -> file-off 0x3bc68, tag=0x13c5fb80}
# - i.e. as of 01.11's shipped data, this table has exactly ONE entry defined
# (not empty, not populated with many ban rows). What's still NOT recovered:
# the entry's actual NAME (the string strcmp'd against the server's ban reply)
# and its associated integer id - the blob at 0x3bc68 is further DC-directory
# -shaped data (floats, nested fixup pointers) that wasn't fully decoded this
# session; see dc_table.ksy's doc for why (the same "nested structure, unclear
# exact stride" gap as member_data.rank_tier). A DC/.psarc dump was NOT needed
# to get this far - it needed finding+decoding the container format, which is
# now done at the container level. What remains needs either finishing that
# one nested blob's decode or a runtime read of the resolved table.
# NOTHING NEEDS DOING HERE unless this project ever wants to
# deliberately ban an account: our reply is an EMPTY body, so buf[0] is 0x00, the
# '+' test at 0x36e2cc fails, and the ban index at g_net+916 stays at the -1 it
# was initialised to at 0x36e1a0/0x36e1a8. The check is fail-open regardless of
# what the table contains, so an unknown table cannot produce a false ban. The
# names would only ever be needed to CONSTRUCT a reply that bans somebody.
#
# TODO(g_net+920): the meaning of the integer parsed out of the ban reply's first
# token and stored at g_net+920 is unknown. It is formatted into the ban message
# shown to the player (format-string pointer 0x1530d90, which is bss and so only
# readable at runtime); duration / expiry / days is a guess and is deliberately
# not recorded as fact. Same disposition as above: it is only reachable on the
# banned path, which our empty reply never enters, so NOTHING NEEDS DOING unless
# we ever want to deliberately ban somebody.
#
# VERIFIED 2026-08-19 against the 01.11 ELF, instruction by instruction, so the
# fail-open reasoning above is not being restated on trust:
#   0x36e1a0  li  r0,-1          / 0x36e1a8  stw r0,916(r9)   (r9 = g_net)
#   0x36e28c  li  r5,256         / 0x36e290  bl 0xafacf8      (one bounded recv)
#   0x36e298  cmpwi cr7,r3,0     / 0x36e29c  ble cr7,0x36e388 (n<=0 -> skip all)
#   0x36e2c8  lbz r0,904(r1)     / 0x36e2cc  cmpwi cr7,r0,43  ('+')
#   0x36e2d0  bne cr7,0x36e388   (no '+' -> skip all; index left at -1)
#   0x36e2dc  addi r3,r1,905     -> strtok_r 0xe72d80, strtol 0xe75d78 -> r27
#   0x36e33c-0x36e368  loop: mulli r9,r9,12 (12-byte entries), lwz r3,8(r9)
#                      (name at [+8]), strcmp 0xe778e4; ONLY on a match does it
#                      stw r27,920(r9) / stw r29,916(r9)
# 0x36e388 is the shared "done" label reached by every non-ban path, and it does
# not touch g_net+916. Note the older claim that "0x36e1fc is the connect call"
# is off by one step: 0x36e1fc loads the "report-server" string pointer (slot
# 0x129a3c8) and the connect itself is the bl 0xaf9bb4 at 0x36e220.
def build_report_response(cmd):
    """Map one decoded report-server line to a reply. Returns (response, note).

    The only verb is `is-banned <online_id>`. This server keeps no ban list, so
    no account has a standing record and every account is answered "not
    banned". See the block comment above for the decoded grammar and for why
    "not banned" is an EMPTY body rather than a '+' row."""
    tokens = cmd.strip().split(" ")
    verb = tokens[0] if tokens else ""

    if verb == "is-banned":
        who = tokens[1] if len(tokens) > 1 else "<no id>"
        return "", (f"is-banned {who!r} -> NOT banned (empty body + NUL: buf[0] "
                    f"fails the '+' test @0x36e2cc, ban index stays -1)")

    # Unknown verb: same empty answer. NEVER close first - a server-initiated
    # EOF is this family's error path.
    return "", f"unknown report verb {verb!r} - empty answer (not banned)"


def handle_report(conn, session_token, client_nonce, log_append):
    """report-server post-hello loop. Same frame layer and hold-for-client-close
    discipline as every sibling line service (see handle_line_service).

    The client does ONE bounded 256-byte recv and then closes, so the entire
    reply must go out in a single frame - which the loop already does - and we
    must still not close first.

    Having a handler at all is the point: before this, a ban check was answered
    with a ticket_submit_response frame. That is the same request/response
    mismatch class that produced the leaderboard "Error 9 / disconnected from
    the game servers" boot and the Facebook retry spin, and it sits on the path
    to online entry."""
    handle_line_service(conn, session_token, client_nonce, log_append,
                        "report", build_report_response)


# ---------------------------------------------------------------------------
# gamelist-server (2026-08-19) - grammar and reply shape DERIVED FROM THE BINARY
# ---------------------------------------------------------------------------
# 01.11-ONLY: neither "gamelist-server" nor "game-add " appears anywhere in the
# 01.00 EBOOT. All addresses below are 01.11 VMAs (VMA = file offset + 0x10000)
# in the 01.11 ELF (sha256 241e2b1b...); the sender is FUN_004047f4, found by
# resolving the r2->anchor->displacement chain onto the three string slots
# 0x129cd7c ("game-add " @ 0xeb2680), 0x129cd8c ("gamelist-server" @ 0xeb2690)
# and 0x129cd70 ("games/%s" @ 0xeb2670). r2 for this build is 0x1338de0, taken
# from the entry-point function descriptor at 0x12d5c08.
#
# WHAT IT IS FOR: registering a live game with the backend. The client announces
# "this match-session id exists and these accounts are in it". There is no read
# verb - "game-add " is the ONLY "game-" verb in the whole binary, no
# "game-remove" and no "game-list" - so this is write-only registration, NOT a
# second discovery path. Discovery stays 0x135/0x136 on the session manager.
#
# REQUEST, assembled literally by strcat in FUN_004047f4:
#     buf[0] = *""            @0x4048c0-0x4048e0 (slot 0x129cd78 -> "", so the
#                             buffer simply starts empty), then memset(buf+1,0,255)
#     strcat "game-add "      @0x4048ec (slot 0x129cd7c)
#     strcat <session-id>     @0x4048fc/0x40492c (r25 = arg+16222)
#     for i in 0..count-1:    count = *(arg+16152), loop @0x404908-0x40494c
#         strcat " "          (slot 0x129cd80 -> " ")
#         strcat <player>     (arg + 17688 + i*212)
#     strcat "\n"             @0x404950 (slot 0x129cd84 -> "\n")
# i.e.  game-add <session-id> <player>[ <player>...]\n
# Live capture matches to the byte: 'game-add mgnomad2.1787116698 mgnomad2
# comradesean\n' = 9 + 19 + 9 + 12 + 1 = 50 bytes, exactly the 50 observed. The
# session id is the <npid>.<unix-ts> string that 0x143 SetRoomDataBlock also
# carries.
#
# CONNECT + REPLY, the part that had to be settled before writing this handler:
#     0x4049b0  r6 = "gamelist-server"; r4/r5 = ip/port from *(0x15900b8)+0x60
#     0x4049d4  bl 0xaf9bb4    the SHARED hello function - li r5,88 (88-byte
#                              hello) @0xaf9c94, li r5,8 (8-byte reply)
#                              @0xaf9d2c, cmpwi r0,34 (=0x22 ack magic)
#                              @0xaf9d60. Same function report-server uses at
#                              0x36e220, i.e. the 01.11 twin of 01.00's
#                              FUN_00acc424. So this IS a 0x11 sibling.
#     0x4049dc  cmpwi cr7,r3,0 / bne -> 0x404a20   connect failed -> just close
#     0x4049f0  strlen(buf) (0xe72a00)
#     0x404a04  bl 0xafad88    send(conn, buf, len)
#     0x404a14  li r5,256
#     0x404a18  bl 0xafacf8    ONE bounded 256-byte recv, into the SAME buffer
#     0x404a20  mr r3,r31 / bl 0xaf9260    close - immediately, unconditionally
#
# THE REPLY IS NOT PARSED AT ALL. This is the HEARTBEAT shape, and in fact
# weaker than heartbeat's: the recv's return value in r3 is not even compared
# against anything - 0x404a1c is the call's nop and 0x404a20 overwrites r3 with
# the connection pointer for the close. There is no length field, no accumulator
# loop, no '+' test, no strtok - contrast report-server, which does test r3 and
# then parses (0x36e298 onwards), and leaderboard-server, which loops until its
# sentinel. So any bytes satisfy this client, and the whole reply must arrive in
# ONE frame because the client closes right after the single recv.
#
# Consequently the reply body below is a family-CONSISTENCY choice, not a
# decoded requirement: '+0\n' plus the family's NUL sentinel, exactly what
# handle_heartbeat sends for the same reason. What matters, and what is
# load-bearing, is the two family rules handle_line_service already enforces -
# send something so the client's recv returns rather than sitting in its own
# timeout, and NEVER close first.
#
# ADJACENT BUT SEPARATE CHANNEL, noted so it is not confused with this one:
# earlier in the same function (0x404820-0x4048b8) the client builds a buffer
# via 0xa49efc/0xa49f14/0x403ca4, formats the path "games/%s" with the same
# session id into a stack buffer, and hands it to 0xaf39c0 with a retry loop of
# up to 9 attempts. 0xaf39c0 stores a method enum of 4 into its request object
# (li r0,4 @0xaf39f8; the sibling entry point 0xaf3a30 stores 1), so it is an
# HTTP-style request to a DIFFERENT host object (slot 0x129cd74 -> 0x13ba678),
# not this TCP line service. That upload is out of scope here and is NOT handled
# by this server.
GAMELIST_LOCK = threading.Lock()
# session_id -> {"first_seen": epoch, "last_seen": epoch, "adds": int,
#                "roster": [online_id, ...]}
GAMES = {}


def record_game(session_id, roster, now=None):
    """Record (or refresh) one registered game. In-memory only, like PRESENCE:
    the client never reads this back - there is no game-list verb in the binary -
    so nothing depends on it surviving a restart. It exists because registration
    is the message's actual purpose, and having the roster keyed by session id
    makes the log readable and gives any future work a real record to correlate
    against 0x143's data_block. Returns the updated record."""
    now = time.time() if now is None else now
    with GAMELIST_LOCK:
        rec = GAMES.get(session_id)
        if rec is None:
            rec = {"first_seen": now, "last_seen": now, "adds": 0, "roster": []}
            GAMES[session_id] = rec
        rec["last_seen"] = now
        rec["adds"] += 1
        rec["roster"] = list(roster)
        return dict(rec)


def build_gamelist_response(cmd):
    """Map one decoded gamelist-server line to a reply. Returns (response, note).

    The only verb is `game-add <session-id> <player>...`. The client does not
    parse the reply (see the block comment above), so the reply is a bare
    family-shaped ack and the useful work is recording the game."""
    tokens = cmd.strip().split()
    verb = tokens[0] if tokens else ""

    if verb == "game-add" and len(tokens) >= 2:
        session_id = tokens[1]
        roster = tokens[2:]
        rec = record_game(session_id, roster)
        return "+0\n", (f"game-add {session_id!r} roster={roster} "
                        f"(add #{rec['adds']}, {len(GAMES)} game(s) known)")

    if verb == "game-add":
        # Verb with no session id: nothing to key a record on. Still ack, so the
        # client's single bounded recv returns and it closes cleanly.
        return "+0\n", "game-add with no session id - acked, nothing recorded"

    # No other game- verb exists in the binary. If one ever shows up it is new
    # information; ack it so the client is not left waiting, and say so loudly.
    return "+0\n", (f"UNKNOWN gamelist verb {verb!r} - acked. No verb other than "
                    f"'game-add ' exists in the 01.11 EBOOT, so this line is new "
                    f"evidence; capture it.")


def handle_gamelist(conn, session_token, client_nonce, log_append):
    """gamelist-server post-hello loop. Same encrypted-frame layer and
    NUL-sentinel / hold-for-client-close discipline as every sibling line service
    (see handle_line_service).

    Reply shape is settled from the binary, not guessed: FUN_004047f4 does one
    bounded 256-byte recv at 0x404a18 and then closes at 0x404a24 without ever
    inspecting the result, so the whole reply must fit one frame and its contents
    are free. What is NOT free is sending one at all and not closing first.

    Having a handler at all is the point: before this, a game registration fell
    through to the ticket path and was answered with a ticket_submit_response
    blob - the same request/response mismatch class that produced the leaderboard
    "Error 9 / disconnected from the game servers" boot and the Facebook retry
    spin."""
    handle_line_service(conn, session_token, client_nonce, log_append,
                        "gamelist", build_gamelist_response)


# Service-name -> post-hello handler for the 0x11 sibling LINE services. Names
# are read verbatim out of the 88-byte hello (bytes 24:88, NUL-terminated).
# Six services have been observed live; single-player-server has never opened a
# connection, and ticket-server itself uses the message-C/D handshake below
# rather than a line protocol, so neither appears here. invite-server is dead
# code in this build (zero code xrefs across its whole literal pool) and will
# never connect.
LINE_SERVICE_HANDLERS = {
    "leaderboard-server": handle_leaderboard,
    "facebook-server": handle_facebook,
    "heartbeat-server": handle_heartbeat,
    "report-server": handle_report,
    "gamelist-server": handle_gamelist,
}


def handle(conn, addr, log_lock, log):
    ts = datetime.datetime.now().isoformat()
    append, finish = capped_appender(
        f"==== {ts} connection from {addr[0]}:{addr[1]} ====\n",
        MAX_LOG_CHARS, "log characters")
    try:
        # Message 1: 88-byte hello (protos/0x11_ticket_server_hello.ksy)
        hello = recv_exact(conn, 88)
        append(f"-- recv hello (88 bytes) --\n{hexdump(hello)}\n")
        opcode = hello[0]
        client_nonce = int.from_bytes(hello[4:8], "big")
        service_name = hello[24:88].split(b"\x00", 1)[0].decode("ascii", "replace")
        append(f"   opcode=0x{opcode:02x} client_nonce=0x{client_nonce:08x} service_name={service_name!r}\n")

        # Message 2: our 8-byte response (0x22_ticket_server_hello_response.ksy)
        # ack_magic MUST be 0x22 or the client aborts immediately - confirmed.
        # session_token: this becomes the counter that keys the client's message-C
        # encryption (confirmed - see decrypt_frame below). Using 0, matching the
        # value verified live via debugger and used in the confirmed-working decrypt.
        session_token = 0
        resp1 = bytes([0x22, 0x00, 0x00, 0x00]) + session_token.to_bytes(4, "big")
        conn.sendall(resp1)
        append(f"-- sent hello_response (8 bytes, session_token={session_token}) --\n{hexdump(resp1)}\n")

        # Several 0x11 siblings multiplex on THIS listener but speak the
        # line protocol after the hello, not the ticket message-C/D exchange.
        # Branch here; everything above (hello + 8-byte reply) is shared. Every
        # one of them must hold the socket open until the CLIENT closes - a
        # server-initiated EOF is the client's error path (Error 9 /
        # "disconnected from the game servers"). See handle_line_service.
        handler = LINE_SERVICE_HANDLERS.get(service_name)
        if handler is not None:
            # The service loop's log lines land in the same (size-capped)
            # connection block via the same appender.
            handler(conn, session_token, client_nonce, append)
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
        append(f"-- recv message 3, encrypted frame ({len(raw3)} bytes) --\n{hexdump(raw3)}\n")

        plaintext, tag_ok, _, computed_tag, embedded_tag = ticket_cipher.decrypt_frame(
            CANDIDATE_KEY, session_token, raw3)
        append(f"   tag_ok={tag_ok} computed_tag={computed_tag.hex()} embedded_tag={embedded_tag.hex()}\n")
        append(f"   decrypted plaintext ({len(plaintext)} bytes): {plaintext!r}\n")
        ticket_data = plaintext

        # UNHANDLED SIBLING SERVICE WATCH (2026-08-19). Everything that is not
        # ticket-server and has no entry in LINE_SERVICE_HANDLERS lands here and
        # is answered with a ticket_submit_response blob, which is almost
        # certainly wrong for it - that mismatch is what broke the leaderboard
        # channel and the Facebook flow before each got a real handler. Eight
        # service names exist in the 01.11 EBOOT:
        #     ticket / leaderboard / facebook / heartbeat / report /
        #     gamelist                                              - handled
        #     single-player                                         - not
        #     invite                                                - dead code
        # Shout loudly with the decoded payload so an unhandled service cannot
        # sit unnoticed in a 300MB log. In particular single-player-server has
        # NEVER been seen to send anything; if it ever does, that line is the
        # first evidence of its grammar and should not be missed.
        if service_name != "ticket-server":
            append((f"   *** UNHANDLED SIBLING SERVICE {service_name!r} - no "
                      f"handler, falling through to the ticket path and "
                      f"answering with a ticket_submit_response blob, which is "
                      f"probably NOT what it expects. Decoded request: "
                      f"{plaintext!r}. Add a handler in "
                      f"LINE_SERVICE_HANDLERS. ***\n"))
            if service_name == "single-player-server":
                append(("   *** single-player-server HAS SPOKEN FOR THE FIRST "
                          "TIME. It had never been observed sending anything, so "
                          "its line grammar was unknown and protos/ has no spec "
                          "for it. Capture the request above - it is the only "
                          "evidence of that grammar. ***\n"))

        # Message 4: a real encrypted frame, keyed by client_nonce (the client's
        # receive-side counter, confirmed - see decrypt_frame's docstring/the
        # companion doc). Content is still an unconfirmed placeholder (16 zero
        # bytes) - only the crypto wrapper is verified, not what should be inside.
        frame_d, _ = ticket_cipher.encrypt_frame(CANDIDATE_KEY, client_nonce, b"\x00" * 16)
        conn.sendall(frame_d)
        append(f"-- sent ticket_submit_response, encrypted frame ({len(frame_d)} bytes) --\n{hexdump(frame_d)}\n")

        # Handshake complete per current understanding - watch for anything further
        # (a 5th message would mean our understanding is incomplete).
        conn.settimeout(10)
        while True:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                append("  (10s idle after handshake, closing)\n")
                break
            if not chunk:
                append("  (connection closed by peer after handshake)\n")
                break
            append(f"-- UNEXPECTED extra data after handshake ({len(chunk)} bytes) --\n{hexdump(chunk)}\n")
    except (ConnectionError, socket.timeout, OSError) as e:
        append(f"  (error/early close: {e})\n")
    finally:
        # Release the accept slot first: a failure while closing or logging
        # must not permanently retire a slot.
        _handler_slots.release()
        conn.close()
        entry = finish()
        with log_lock:
            print(entry, flush=True)
            log.write(entry + "\n")
            log.flush()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(5)
    print(f"Stateful ticket-server stub listening on 0.0.0.0:{PORT}, logging to "
          f"{LOG_PATH}, max {MAX_CONCURRENT_HANDLERS} concurrent handlers", flush=True)

    log_lock = threading.Lock()
    with RotatingLog(LOG_PATH) as log:
        while True:
            # Gate ACCEPT on the semaphore, not just the handler thread - see
            # MAX_CONCURRENT_HANDLERS.
            _handler_slots.acquire()
            conn, addr = srv.accept()
            t = threading.Thread(target=handle, args=(conn, addr, log_lock, log), daemon=True)
            t.start()


if __name__ == "__main__":
    main()
