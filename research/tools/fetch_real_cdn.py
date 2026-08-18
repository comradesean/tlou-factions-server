#!/usr/bin/env python3
"""Fetch real Factions player-persistence objects from Naughty Dog's live S3 CDN.

The game stores per-player progression at
    t1.final.prod.s3.amazonaws.com/profiles/<online_id>/profile.21   (read-write)
    t1.final.prod.s3.amazonaws.com/userdata/<online_id>.txt.crypt    (read-only)
Unauthenticated GETs return 403, so this signs requests with the game's own
baked-in AWS creds (public in every retail copy of BCUS98174) using AWS
Signature v2 - the scheme the game uses. Creds are EXTRACTED FROM THE EBOOT at
runtime (never hardcoded here): access key id "AKIA..." and the adjacent 40-char
secret, both in the net-info.cpp string pool.

Purpose: obtain a GROUND-TRUTH sample of these encrypted objects for the
revival project's format work (the profile RE never had a real sample - the
buckets 403 anonymously). Decrypt with tools/psarc_crypt.py (same Blowfish+HMAC
container). This is game-preservation of content the user owns; the creds are
already public in the retail binary.

Usage:
    python3 fetch_real_cdn.py <online_id> [--eboot PATH] [--out DIR] [--http]
    python3 fetch_real_cdn.py comradesean
    # explicit creds instead of EBOOT extraction:
    AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... python3 fetch_real_cdn.py comradesean --no-eboot
"""
import sys
import os
import argparse
import base64
import hashlib
import hmac
import email.utils
import urllib.request
import urllib.error

DEFAULT_EBOOT = ("/mnt/f/rpcs3_testing/rpcs3-v0.0.41-19598-357b7d44_win64_msvc/"
                 "games/The Last of Us [BCUS98174]/PS3_GAME/USRDIR/EBOOT.elf")
BUCKET = "t1.final.prod"

# Objects to grab, as (bucket-relative key, local filename suffix).
def objects_for(online_id):
    return [
        (f"profiles/{online_id}/profile.21", f"profiles/{online_id}/profile.21"),
        (f"userdata/{online_id}.txt.crypt", f"userdata/{online_id}.txt.crypt"),
    ]


def extract_creds_from_eboot(path):
    """Pull the AWS access key id + secret from the EBOOT string pool.

    The access key matches AKIA[0-9A-Z]{16}; the secret is the 40-char base64-ish
    string immediately preceding it in the same pooled-string block (offset ~48
    bytes earlier in this build). We locate the access key, then scan backwards
    for the nearest 40-char [A-Za-z0-9+/] run - robust to small layout shifts.
    """
    import re
    with open(path, "rb") as f:
        blob = f.read()
    m = re.search(rb"AKIA[0-9A-Z]{16}", blob)
    if not m:
        raise SystemExit("Could not find an AWS access key (AKIA...) in the EBOOT.")
    access_key = m.group(0).decode("ascii")
    # secret: the last 40-char base64-alphabet run ending before the access key.
    window = blob[max(0, m.start() - 128): m.start()]
    secrets = re.findall(rb"[A-Za-z0-9+/]{40}", window)
    if not secrets:
        raise SystemExit("Found the access key but no adjacent 40-char secret; "
                         "pass creds via AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.")
    secret_key = secrets[-1].decode("ascii")
    return access_key, secret_key


def sign_v2(secret_key, method, canonical_resource, date_str):
    """AWS Signature v2 for S3: base64(HMAC-SHA1(secret, StringToSign))."""
    string_to_sign = f"{method}\n\n\n{date_str}\n{canonical_resource}"
    digest = hmac.new(secret_key.encode("utf-8"),
                      string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def fetch_one(key, access_key, secret_key, scheme, timeout=30):
    """GET one object, virtual-hosted, SigV2-signed. Returns (status, body|err)."""
    host = f"{BUCKET}.s3.amazonaws.com"
    url = f"{scheme}://{host}/{key}"
    date_str = email.utils.formatdate(usegmt=True)
    canonical_resource = f"/{BUCKET}/{key}"
    sig = sign_v2(secret_key, "GET", canonical_resource, date_str)
    req = urllib.request.Request(url, method="GET", headers={
        "Host": host,
        "Date": date_str,
        "Authorization": f"AWS {access_key}:{sig}",
        "User-Agent": "TLOU-preservation/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, str(e).encode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser(description="Fetch real Factions S3 profile/userdata objects.")
    ap.add_argument("online_id", help="PSN online id, e.g. comradesean")
    ap.add_argument("--eboot", default=DEFAULT_EBOOT, help="EBOOT.elf path (for cred extraction)")
    ap.add_argument("--no-eboot", action="store_true",
                    help="use AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY env instead of the EBOOT")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "real_cdn_samples"),
                    help="output directory")
    ap.add_argument("--http", action="store_true", help="use http:// (game default) instead of https")
    args = ap.parse_args()

    if args.no_eboot:
        access_key = os.environ.get("AWS_ACCESS_KEY_ID")
        secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
        if not access_key or not secret_key:
            raise SystemExit("--no-eboot needs AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY set.")
    else:
        access_key, secret_key = extract_creds_from_eboot(args.eboot)
        print(f"Extracted creds from EBOOT: {access_key} (secret {secret_key[:4]}...{secret_key[-4:]})")

    scheme = "http" if args.http else "https"
    any_ok = False
    for key, rel in objects_for(args.online_id):
        # try signed first; if that 403s, try anonymous (some content is public).
        status, body = fetch_one(key, access_key, secret_key, scheme)
        if status == 403:
            print(f"  {key}: 403 signed - retrying anonymous...")
            try:
                with urllib.request.urlopen(f"{scheme}://{BUCKET}.s3.amazonaws.com/{key}", timeout=30) as r:
                    status, body = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read()
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                status, body = None, str(e).encode()
        if status == 200 and body:
            dest = os.path.join(args.out, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(body)
            print(f"  {key}: 200 OK, {len(body)} bytes -> {dest}")
            any_ok = True
        else:
            snippet = body[:200].decode("latin1", "replace") if body else ""
            print(f"  {key}: status={status} len={len(body) if body else 0}  {snippet!r}")

    if any_ok:
        print("\nDecrypt a fetched object with tools/psarc_crypt.py (same Blowfish+HMAC "
              "container as net1.bin.psarc.crypt / profile.21).")
    else:
        print("\nNothing fetched. The objects may be gone or the creds revoked for reads; "
              "a real PS3 capture or a cached copy is the fallback.")


if __name__ == "__main__":
    main()
