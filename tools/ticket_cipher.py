#!/usr/bin/env python3
"""Reimplementation of the ticket-server frame cipher, reverse-engineered from
raw PPC disassembly of FUN_00acb6fc/FUN_00acbb90 and the primitives they call:
FUN_00db5ec0 (key schedule), FUN_00db7f88 (digest), FUN_00db7cb0 (encrypt),
FUN_00db7e08 (decrypt), FUN_00db7c80 (per-word byte-reversal), FUN_00db5e50
(tag finalize). See docs/protocol/0x11_ticket_server_hello.md's "Encrypted
frame layer" section for the disassembly evidence this is built from.

Every operation here was read directly off raw instructions (not decompiled
C, which repeatedly dropped parameters for this call chain) - see
research/ghidra/cipher_final_disasm.txt, round_funcs_disasm.txt,
finalize_disasm.txt, acbb90_key_check.txt.

STATUS (2026-08-14, fourth pass): WORKING AND VERIFIED. The coordinator
independently confirmed the candidate static key two ways live (r3 at
FUN_00db5ec0's entry == 0xed7a50 on both call sites of a real frame; a
direct memory read of 16 bytes at 0xed7a50 matched the candidate key
byte-for-byte), which ruled out "wrong key" and pointed the remaining bug
back at this file's algorithm. Ground-truth Ghidra emulation of
FUN_00db5ec0 (research/ghidra/keysched_trace.txt, via
tools/ghidra_scripts/EmulateKeySchedule.java) checkpointed every internal
call boundary and found the exact divergence: key_schedule()'s
finalization round was feeding a wrongly-transformed "reversed_words" data
array into the last ARX pass, when the real function - because
FUN_00db7cb0 (which FUN_00db5ec0 calls for that step) does its OWN
internal byte-swap-in on its data argument, on top of the explicit swap
FUN_00db5ec0 already applied - actually ends up feeding the state through
ITSELF unchanged (the two swaps cancel). Fixed in key_schedule() below;
confirmed to match the emulated ground truth bit-for-bit at every
checkpoint. See docs/protocol/0x11_ticket_server_hello.md's "Encrypted
frame layer" section for the full checkpoint trace and the bug diagnosis.

With the fix, decrypt_frame() on the real 272-byte capture
(2026-08-14T08:11:28, captures/tcp_catch.log) with the confirmed key and
session_token=0 now: (1) passes its own auth_tag verification exactly
(computed_tag == embedded_tag), and (2) recovers a plaintext that is
unambiguously a real Sony NP ticket - it contains the literal ASCII
substring "UP9000-BCUS98174_00" (this title's PS3 content ID) and
"comradesean" (very likely the connecting player's PSN online ID), plus
clear Sony-style TLV (type/length/value) structure throughout. This is
about as strong a real-world confirmation as this investigation could ask
for - a from-first-principles reverse-engineered cipher recovering
recognizable, semantically correct plaintext from a real capture.
"""
import struct

MASK32 = 0xFFFFFFFF
C1 = 0x5b3aa654
C2 = 0x75970a4d


def rotl32(x, n):
    x &= MASK32
    return ((x << n) | (x >> (32 - n))) & MASK32


def words_from_bytes(b):
    """FUN_00db7c80 direction 1: wire bytes -> native words (LE32 per word)."""
    n = len(b) // 4
    return list(struct.unpack('<%dI' % n, b))


def bytes_from_words(words):
    """FUN_00db7c80 direction 2: native words -> wire bytes (LE32 per word)."""
    return struct.pack('<%dI' % len(words), *[w & MASK32 for w in words])


