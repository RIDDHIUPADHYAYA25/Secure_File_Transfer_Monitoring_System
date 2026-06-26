"""
db_crypto.py — SentinelTransfer Database Encryption Module
===========================================================
Encrypts / decrypts the SQLite database using AES-256 (Fernet).
Key is derived from admin e-mail + SECRET_KEY via PBKDF2-HMAC-SHA256.

Nobody can decrypt the database without:
  1. The exact admin e-mail address
  2. The SECRET_KEY (stored only in .env, never committed to Git)
"""
import os
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ─── Encrypted-file header ─────────────────────────────────────────────────────
# This text is written at the TOP of every .enc file in plain ASCII so that
# ANYONE who opens the file on GitHub or in a text editor immediately sees the
# privacy notice.  The actual SQLite data beneath is AES-256 ciphertext.
HEADER = """\
╔══════════════════════════════════════════════════════════════════╗
║        🔒  SENTINELTRANSFER — ENCRYPTED DATABASE  🔒            ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  This file contains an AES-256 encrypted SQLite database.        ║
║  It is encrypted to PROTECT USER PRIVACY.                        ║
║                                                                  ║
║  ⚠️  Unauthorised access to this data is PROHIBITED.            ║
║                                                                  ║
║  Admin decryption only:                                          ║
║      python admin_decrypt.py --email <admin_email>               ║
║                                                                  ║
║  Algorithm  : AES-256 (Fernet / PBKDF2-HMAC-SHA256)             ║
║  Iterations : 300,000 rounds                                     ║
║  Key source : Admin e-mail + SECRET_KEY  (not in this repo)      ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
---BEGIN ENCRYPTED DATA---
"""

MARKER_START = b"---BEGIN ENCRYPTED DATA---\n"
SALT_SIZE    = 32
ITERATIONS   = 300_000


# ─── Key derivation ────────────────────────────────────────────────────────────
def _derive_key(admin_email: str, secret_key: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from admin e-mail + secret using PBKDF2."""
    material = f"{admin_email.strip().lower()}:{secret_key}".encode("utf-8")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=ITERATIONS,
    )
    raw = kdf.derive(material)
    return base64.urlsafe_b64encode(raw)          # Fernet expects URL-safe base64


# ─── Public API ────────────────────────────────────────────────────────────────
def encrypt_db(db_path: str, enc_path: str, admin_email: str, secret_key: str) -> None:
    """
    Encrypt *db_path* → *enc_path*.
    The output file starts with a human-readable privacy notice (visible on
    GitHub / any text editor) followed by AES-256 ciphertext.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    with open(db_path, "rb") as f:
        plaintext = f.read()

    salt      = os.urandom(SALT_SIZE)
    key       = _derive_key(admin_email, secret_key, salt)
    fernet    = Fernet(key)
    ciphertext = fernet.encrypt(plaintext)

    # Encode ciphertext as base64 so the file is all-printable ASCII
    encoded   = base64.b64encode(ciphertext)

    # Embed the salt as a hex line so decrypt can find it
    salt_hex  = f"SALT:{salt.hex()}\n".encode()

    with open(enc_path, "wb") as f:
        f.write(HEADER.encode("utf-8"))
        f.write(salt_hex)
        f.write(encoded)

    size_kb = os.path.getsize(enc_path) / 1024
    print(f"  ✓ Encrypted  → {enc_path}  ({size_kb:.1f} KB)")


def decrypt_db(enc_path: str, out_path: str, admin_email: str, secret_key: str) -> None:
    """
    Decrypt *enc_path* → *out_path*.
    Raises ValueError if the e-mail / key is wrong.
    """
    if not os.path.exists(enc_path):
        raise FileNotFoundError(f"Encrypted database not found: {enc_path}")

    with open(enc_path, "rb") as f:
        raw = f.read()

    # Find where the encrypted data begins
    marker_pos = raw.find(MARKER_START)
    if marker_pos == -1:
        raise ValueError("File format unrecognised — not a SentinelTransfer encrypted database.")

    body = raw[marker_pos + len(MARKER_START):]

    # First line of body is SALT:hex
    lines      = body.split(b"\n", 1)
    salt_line  = lines[0].decode("ascii").strip()
    if not salt_line.startswith("SALT:"):
        raise ValueError("Missing salt in encrypted file — file may be corrupted.")

    salt        = bytes.fromhex(salt_line[5:])
    encoded_ct  = lines[1].strip()
    ciphertext  = base64.b64decode(encoded_ct)

    key    = _derive_key(admin_email, secret_key, salt)
    fernet = Fernet(key)

    try:
        plaintext = fernet.decrypt(ciphertext)
    except InvalidToken:
        raise ValueError(
            "❌ Decryption failed — e-mail or SECRET_KEY is incorrect."
        )

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(plaintext)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"  ✓ Decrypted  → {out_path}  ({size_kb:.1f} KB)")


def verify_enc_file(enc_path: str) -> bool:
    """Return True if the file looks like a valid encrypted database."""
    try:
        with open(enc_path, "rb") as f:
            header = f.read(200)
        return b"SENTINELTRANSFER" in header and MARKER_START in header
    except Exception:
        return False
