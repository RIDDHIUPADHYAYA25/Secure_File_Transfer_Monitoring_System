#!/usr/bin/env python3
"""
admin_decrypt.py — SentinelTransfer Admin Database Tool
=========================================================
Only the admin (whose e-mail matches ADMIN_EMAIL in .env) can
encrypt or decrypt the database.

Usage:
  Encrypt DB for GitHub:
    python admin_decrypt.py --action encrypt --email your@email.com

  Decrypt DB for local use:
    python admin_decrypt.py --action decrypt --email your@email.com
"""
import argparse
import os
import sys
from pathlib import Path

# Configure stdout and stderr to use UTF-8 to prevent UnicodeEncodeError on Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()

# ─── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent
INST_DIR  = BASE_DIR / "instance"
DB_PATH   = INST_DIR / "sentinel.db"
ENC_PATH  = INST_DIR / "sentinel.db.enc"

# ─── Banner ────────────────────────────────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║       🛡  SentinelTransfer — Admin Database Tool  🛡            ║
╠══════════════════════════════════════════════════════════════════╣
║   AES-256 (Fernet / PBKDF2-HMAC-SHA256, 300 000 iterations)     ║
║   Key = PBKDF2(admin_email + SECRET_KEY)                         ║
╚══════════════════════════════════════════════════════════════════╝
"""


def get_admin_email() -> str:
    """Return the authorised admin e-mail from environment."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    if not email:
        print("⚠️  ADMIN_EMAIL is not set in your .env file.")
        print("   Add:  ADMIN_EMAIL=your@email.com   to .env and retry.")
        sys.exit(1)
    return email


def verify_admin(provided_email: str, admin_email: str) -> None:
    """Abort if the provided e-mail doesn't match the registered admin."""
    if provided_email.strip().lower() != admin_email:
        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║  ❌  ACCESS DENIED                               ║")
        print("║  The e-mail you entered does not match the       ║")
        print("║  registered admin account.                       ║")
        print("╚══════════════════════════════════════════════════╝")
        sys.exit(1)


def do_encrypt(admin_email: str, secret: str) -> None:
    print(f"\n  📦  Encrypting database …")
    print(f"      Source  : {DB_PATH}")
    print(f"      Output  : {ENC_PATH}")
    print(f"      Admin   : {admin_email}")
    print()

    if not DB_PATH.exists():
        print(f"  ❌  {DB_PATH} not found — run the app first to create the database.")
        sys.exit(1)

    from db_crypto import encrypt_db
    encrypt_db(str(DB_PATH), str(ENC_PATH), admin_email, secret)

    print()
    print("  ✅  Done! Commit instance/sentinel.db.enc to GitHub.")
    print("      The plain sentinel.db is excluded via .gitignore.")


def do_decrypt(admin_email: str, secret: str) -> None:
    print(f"\n  🔓  Decrypting database …")
    print(f"      Source  : {ENC_PATH}")
    print(f"      Output  : {DB_PATH}")
    print(f"      Admin   : {admin_email}")
    print()

    if not ENC_PATH.exists():
        print(f"  ❌  {ENC_PATH} not found.")
        print("      Encrypt first:  python admin_decrypt.py --action encrypt --email <email>")
        sys.exit(1)

    from db_crypto import decrypt_db
    try:
        decrypt_db(str(ENC_PATH), str(DB_PATH), admin_email, secret)
    except ValueError as exc:
        print(f"\n  ❌  {exc}")
        sys.exit(1)

    print()
    print("  ✅  Database decrypted and ready for use.")
    print("      ⚠️   Do NOT commit sentinel.db to GitHub.")


def main() -> None:
    print(BANNER)

    parser = argparse.ArgumentParser(
        description="SentinelTransfer — Admin Database Encryption Tool"
    )
    parser.add_argument(
        "--email", required=True,
        help="Your admin e-mail address (must match ADMIN_EMAIL in .env)"
    )
    parser.add_argument(
        "--action", choices=["encrypt", "decrypt"], default="decrypt",
        help="'encrypt' to lock DB for GitHub  |  'decrypt' to unlock for local use"
    )
    args = parser.parse_args()

    admin_email = get_admin_email()
    verify_admin(args.email, admin_email)

    secret = os.environ.get(
        "SECRET_KEY",
        "sentinel-transfer-secure-key-2026-change-in-production"
    )

    if args.action == "encrypt":
        do_encrypt(admin_email, secret)
    else:
        do_decrypt(admin_email, secret)


if __name__ == "__main__":
    main()