def arx_round(r16, r17, r18, r19):
    """One round's mixing, shared identically by FUN_00db7f88/db7cb0/db7e08
    up to (but not including) the data-word XOR - confirmed via raw
    disassembly (0xdb7fd8-0xdb8054 / 0xdb7d18-0xdb7d7c / 0xdb7e70-0xdb7ed4,
    byte-identical across all three functions). Returns (r16,r17,r18,K)
    where K is the value XORed against the data word next."""
    r19 = r19 ^ C1
    r18 = (r18 + r16 + r19) & MASK32
    r18 = rotl32(r18, 7)
    r17 = (r17 + r19 + r18) & MASK32
    r18 = r18 ^ C2
    r17 = rotl32(r17, 11)
    r16 = (r16 + r18 + r17) & MASK32
    r16 = rotl32(r16, 17)
    mux = (r16 & r17) | (r18 & (~r17 & MASK32))
    K = (r19 + mux) & MASK32
    r16 = (~r16) & MASK32
    r17 = (~r17) & MASK32
    return r16, r17, r18, K


def process(state, data_words, mode):
    """mode: 'digest' (read-only), 'encrypt' (CFB encrypt), 'decrypt' (CFB
    decrypt). Returns (final_state, output_words). For 'digest', output_words
    == data_words (unused/ignored by caller)."""
    r16, r17, r18, r19 = state
    out = []
    for w in data_words:
        r16, r17, r18, K = arx_round(r16, r17, r18, r19)
        if mode == 'decrypt':
            # FUN_00db7e08: plaintext = K ^ ciphertext_word; feedback uses
            # the ORIGINAL ciphertext word, NOT the recovered plaintext -
            # confirmed via raw disasm (0xdb7edc-0xdb7ee4): `xor r0,r19,r0`
            # (result to r0, not r19) then `xor r19,r19,r0` recovers the
            # original word into r19 for next round's feedback.
            out_w = K ^ w
            r19 = w
        else:
            # FUN_00db7f88 (digest) / FUN_00db7cb0 (encrypt): identical
            # feedback formula either way - r19_next = K ^ data_word.
            # Encrypt additionally persists out_w as the ciphertext byte
            # output; digest discards it (data buffer is never written).
            out_w = K ^ w
            r19 = out_w
        out.append(out_w)
    return (r16, r17, r18, r19), out


def key_schedule(static_key16, counter):
    """FUN_00db5ec0(static_key, counter) -> 4-word state, confirmed via raw
    disassembly AND ground-truth Ghidra emulation of 0x00db5ec0
    (research/ghidra/keysched_trace.txt) - see docs/protocol/
    0x11_ticket_server_hello.md's "Encrypted frame layer" section for the
    checkpoint-by-checkpoint trace this was debugged against.

    BUG FIX (2026-08-14, fourth pass): a prior version of this function
    modeled FUN_00db5ec0's finalization round as feeding a byte-reversed
    SNAPSHOT of the state back into an encrypt-mode round ("reversed_words",
    computed by simulating the explicit FUN_00db7c80(scratch2,scratch2,16)
    call visible in FUN_00db5ec0's own disassembly at 0xdb5fd4). Ground-truth
    emulation proved this wrong: FUN_00db7cb0 (the function FUN_00db5ec0
    calls for this step) ALSO does its OWN internal byte-swap-in on its
    "data" argument before its round loop (the same pattern as
    FUN_00db7f88/FUN_00db7e08, each of which independently pre-swap their
    own data pointer - already correctly modeled by this module's
    words_from_bytes()/bytes_from_words() helpers for every OTHER call site).
    Applying a swap twice in a row (once explicitly by FUN_00db5ec0, once
    again internally by FUN_00db7cb0) is a no-op (byte-reversal is its own
    inverse), so the actual data words FUN_00db7cb0's round loop consumes
    are simply the state's OWN current values, unchanged - i.e. the state
    is fed through itself, no snapshot/reversal step needed in this
    implementation at all. Confirmed to match ground truth emulation
    exactly (bit-for-bit across all 4 output words) once fixed."""
    state = words_from_bytes(static_key16)          # state[i] = LE32(key[4i:4i+4])
    state, _ = process(state, [counter & MASK32], 'digest')   # mix in counter (1 word)
    # Finalization round: run the state back through an ENCRYPT-mode round
    # using the state's OWN current words as the "data" - see docstring above
    # for why no extra byte-swap simulation is needed here.
    state, _ = process(state, list(state), 'encrypt')
    return state


def finalize_tag(state):
    """FUN_00db5e50(state) -> 16-byte auth_tag, confirmed via raw
    disassembly of 0x00db5e50: X = state[0]^state[1]^state[2]^state[3];
    tag = concat(LE32(X^state[i]) for i in 0..3)."""
    x = state[0] ^ state[1] ^ state[2] ^ state[3]
    out_words = [x ^ s for s in state]
    return bytes_from_words(out_words)


def encrypt_frame(static_key16, session_token, plaintext):
    """Build a full 20-byte-header + ciphertext frame, per FUN_00acb6fc.
    Returns (frame_bytes, new_session_token)."""
    plen = len(plaintext)
    pad = (-plen) & 3
    padded = plaintext + b'\x00' * pad

    tag_state = key_schedule(static_key16, session_token)
    tag_state, _ = process(tag_state, words_from_bytes(padded), 'digest')
    auth_tag = finalize_tag(tag_state)

    enc_state = key_schedule(static_key16, session_token)
    enc_state, out_words = process(enc_state, words_from_bytes(padded), 'encrypt')
    ciphertext = bytes_from_words(out_words)

    header = bytes([0x33, pad]) + struct.pack('>H', plen)
    frame = header + auth_tag + ciphertext
    return frame, (session_token + 1) & MASK32


def decrypt_frame(static_key16, counter, frame):
    """Parse+decrypt a frame per FUN_00acbb90. Returns
    (plaintext, tag_ok, new_counter, computed_tag, embedded_tag)."""
    magic = frame[0]
    pad = frame[1]
    plen = struct.unpack('>H', frame[2:4])[0]
    embedded_tag = frame[4:20]
    ciphertext = frame[20:20 + plen + pad]

    dec_state = key_schedule(static_key16, counter)
    dec_state, out_words = process(dec_state, words_from_bytes(ciphertext), 'decrypt')
    plaintext_padded = bytes_from_words(out_words)

    # Tag verification digests the DECRYPTED PLAINTEXT (FUN_00acbb90 calls
    # FUN_00db7f88 on *(conn+0x5c)+0x14 - the same buffer FUN_00db7e08 just
    # overwrote in place with plaintext, per its decompile), using a fresh
    # independent key-schedule call with the same counter value.
    verify_state = key_schedule(static_key16, counter)
    verify_state, _ = process(verify_state, words_from_bytes(plaintext_padded), 'digest')
    computed_tag = finalize_tag(verify_state)

    tag_ok = (computed_tag == embedded_tag)
    return plaintext_padded[:plen], tag_ok, (counter + 1) & MASK32, computed_tag, embedded_tag


if __name__ == '__main__':
    candidate_key = bytes.fromhex('78 56 34 12 32 54 76 98 88 ef cd ab ef cd ab 89'.replace(' ', ''))
    real_capture = bytes.fromhex("""
        33 02 00 fa bb 75 ef e6 43 c7 25 d5 3a bf ca 68
        02 a0 f7 a7 9c b6 9f ca 2b a4 64 51 cb 87 f9 fe
        6d 29 2e 90 10 65 05 54 11 04 65 2d e5 6f cf 33
        4f 32 af 96 04 55 75 57 a3 a9 d7 2e 29 7a 9c 46
        53 1b 4a 28 9d a1 b0 82 15 7c f3 90 43 6b a9 eb
        6b b3 45 b3 35 86 28 42 d0 1d fc 22 cf ab f5 3f
        36 8f a5 8e 76 02 36 12 5b 85 6b b2 f1 20 f6 b8
        ef a3 31 48 51 19 b0 f4 a7 61 b8 5f de 3e 4e e6
        a7 a6 e4 70 10 3e d5 b9 c8 97 87 e0 64 3f f7 d7
        04 07 cc de 49 55 9c 41 5f f1 1f cc 9e 8b 40 e3
        a7 f6 a3 ae c4 b1 20 ef 26 e2 2f 7b 7c 46 e4 4b
        91 95 d9 80 1a 7d 3a a7 b7 58 9c de 31 d0 ef db
        16 24 a4 d7 fa 0c 0f df 27 49 1f 8a 41 43 c7 4f
        d4 0d 82 7a cb 57 ff a9 66 91 e5 32 7f bb ea 25
        8a 9c 70 68 fd 9e 65 11 52 a7 ff 8b ef 75 e8 34
        52 ae 0f fe 14 42 f8 ec e9 d3 8d 82 1d eb 4e 0d
        49 1c 6b 19 64 ab 73 bd 68 a0 f1 cd c2 0d 00 5b
    """)
    assert len(real_capture) == 272, len(real_capture)

    pt, ok, new_ctr, computed, embedded = decrypt_frame(candidate_key, 0, real_capture)
    print("plaintext_len:", len(pt))
    print("tag_ok:", ok, "(expect True - fixed as of the fourth pass, see module docstring)")
    print("computed_tag:", computed.hex())
    print("embedded_tag:", embedded.hex())
    print("plaintext (hex):", pt.hex())
    print("plaintext (repr):", pt)
    assert ok, "decrypt_frame regressed - see module docstring for the expected-working state"
    assert b"BCUS98174" in pt, "expected the real NP ticket's title-ID substring in the decrypted plaintext"
    print()

    # ---- Derive a real, verified message-D (ticket_server_ticket_submit_response)
    # frame, per the coordinator's ask. Keyed by client_nonce (conn+0x4c), NOT
    # session_token - the client's own value from this same captured session's
    # message A (opcode=0x11 client_nonce=0x3b188d6f, see captures/tcp_catch.log,
    # 2026-08-14T08:11:28). Content is still an UNCONFIRMED GUESS (message D's
    # semantics were never observed) - what's now real and verified is the
    # FRAMING/CRYPTO: this frame's magic byte, length field, and auth_tag are
    # all correct per the confirmed-working cipher, so the client's own
    # FUN_00acbb90 decoder should accept it (pass the tag check) regardless of
    # whether the placeholder content means anything to the game logic that
    # reads it afterward.
    print("Deriving a real, cryptographically-valid message-D frame (content is still a guess):")
    client_nonce = 0x3b188d6f
    placeholder_content = b"\x00" * 16  # content semantics unknown - see comment above
    message_d_frame, _ = encrypt_frame(candidate_key, client_nonce, placeholder_content)
    print("  client_nonce (this session's message-A value):", hex(client_nonce))
    print("  message_d_frame (hex):", message_d_frame.hex())
    print("  message_d_frame length:", len(message_d_frame), "bytes")
    # Self-check: the client's own decoder logic (FUN_00acbb90) would decrypt
    # this with the SAME key/counter and must recompute a matching tag -
    # verify that round-trip here before calling it "real":
    d_pt, d_ok, _, d_computed, d_embedded = decrypt_frame(candidate_key, client_nonce, message_d_frame)
    print("  self-verify tag_ok:", d_ok, "(must be True for this to be a valid frame the client will accept)")
    print("Self round-trip sanity check (proves the algorithm is internally"
          " consistent, independent of whether the candidate key is right):")
    frame, tok = encrypt_frame(candidate_key, 0, b"self-test payload, arbitrary length 123")
    pt2, ok2, _, c2, e2 = decrypt_frame(candidate_key, 0, frame)
    print("  round-trip plaintext matches:", pt2 == b"self-test payload, arbitrary length 123")
    print("  round-trip tag_ok:", ok2)
