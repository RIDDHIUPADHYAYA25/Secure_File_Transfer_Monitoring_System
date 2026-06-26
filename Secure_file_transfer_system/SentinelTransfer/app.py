# app.py — SentinelTransfer with Custom Auth (Email OTP + Password)
import sys
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

from flask import (Flask, render_template, jsonify, request,
                   session, redirect, url_for, flash, send_file)
from datetime import datetime, timedelta
import os
import sqlite3
import random
import re
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from dotenv import load_dotenv
from contextlib import contextmanager
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SentinelTransfer")

db_lock = threading.Lock()
_last_processed_events = {}
_debounce_lock = threading.Lock()

try:
    import win32api  # type: ignore
except Exception:
    win32api = None

load_dotenv()

import atexit

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sentinel-transfer-secure-key-2026-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# ==================================================
# FLASK-MAIL CONFIGURATION
# ==================================================
app.config['MAIL_SERVER']           = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT']             = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS']          = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL']          = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME']         = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD']         = os.environ.get('MAIL_PASSWORD', '')

# Ensure sender matches MAIL_USERNAME if a dummy/default sender is set, to avoid SMTP auth/spoofing errors
mail_username = os.environ.get('MAIL_USERNAME', '').strip()
mail_default_sender = os.environ.get('MAIL_DEFAULT_SENDER', '').strip()

if not mail_default_sender or mail_default_sender == 'noreply@sentineltransfer.com':
    app.config['MAIL_DEFAULT_SENDER'] = mail_username if mail_username else 'noreply@sentineltransfer.com'
else:
    app.config['MAIL_DEFAULT_SENDER'] = mail_default_sender

mail = Mail(app)

# ==================================================
# DATABASE SETUP
# ==================================================
def _db_path():
    os.makedirs(app.instance_path, exist_ok=True)
    return os.path.join(app.instance_path, 'sentinel.db')

def _enc_path():
    return os.path.join(app.instance_path, 'sentinel.db.enc')

def _auto_decrypt_on_startup():
    """If the encrypted DB exists but the plain DB doesn't, auto-decrypt using ADMIN_EMAIL."""
    db  = _db_path()
    enc = _enc_path()
    if not os.path.exists(db) and os.path.exists(enc):
        admin_email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
        secret      = app.secret_key
        if admin_email:
            try:
                from db_crypto import decrypt_db
                print('[SentinelTransfer] Encrypted database detected — auto-decrypting …')
                decrypt_db(enc, db, admin_email, secret)
                print('[SentinelTransfer] Database ready.')
            except Exception as exc:
                print(f'[SentinelTransfer] ⚠️  Auto-decrypt failed: {exc}')
                print('[SentinelTransfer]    Run:  python admin_decrypt.py --action decrypt --email <admin_email>')
        else:
            print('[SentinelTransfer] ⚠️  Encrypted database found but ADMIN_EMAIL is not set in .env.')
            print('[SentinelTransfer]    Run:  python admin_decrypt.py --action decrypt --email <admin_email>')

def _auto_encrypt_on_shutdown():
    """Re-encrypt the database when the app shuts down cleanly."""
    db  = _db_path()
    enc = _enc_path()
    admin_email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    secret      = app.secret_key
    if os.path.exists(db) and admin_email:
        try:
            from db_crypto import encrypt_db
            encrypt_db(db, enc, admin_email, secret)
            print('[SentinelTransfer] Database re-encrypted on shutdown.')
        except Exception as exc:
            print(f'[SentinelTransfer] ⚠️  Re-encryption on shutdown failed: {exc}')

@contextmanager
def get_db():
    conn = sqlite3.connect(
        _db_path(),
        timeout=30,
        check_same_thread=False
    )
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()
def is_db_ready():
    db_path = _db_path()
    enc_path = _enc_path()
    
    # If the encrypted DB exists but the decrypted one does not, we are locked
    if os.path.exists(enc_path) and not os.path.exists(db_path):
        return False
    
    # If the database file doesn't exist at all (and no enc_path), it's not ready yet
    if not os.path.exists(db_path):
        return False
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        row = cursor.fetchone()
        conn.close()
        return row is not None
    except sqlite3.Error:
        return False

# ==================================================
# ADDITIONAL IMPORT STATEMENTS FOR MONITORING
# ==================================================
import hashlib
import threading
import time
import getpass
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import psutil

# ==================================================
# REAL-TIME FILE SYSTEM MONITOR (WATCHDOG)
# ==================================================
def get_process_for_file(filepath):
    try:
        for proc in psutil.process_iter(['pid', 'name', 'open_files']):
            try:
                for f in proc.info.get('open_files') or []:
                    if f.path == filepath:
                        return proc.info['name']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    try:
        return psutil.Process().name()
    except Exception:
        return 'explorer.exe'

def get_current_user():
    try:
        return getpass.getuser()
    except Exception:
        return 'system'

def _get_win32file_module():
    try:
        import win32file
        return win32file
    except Exception:
        return None

def is_path_on_usb(filepath):
    if not filepath:
        return False
    drive, _ = os.path.splitdrive(filepath)
    if not drive:
        return False

    win32file = _get_win32file_module()
    if win32file:
        try:
            if win32file.GetDriveType(drive + '\\') in (win32file.DRIVE_REMOVABLE, win32file.DRIVE_CDROM):
                return True
        except Exception:
            pass

    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            if part.mountpoint.upper().startswith(drive.upper()):
                if 'removable' in part.opts or 'cdrom' in part.opts:
                    return True
    except Exception:
        pass
    return False

class SentinelFileSystemHandler(FileSystemEventHandler):
    def __init__(self, app):
        self.app = app

    def process_event(self, event_type, src_path, dest_path=None):
        print(f"[DEBUG 1] process_event entered for {event_type} - {src_path}", flush=True)
        if os.path.basename(src_path).startswith('.') or '~' in src_path:
            print(f"[DEBUG] process_event early return: starts with dot or contains tilde", flush=True)
            return
        if dest_path and (os.path.basename(dest_path).startswith('.') or '~' in dest_path):
            print(f"[DEBUG] process_event early return: dest_path starts with dot or contains tilde", flush=True)
            return

        print(f"[DEBUG 2] basic path checks passed", flush=True)
        filepath = dest_path if dest_path else src_path
        if os.path.isdir(filepath):
            print(f"[DEBUG] process_event early return: filepath is dir", flush=True)
            return

        print(f"[DEBUG 3] dir check passed", flush=True)
        # Event debouncing & duplicate record prevention (within 1 second)
        now = time.time()
        with _debounce_lock:
            key = (filepath, event_type)
            last_time = _last_processed_events.get(key, 0)
            if now - last_time < 1.0:
                print(f"[DEBUG] process_event early return: debounced", flush=True)
                return
            _last_processed_events[key] = now

        print(f"[DEBUG 4] debounce check passed", flush=True)
        file_name = os.path.basename(filepath)
        time.sleep(0.5)

        print(f"[DEBUG 5] slept 0.5s, checking exist", flush=True)
        if not os.path.exists(filepath) and event_type != 'Deleted':
            print(f"[DEBUG] process_event early return: filepath does not exist", flush=True)
            return

        print(f"[DEBUG 6] exist check passed. event_type={event_type}", flush=True)
        pre_hash = None
        post_hash = None

        if os.path.exists(filepath):
            print(f"[DEBUG 7] calculating hash", flush=True)
            try:
                hasher = hashlib.sha256()
                with open(filepath, "rb") as f:
                    while chunk := f.read(8192):
                        hasher.update(chunk)
                post_hash = hasher.hexdigest()
                print(f"[DEBUG 8] hash calculated: {post_hash}", flush=True)
            except Exception as e:
                print(f"[DEBUG 9] hash failed: {e}", flush=True)

        print(f"[DEBUG 10] entering app_context", flush=True)
        with self.app.app_context():
            print(f"[DEBUG 11] app_context entered", flush=True)
            try:
                print(f"[DEBUG 12] getting db connection", flush=True)
                with get_db() as db:
                    print(f"[DEBUG 13] db connection obtained", flush=True)
                    src_dir = os.path.abspath(os.path.dirname(src_path))
                    dest_dir = os.path.abspath(os.path.dirname(dest_path)) if dest_path else None

                    # Read sensitive files from sensitive_files.txt
                    txt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sensitive_files.txt')
                    sensitive_list = []
                    if os.path.exists(txt_path):
                        try:
                            with open(txt_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    s_line = line.strip()
                                    if s_line and not s_line.startswith('#'):
                                        sensitive_list.append(s_line.lower())
                        except Exception as ex:
                            logger.exception("Error reading sensitive_files.txt")
                    else:
                        try:
                            with open(txt_path, 'w', encoding='utf-8') as f:
                                f.write("# List sensitive file names here (one per line)\n")
                                f.write("# Add only real sensitive file names from your monitored directories.\n")
                        except Exception:
                            pass

                    is_sensitive = False
                    classification = 'Confidential'
                    protection_status = 'Medium'

                    if file_name.lower() in sensitive_list:
                        is_sensitive = True
                        classification = 'Confidential'
                        protection_status = 'High'

                    row = db.execute("SELECT * FROM sensitive_files WHERE name = ? OR location = ? OR location = ?",
                                     (file_name, src_dir + os.sep, (dest_dir + os.sep) if dest_dir else '')).fetchone()
                    if row:
                        is_sensitive = True
                        classification = row['classification']
                        protection_status = row['protection_status']

                    lower_name = file_name.lower()
                    if any(k in lower_name for k in ['confidential', 'payroll', 'financial', 'employee', 'password', 'api_key']):
                        is_sensitive = True
                        classification = 'Financial' if 'financial' in lower_name else 'Confidential'
                        protection_status = 'High'

                    status = 'info'
                    severity = 'info'
                    severity_reason = 'Normal file creation' if event_type == 'Created' else 'Normal file modification' if event_type == 'Modified' else 'Normal file deletion' if event_type == 'Deleted' else f"File {event_type.lower()} event detected."
                    alert_reason = 'Normal file event'
                    alert_type = 'None'
                    details = f"File {event_type.lower()} event detected."

                    # Check Integrity registry with try-except to prevent watchdog crash
                    try:
                        reg_row = db.execute("SELECT * FROM integrity_files WHERE file_path = ?", (filepath,)).fetchone()
                        if reg_row:
                            pre_hash = reg_row['original_hash']
                            if post_hash:
                                if pre_hash == post_hash:
                                    with db_lock:
                                        db.execute("UPDATE integrity_files SET current_hash = ?, status = 'valid', last_verified = ? WHERE id = ?",
                                                   (post_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reg_row['id']))
                                        db.commit()
                                else:
                                    status = 'critical'
                                    severity = 'critical'
                                    severity_reason = 'Hash mismatch detected'
                                    alert_reason = 'Hash mismatch detected'
                                    alert_type = 'Integrity'
                                    details = f"Hash mismatch detected for sensitive integrity file {file_name}."
                                    with db_lock:
                                        db.execute("UPDATE integrity_files SET current_hash = ?, status = 'failed', last_verified = ? WHERE id = ?",
                                                   (post_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), reg_row['id']))
                                        db.commit()
                        elif post_hash and event_type in ('Created', 'Modified') and not is_path_on_usb(filepath):
                            # Auto register if in monitored folders
                            dir_rows = db.execute("SELECT path FROM monitored_directories").fetchall()
                            in_monitored = False
                            for r in dir_rows:
                                if filepath.startswith(os.path.abspath(r['path'])):
                                    in_monitored = True
                                    break
                            if in_monitored:
                                with db_lock:
                                    db.execute("INSERT OR IGNORE INTO integrity_files (file_name, file_path, original_hash, current_hash, status, last_verified) VALUES (?, ?, ?, ?, 'valid', ?)",
                                               (file_name, filepath, post_hash, post_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                                    db.commit()
                    except Exception as integrity_ex:
                        logger.exception("Database write failure during integrity_files check")

                    # Check USB
                    drive, _ = os.path.splitdrive(filepath)
                    is_usb = is_path_on_usb(filepath) or (dest_path and is_path_on_usb(dest_path))
                    
                    if is_usb:
                        alert_type = 'USB Copy'
                        if is_sensitive:
                            status = 'critical'
                            severity = 'critical'
                            severity_reason = 'Sensitive file copied to removable USB drive'
                            alert_reason = 'Sensitive file copied to removable USB drive'
                            details = f"Sensitive file {file_name} copied or moved to a removable USB drive {drive}."
                        else:
                            status = 'warning'
                            severity = 'warning'
                            severity_reason = 'File copied or moved to removable USB drive'
                            alert_reason = 'File copied or moved to removable USB drive'
                            details = f"File {file_name} copied or moved to removable USB drive {drive}."
                    elif is_sensitive and alert_type != 'Integrity':
                        alert_type = 'DLP Policy'
                        if event_type == 'Deleted':
                            status = 'critical'
                            severity = 'critical'
                            severity_reason = 'Unauthorized deletion detected'
                            alert_reason = 'Unauthorized deletion detected'
                            details = f"Unauthorized deletion detected for sensitive file: {src_path}."
                        elif event_type == 'Modified':
                            status = 'warning'
                            severity = 'warning'
                            severity_reason = 'Sensitive file modified'
                            alert_reason = 'Sensitive file modified'
                            details = f"Sensitive file modified: {src_path}."
                        elif event_type == 'Moved':
                            status = 'warning'
                            severity = 'warning'
                            severity_reason = 'Sensitive file moved outside monitored directory'
                            alert_reason = 'Sensitive file moved outside monitored directory'
                            details = f"Sensitive file moved from {src_path} to {dest_path}."
                        else:
                            status = 'warning'
                            severity = 'warning'
                            severity_reason = 'Sensitive file accessed'
                            alert_reason = 'Sensitive file accessed'
                            details = f"Sensitive file access detected: {src_path}."
                    else:
                        if status == 'info':
                            if event_type == 'Created':
                                details = f"Normal file created: {src_path}."
                                severity_reason = 'Normal file creation'
                                alert_reason = 'Normal file creation'
                            elif event_type == 'Modified':
                                details = f"Normal file modified: {src_path}."
                                severity_reason = 'Normal file modification'
                                alert_reason = 'Normal file modification'
                            elif event_type == 'Deleted':
                                details = f"File deleted: {src_path}."
                                severity_reason = 'Normal file deletion'
                                alert_reason = 'Normal file deletion'
                            elif event_type == 'Moved':
                                details = f"File moved from {src_path} to {dest_path}."
                                severity_reason = 'Normal file movement'
                                alert_reason = 'Normal file movement'
                            else:
                                alert_reason = f"{event_type} event detected"
                                severity_reason = alert_reason

                    status = severity

                    user = get_current_user()
                    process_name = get_process_for_file(filepath)

                    # Audit logs write with try-except to ensure success even if integrity checks fail
                    try:
                        print(f"[DEBUG] process_event: attempting to insert audit_logs", flush=True)
                        with db_lock:
                            db.execute('''
                                INSERT INTO audit_logs (timestamp, event_type, file_name, source_path, destination_path, user, process_name, status, severity, severity_reason, alert_reason, pre_hash, post_hash, details, sha256_hash, alert_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                event_type,
                                file_name,
                                src_path,
                                dest_path,
                                user,
                                process_name,
                                status,
                                severity,
                                severity_reason,
                                alert_reason,
                                pre_hash,
                                post_hash,
                                details,
                                post_hash,
                                alert_type
                            ))
                            db.commit()
                        print(f"[DEBUG] process_event: audit_logs inserted and committed successfully", flush=True)
                    except Exception as audit_ex:
                        print(f"[DEBUG] process_event: audit_logs insert failed: {audit_ex}", flush=True)
                        logger.exception("Database write failure during audit_logs insert")

                    if status in ('warning', 'critical'):
                        admin_email = os.environ.get('ADMIN_EMAIL')
                        if admin_email:
                            subject = f"🛡️ SentinelTransfer ALERT: {status.upper()} Event Detected"
                            body = f"""
                            <div style="font-family:'Inter',sans-serif;background:#0a0c12;padding:40px;color:#e9ecef;">
                                <h2>🛡️ Security Event Alert</h2>
                                <p>A policy violation event has been detected on the file system.</p>
                                <hr style="border:none;border-top:1px solid #23252e;">
                                <p><strong>Type:</strong> {event_type}</p>
                                <p><strong>File:</strong> {file_name}</p>
                                <p><strong>Path:</strong> {filepath}</p>
                                <p><strong>Details:</strong> {details}</p>
                                <p><strong>Severity:</strong> {status.upper()}</p>
                                <p><strong>User:</strong> {user}</p>
                                <p><strong>Process:</strong> {process_name}</p>
                            </div>
                            """
                            send_email(admin_email, subject, body)
            except Exception as conn_ex:
                logger.exception("Connection or global context error inside process_event")

    def on_created(self, event):
        print(f"[DEBUG] on_created called for {event.src_path}", flush=True)
        if not event.is_directory:
            self.process_event('Created', event.src_path)
            

    def on_modified(self, event):
        print(f"[DEBUG] on_modified called for {event.src_path}", flush=True)
        if not event.is_directory:
            self.process_event('Modified', event.src_path)
        print("FILE MODIFIED:", event.src_path, flush=True)    

    def on_deleted(self, event):
        print(f"[DEBUG] on_deleted called for {event.src_path}", flush=True)
        if not event.is_directory:
            self.process_event('Deleted', event.src_path)

    def on_moved(self, event):
        print(f"[DEBUG] on_moved called from {event.src_path} to {event.dest_path}", flush=True)
        if not event.is_directory:
            self.process_event('Moved', event.src_path, event.dest_path)

active_usb_watches = {} # maps drive_letter -> watch_object

def usb_poller_thread(app):
    global active_usb_watches, observer
    handler = SentinelFileSystemHandler(app)
    
    while True:
        try:
            # Detect removable drives
            import psutil
            drives = []
            for part in psutil.disk_partitions(all=False):
                if 'removable' in part.opts or 'cdrom' in part.opts:
                    drives.append(part.mountpoint)
            
            # For Windows, check with win32file if psutil didn't catch or to be extra robust
            win32file = _get_win32file_module()
            if win32file:
                try:
                    import string
                    for letter in string.ascii_uppercase:
                        drive = f"{letter}:\\"
                        if win32file.GetDriveType(drive) == win32file.DRIVE_REMOVABLE:
                            if drive not in drives:
                                drives.append(drive)
                except Exception:
                    pass
            
            # Normalize drive paths
            current_usb_paths = [os.path.abspath(d) for d in drives if os.path.exists(d)]
            
            # Remove watches for unplugged USBs
            unplugged = [d for d in active_usb_watches if d not in current_usb_paths]
            for d in unplugged:
                if observer:
                    try:
                        observer.unschedule(active_usb_watches[d])
                        print(f"[SentinelTransfer] Unscheduled USB watch for: {d}")
                    except Exception as e:
                        print(f"[SentinelTransfer] Error unscheduling watch for {d}: {e}")
                del active_usb_watches[d]
                
            # Add watches for new USBs
            for d in current_usb_paths:
                if d not in active_usb_watches:
                    if observer:
                        try:
                            # Watch the USB drive root directory recursively
                            watch = observer.schedule(handler, d, recursive=True)
                            active_usb_watches[d] = watch
                            print(f"[SentinelTransfer] Dynamically scheduled USB watch for: {d}")
                        except Exception as e:
                            print(f"[SentinelTransfer] Error scheduling watch for USB {d}: {e}")
                            
        except Exception as e:
            print(f"[SentinelTransfer] USB Poller Error: {e}")
            
        time.sleep(3)

observer = None

def start_file_monitoring(app):
    global observer
    if observer:
        try:
            observer.stop()
            observer.join()
        except Exception:
            pass

    observer = Observer()
    handler = SentinelFileSystemHandler(app)

    with app.app_context():
        try:
            with get_db() as db:
                rows = db.execute("SELECT path, recursive FROM monitored_directories").fetchall()
                for row in rows:
                    path = os.path.abspath(row['path'])
                    recursive = bool(row['recursive'])
                    if os.path.exists(path):
                        observer.schedule(handler, path, recursive=recursive)
                        print(f"[SentinelTransfer] Monitoring path: {path} (recursive={recursive})")
                    else:
                        print(f"[SentinelTransfer] Monitored directory path does not exist: {path}")
            observer.start()
            
            # Start dynamic USB poller
            t = threading.Thread(target=usb_poller_thread, args=(app,), daemon=True)
            t.start()
            print("[SentinelTransfer] Started dynamic USB poller thread.")
            
        except Exception as e:
            print(f"[SentinelTransfer] Failed to start Observer: {e}")

def get_monitored_directories():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM monitored_directories").fetchall()
        return [dict(row) for row in rows]

def add_monitored_directory(name, path, recursive=1):
    with get_db() as conn:
        with db_lock:
            conn.execute("INSERT INTO monitored_directories (name, path, recursive) VALUES (?, ?, ?)",
                         (name, path, recursive))
            conn.commit()

def remove_monitored_directory(dir_id):
    with get_db() as conn:
        with db_lock:
            conn.execute("DELETE FROM monitored_directories WHERE id = ?", (dir_id,))
            conn.commit()

def get_sensitive_files():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM sensitive_files").fetchall()
        return [dict(row) for row in rows]

def add_sensitive_file(name, location, protection_status='Medium', classification='Confidential'):
    with get_db() as conn:
        with db_lock:
            conn.execute("INSERT OR REPLACE INTO sensitive_files (name, location, protection_status, classification) VALUES (?, ?, ?, ?)",
                         (name, location, protection_status, classification))
            conn.commit()

def remove_sensitive_file(file_id):
    with get_db() as conn:
        with db_lock:
            conn.execute("DELETE FROM sensitive_files WHERE id = ?", (file_id,))
            conn.commit()

def run_integrity_scan():
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        directories = conn.execute("SELECT path, recursive FROM monitored_directories").fetchall()
        found_files = []
        for d in directories:
            dpath = d['path']
            recursive = bool(d['recursive'])
            if not os.path.exists(dpath):
                continue
            if recursive:
                for root, _, files in os.walk(dpath):
                    for f in files:
                        found_files.append(os.path.join(root, f))
            else:
                for f in os.listdir(dpath):
                    fpath = os.path.join(dpath, f)
                    if os.path.isfile(fpath):
                        found_files.append(fpath)

        for filepath in found_files:
            file_name = os.path.basename(filepath)
            try:
                hasher = hashlib.sha256()
                with open(filepath, "rb") as f:
                    while chunk := f.read(8192):
                        hasher.update(chunk)
                hval = hasher.hexdigest()

                row = conn.execute("SELECT * FROM integrity_files WHERE file_path = ?", (filepath,)).fetchone()
                if row:
                    original_hash = row['original_hash']
                    status = 'valid' if original_hash == hval else 'failed'
                    with db_lock:
                        conn.execute("UPDATE integrity_files SET current_hash = ?, status = ?, last_verified = ? WHERE id = ?",
                                     (hval, status, now_str, row['id']))
                        conn.commit()
                else:
                    with db_lock:
                        conn.execute("INSERT INTO integrity_files (file_name, file_path, original_hash, current_hash, status, last_verified) VALUES (?, ?, ?, ?, 'valid', ?)",
                                     (file_name, filepath, hval, hval, now_str))
                        conn.commit()
            except Exception:
                continue

        reg_rows = conn.execute("SELECT id, file_path FROM integrity_files").fetchall()
        for r in reg_rows:
            if not os.path.exists(r['file_path']):
                with db_lock:
                    conn.execute("UPDATE integrity_files SET status = 'failed', last_verified = ? WHERE id = ?",
                                 (now_str, r['id']))
                    conn.commit()

def init_db():
    _auto_decrypt_on_startup()
    db_path = _db_path()
    enc_path = _enc_path()
    
    if os.path.exists(enc_path) and not os.path.exists(db_path):
        print('[SentinelTransfer] ⚠️  Database sentinel.db is encrypted/locked. Skipping initialization.')
        return
        
    try:
        with get_db() as conn:
            with db_lock:
                cursor = conn.cursor()
                schema_outdated = False
                try:
                    cursor.execute("SELECT username FROM users LIMIT 1")
                except sqlite3.OperationalError:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
                    if cursor.fetchone() is not None:
                        schema_outdated = True

                if schema_outdated:
                    print('[SentinelTransfer] Outdated schema detected, rebuilding users table...')
                    conn.execute("DROP TABLE IF EXISTS users")
                    conn.commit()

                conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                        first_name            TEXT NOT NULL,
                        last_name             TEXT NOT NULL,
                        username              TEXT UNIQUE NOT NULL,
                        email                 TEXT UNIQUE NOT NULL,
                        mobile                TEXT,
                        country               TEXT,
                        password_hash         TEXT NOT NULL,
                        is_verified           INTEGER DEFAULT 0,
                        verification_code     TEXT,
                        verification_expires  TEXT,
                        reset_otp             TEXT,
                        reset_otp_expires     TEXT,
                        created_at            TEXT NOT NULL,
                        last_login            TEXT
                    )
                ''')
                
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS monitored_directories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        path TEXT UNIQUE NOT NULL,
                        recursive INTEGER DEFAULT 1,
                        files_monitored INTEGER DEFAULT 0
                    )
                ''')
                
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS sensitive_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        location TEXT NOT NULL,
                        protection_status TEXT DEFAULT 'Medium',
                        last_access TEXT,
                        classification TEXT DEFAULT 'Confidential',
                        UNIQUE(name, location)
                    )
                ''')
                
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        destination_path TEXT,
                        user TEXT,
                        process_name TEXT,
                        status TEXT DEFAULT 'info',
                        severity TEXT DEFAULT 'info',
                        severity_reason TEXT,
                        alert_reason TEXT,
                        pre_hash TEXT,
                        post_hash TEXT,
                        details TEXT,
                        sha256_hash TEXT,
                        alert_type TEXT DEFAULT 'None'
                    )
                ''')
                
                # Migration check: add columns if they don't exist
                cursor.execute("PRAGMA table_info(audit_logs)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'sha256_hash' not in columns:
                    conn.execute("ALTER TABLE audit_logs ADD COLUMN sha256_hash TEXT")
                if 'alert_type' not in columns:
                    conn.execute("ALTER TABLE audit_logs ADD COLUMN alert_type TEXT DEFAULT 'None'")
                if 'severity' not in columns:
                    conn.execute("ALTER TABLE audit_logs ADD COLUMN severity TEXT DEFAULT 'info'")
                if 'severity_reason' not in columns:
                    conn.execute("ALTER TABLE audit_logs ADD COLUMN severity_reason TEXT")
                if 'alert_reason' not in columns:
                    conn.execute("ALTER TABLE audit_logs ADD COLUMN alert_reason TEXT")
                
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS integrity_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        file_path TEXT UNIQUE NOT NULL,
                        original_hash TEXT NOT NULL,
                        current_hash TEXT,
                        status TEXT DEFAULT 'valid',
                        last_verified TEXT
                    )
                ''')
                
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS report_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        generated_at TEXT NOT NULL,
                        report_type TEXT NOT NULL,
                        time_period TEXT NOT NULL,
                        format TEXT NOT NULL,
                        record_count INTEGER,
                        status TEXT NOT NULL
                    )
                ''')
                
                cursor.execute("SELECT COUNT(*) FROM monitored_directories")
                if cursor.fetchone()[0] == 0:
                    default_monitored_path = os.path.abspath(os.path.join(app.instance_path, 'monitored_folder'))
                    os.makedirs(default_monitored_path, exist_ok=True)
                    
                    conn.execute("INSERT OR IGNORE INTO monitored_directories (name, path, recursive) VALUES (?, ?, ?)",
                                 ("Sentinel Monitor Directory", default_monitored_path, 1))
                                 
                    default_file = os.path.join(default_monitored_path, "confidential_memo.txt")
                    if not os.path.exists(default_file):
                        with open(default_file, "w") as f:
                            f.write("CONFIDENTIAL: Under no circumstances should this file be copied or moved without authorization.")
                    
                    try:
                        hasher = hashlib.sha256()
                        with open(default_file, "rb") as f:
                            hasher.update(f.read())
                        hval = hasher.hexdigest()
                        
                        conn.execute("INSERT OR IGNORE INTO sensitive_files (name, location, protection_status, classification) VALUES (?, ?, ?, ?)",
                                     ("confidential_memo.txt", default_monitored_path + os.sep, "High", "Confidential"))
                                     
                        conn.execute("INSERT OR IGNORE INTO integrity_files (file_name, file_path, original_hash, current_hash, status, last_verified) VALUES (?, ?, ?, ?, ?, ?)",
                                     ("confidential_memo.txt", default_file, hval, hval, "valid", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                    except Exception as ex:
                        print(f"[SentinelTransfer] Error creating default monitoring file: {ex}")
                        
                conn.commit()
        atexit.register(_auto_encrypt_on_shutdown)
    except sqlite3.Error as e:
        print(f'[SentinelTransfer] Database init failed: {e}')

with app.app_context():
    init_db()
    start_file_monitoring(app)

# ==================================================
# DB HELPERS
# ==================================================
def get_user_by_username(username):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        return dict(row) if row else None

def get_user_by_email(email):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE email = ?', (email.lower(),)).fetchone()
        return dict(row) if row else None

def create_user(first_name, last_name, username, email, mobile, country,
                password_hash, verification_code, verification_expires):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        with db_lock:
            conn.execute('''
                INSERT INTO users
                  (first_name, last_name, username, email, mobile, country,
                   password_hash, is_verified, verification_code, verification_expires, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            ''', (first_name, last_name, username, email.lower(), mobile, country,
                  password_hash, verification_code, verification_expires, now))
            conn.commit()

def mark_user_verified(user_id):
    with get_db() as conn:
        with db_lock:
            conn.execute('''UPDATE users SET is_verified=1, verification_code=NULL,
                            verification_expires=NULL WHERE id=?''', (user_id,))
            conn.commit()

def set_verification_code(user_id, code, expires):
    with get_db() as conn:
        with db_lock:
            conn.execute('UPDATE users SET verification_code=?, verification_expires=? WHERE id=?',
                         (code, expires, user_id))
            conn.commit()

def set_reset_otp(user_id, otp, expires):
    with get_db() as conn:
        with db_lock:
            conn.execute('UPDATE users SET reset_otp=?, reset_otp_expires=? WHERE id=?',
                         (otp, expires, user_id))
            conn.commit()

def update_password(user_id, password_hash):
    with get_db() as conn:
        with db_lock:
            conn.execute('UPDATE users SET password_hash=?, reset_otp=NULL, reset_otp_expires=NULL WHERE id=?',
                         (password_hash, user_id))
            conn.commit()

def update_last_login(user_id):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db() as conn:
        with db_lock:
            conn.execute('UPDATE users SET last_login=? WHERE id=?', (now, user_id))
            conn.commit()

# ==================================================
# OTP GENERATOR
# ==================================================
def generate_otp(length=6):
    return ''.join([str(random.randint(0, 9)) for _ in range(length)])

# ==================================================
# EMAIL HELPERS
# ==================================================
def send_email(to_email, subject, html_body):
    """Send email. Falls back to console print if SMTP not configured."""
    if not app.config.get('MAIL_USERNAME'):
        print(f"\n{'='*60}")
        print(f"[EMAIL SIMULATION — Configure SMTP to send real emails]")
        print(f"TO:      {to_email}")
        print(f"SUBJECT: {subject}")
        # Extract OTP from HTML for console display
        import re
        otps = re.findall(r'\b(\d{4,6})\b', html_body)
        if otps:
            print(f"OTP/CODE: {otps[0]}")
        print(f"{'='*60}\n")
        return True
    try:
        with app.app_context():
            sender = app.config.get('MAIL_DEFAULT_SENDER') or app.config.get('MAIL_USERNAME')
            msg = Message(subject, recipients=[to_email], html=html_body, sender=sender)
            mail.send(msg)
        return True
    except Exception as e:
        print(f"[Email Error] {e}")
        return False

def send_verification_email(email, first_name, code):
    subject = "Verify your SentinelTransfer account"
    html = f"""
    <div style="font-family:'Inter',Arial,sans-serif;background:#0a0c12;padding:40px 20px;max-width:480px;margin:auto;">
      <div style="background:#1a1d2b;border-radius:16px;padding:36px;border:1px solid rgba(255,255,255,0.06);">
        <div style="text-align:center;margin-bottom:28px;">
          <div style="display:inline-block;background:linear-gradient(135deg,#0d6efd,#0a58ca);
                      border-radius:14px;padding:14px 18px;margin-bottom:12px;">
            <span style="font-size:28px;">🛡</span>
          </div>
          <h1 style="color:#e9ecef;font-size:20px;margin:0;">SentinelTransfer</h1>
        </div>
        <h2 style="color:#e9ecef;font-size:18px;text-align:center;margin-bottom:8px;">
          Verify Your Email Address
        </h2>
        <p style="color:#8b92a8;font-size:14px;text-align:center;line-height:1.6;">
          Hi {first_name}, enter this 6-digit code to activate your account:
        </p>
        <div style="background:#0f1118;border:2px solid #0d6efd;border-radius:12px;
                    padding:24px;text-align:center;margin:24px 0;">
          <span style="font-size:40px;font-weight:800;letter-spacing:14px;color:#6ea8fe;
                       font-family:monospace;">{code}</span>
        </div>
        <p style="color:#8b92a8;font-size:13px;text-align:center;">
          ⏱ This code expires in <strong style="color:#ffc107;">10 minutes</strong>.
        </p>
        <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:20px 0;">
        <p style="color:#6c757d;font-size:12px;text-align:center;">
          If you didn't create this account, you can safely ignore this email.
        </p>
      </div>
    </div>
    """
    return send_email(email, subject, html)

def send_reset_email(email, first_name, otp):
    subject = "Your SentinelTransfer password reset OTP"
    html = f"""
    <div style="font-family:'Inter',Arial,sans-serif;background:#0a0c12;padding:40px 20px;max-width:480px;margin:auto;">
      <div style="background:#1a1d2b;border-radius:16px;padding:36px;border:1px solid rgba(255,255,255,0.06);">
        <div style="text-align:center;margin-bottom:28px;">
          <div style="display:inline-block;background:linear-gradient(135deg,#dc3545,#a71d2a);
                      border-radius:14px;padding:14px 18px;margin-bottom:12px;">
            <span style="font-size:28px;">🔑</span>
          </div>
          <h1 style="color:#e9ecef;font-size:20px;margin:0;">SentinelTransfer</h1>
        </div>
        <h2 style="color:#e9ecef;font-size:18px;text-align:center;margin-bottom:8px;">
          Password Reset Request
        </h2>
        <p style="color:#8b92a8;font-size:14px;text-align:center;line-height:1.6;">
          Hi {first_name}, use this 4-digit OTP to reset your password:
        </p>
        <div style="background:#0f1118;border:2px solid #f59e0b;border-radius:12px;
                    padding:28px;text-align:center;margin:24px 0;">
          <span style="font-size:52px;font-weight:800;letter-spacing:18px;color:#fbbf24;
                       font-family:monospace;">{otp}</span>
        </div>
        <p style="color:#8b92a8;font-size:13px;text-align:center;">
          ⏱ This OTP expires in <strong style="color:#f87171;">5 minutes</strong>.
        </p>
        <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:20px 0;">
        <p style="color:#6c757d;font-size:12px;text-align:center;">
          If you did not request this, please secure your account immediately.
        </p>
      </div>
    </div>
    """
    return send_email(email, subject, html)

# ==================================================
# LOGIN REQUIRED DECORATOR
# ==================================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# ==================================================
# CONTEXT PROCESSOR
# ==================================================
@app.context_processor
def inject_global_variables():
    user = session.get('user', {})
    name = user.get('name', 'User')
    avatar_url = user.get('avatar_url') or (
        f"https://ui-avatars.com/api/?background=0D6EFD&color=fff&bold=true&size=40"
        f"&name={name.replace(' ', '+')}"
    )
    return {
        'current_year': datetime.now().year,
        'app_name': 'SentinelTransfer',
        'app_version': '3.2.1',
        'db_encrypted': not is_db_ready(),
        'current_user': {
            'name': name,
            'email': user.get('email', ''),
            'username': user.get('username', ''),
            'avatar_url': avatar_url,
            'is_authenticated': bool(user)
        }
    }

# ==================================================
# AUTH ROUTES
# ==================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == 'on'

        if not username or not password:
            return render_template('login.html', error='Please enter your username and password.')

        user = get_user_by_username(username)
        if not user:
            return render_template('login.html', error='Invalid username or password.')

        if not user['is_verified']:
            return render_template('login.html',
                error='Your email is not verified. Please check your inbox.',
                show_resend=True, resend_email=user['email'])

        if not check_password_hash(user['password_hash'], password):
            return render_template('login.html', error='Invalid username or password.')

        session.permanent = remember_me
        session['user'] = {
            'id': user['id'],
            'name': f"{user['first_name']} {user['last_name']}",
            'email': user['email'],
            'username': user['username'],
            'avatar_url': None
        }
        update_last_login(user['id'])

        next_url = request.args.get('next') or url_for('dashboard')
        return redirect(next_url)

    return render_template('login.html',
                           success=request.args.get('success'),
                           error=request.args.get('error'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        first_name       = request.form.get('first_name', '').strip()
        last_name        = request.form.get('last_name', '').strip()
        username         = request.form.get('username', '').strip()
        email            = request.form.get('email', '').strip().lower()
        mobile           = request.form.get('mobile', '').strip()
        country          = request.form.get('country', '').strip()
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = []
        if not all([first_name, last_name, username, email, password, confirm_password]):
            errors.append('Please fill in all required fields.')
        elif password != confirm_password:
            errors.append('Passwords do not match.')
        elif len(password) < 8:
            errors.append('Password must be at least 8 characters long.')

        if not errors:
            if get_user_by_username(username):
                errors.append('Username is already taken. Please choose another.')
            if get_user_by_email(email):
                errors.append('An account with this email already exists.')

        if errors:
            return render_template('signup.html', errors=errors, fd=request.form)

        code    = generate_otp(6)
        expires = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')

        create_user(first_name, last_name, username, email, mobile, country,
                    generate_password_hash(password), code, expires)
        
        email_sent = send_verification_email(email, first_name, code)
        if not app.config.get('MAIL_USERNAME'):
            success_msg = "Account created! [DEMO MODE: Verification code printed to terminal console]"
        elif not email_sent:
            success_msg = "Account created, but we failed to send the verification email. Please check terminal logs or try resending."
        else:
            success_msg = "Verification email sent! Please check your inbox."

        return redirect(url_for('verify_email', email=email, success=success_msg))

    return render_template('signup.html')


@app.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    email = request.args.get('email', '')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        # Collect the six digit boxes into one code
        digits = [request.form.get(f'd{i}', '').strip() for i in range(1, 7)]
        code   = ''.join(digits)

        user = get_user_by_email(email)
        if not user:
            return render_template('verify_email.html', error='Invalid session. Please sign up again.', email=email)

        if user['is_verified']:
            return redirect(url_for('login', success='Account already verified. Please sign in.'))

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if user['verification_code'] != code:
            return render_template('verify_email.html', error='Incorrect verification code. Please try again.', email=email)
        if user['verification_expires'] < now:
            return render_template('verify_email.html',
                error='Code has expired. Please request a new one.', email=email, show_resend=True)

        mark_user_verified(user['id'])
        return redirect(url_for('login', success='✅ Account verified! You can now sign in.'))

    return render_template('verify_email.html', email=email)


@app.route('/resend-verification', methods=['POST'])
def resend_verification():
    email = request.form.get('email', '').strip().lower()
    user  = get_user_by_email(email)
    success_msg = 'A new verification code has been generated.'
    if user and not user['is_verified']:
        code    = generate_otp(6)
        expires = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        set_verification_code(user['id'], code, expires)
        email_sent = send_verification_email(email, user['first_name'], code)
        if not app.config.get('MAIL_USERNAME'):
            success_msg = "Code generated! [DEMO MODE: Code printed to terminal console]"
        elif not email_sent:
            success_msg = "Failed to send verification email. Please check server logs."
        else:
            success_msg = "A new verification code has been sent to your email."
    return redirect(url_for('verify_email', email=email, success=success_msg))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = get_user_by_email(email)
        demo_msg = None
        if user and user['is_verified']:
            otp     = generate_otp(4)
            expires = (datetime.now() + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
            set_reset_otp(user['id'], otp, expires)
            email_sent = send_reset_email(email, user['first_name'], otp)
            if not app.config.get('MAIL_USERNAME'):
                demo_msg = "[DEMO MODE: Password reset OTP printed to terminal console]"
            elif not email_sent:
                demo_msg = "Failed to send recovery email. Please check SMTP settings or terminal logs."
        # Always show success — prevents email enumeration
        return render_template('forgot_password.html', sent=True, email=email, demo_msg=demo_msg)

    return render_template('forgot_password.html')


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = request.args.get('email', '')

    if request.method == 'POST':
        email            = request.form.get('email', '').strip().lower()
        digits           = [request.form.get(f'o{i}', '').strip() for i in range(1, 5)]
        otp              = ''.join(digits)
        new_password     = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not all([email, otp, new_password, confirm_password]):
            return render_template('reset_password.html', error='Please fill in all fields.', email=email)
        if new_password != confirm_password:
            return render_template('reset_password.html', error='Passwords do not match.', email=email)
        if len(new_password) < 8:
            return render_template('reset_password.html', error='Password must be at least 8 characters.', email=email)

        user = get_user_by_email(email)
        if not user:
            return render_template('reset_password.html', error='Invalid request.', email=email)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if not user['reset_otp'] or user['reset_otp'] != otp:
            return render_template('reset_password.html', error='Invalid OTP. Please try again.', email=email)
        if user['reset_otp_expires'] < now:
            return render_template('reset_password.html',
                error='OTP has expired. Please request a new one.', email=email, expired=True)

        update_password(user['id'], generate_password_hash(new_password))
        return redirect(url_for('login', success='🔒 Password updated successfully! Please sign in.'))

    return render_template('reset_password.html', email=email)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/live-monitor')
@login_required
def live_monitor():
    return render_template('live_monitor.html', active_page='live_monitor')

@app.route('/sensitive-files')
@login_required
def sensitive_files():
    return render_template('sensitive_files.html', active_page='sensitive_files')

@app.route('/integrity-check')
@login_required
def integrity_check():
    return render_template('integrity_check.html', active_page='integrity_check')

@app.route('/usb-monitoring')
@login_required
def usb_monitoring():
    return render_template('usb_monitoring.html', active_page='usb_monitoring')

@app.route('/audit-logs')
@login_required
def audit_logs():
    return render_template('audit_logs.html', active_page='audit_logs')

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html', active_page='reports')

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html', active_page='settings')

@app.route('/alerts')
@login_required
def alerts():
    return redirect(url_for('audit_logs'))

@app.route('/')
def index_route():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


def _reports_dir():
    reports_path = os.path.join(app.instance_path, 'reports')
    os.makedirs(reports_path, exist_ok=True)
    return reports_path


def _safe_report_filename(report_type, fmt):
    safe_type = re.sub(r'[^A-Za-z0-9_-]+', '_', report_type or 'Security_Report').strip('_')
    safe_type = safe_type[:80] or 'Security_Report'
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{safe_type}_{timestamp}.{fmt}"


def _is_safe_report_path(file_path):
    if not file_path:
        return False
    reports_root = os.path.abspath(_reports_dir())
    candidate = os.path.abspath(file_path)
    return candidate.startswith(reports_root + os.sep) and os.path.isfile(candidate)


def _time_period_filter(time_period):
    normalized = (time_period or 'Last_30_Days').lower()
    now = datetime.now()
    start = None
    end = now

    if normalized == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif normalized == 'yesterday':
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
    elif normalized in ('last_7_days', 'week'):
        start = now - timedelta(days=7)
    elif normalized in ('last_30_days', 'month'):
        start = now - timedelta(days=30)
    elif normalized in ('last_90_days', 'quarter'):
        start = now - timedelta(days=90)
    elif normalized in ('last_12_months', 'year'):
        start = now - timedelta(days=365)

    if not start:
        return '', []

    return ' WHERE timestamp >= ? AND timestamp < ?', [
        start.strftime('%Y-%m-%d %H:%M:%S'),
        end.strftime('%Y-%m-%d %H:%M:%S')
    ]


def _append_condition(where_sql, condition):
    return f"{where_sql} AND {condition}" if where_sql else f" WHERE {condition}"


def _record_report_history(filename, output_path, report_type, time_period, fmt, record_count, status='completed'):
    with get_db() as conn:
        with db_lock:
            conn.execute('''
                INSERT INTO report_history (file_name, file_path, generated_at, report_type, time_period, format, record_count, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                filename,
                output_path,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                report_type,
                time_period,
                fmt,
                record_count,
                status
            ))
            conn.commit()


def _fetch_report_dataset(report_type, time_period):
    where_sql, params = _time_period_filter(time_period)
    with get_db() as conn:
        logs = [dict(row) for row in conn.execute(f"SELECT * FROM audit_logs{where_sql} ORDER BY id DESC", params).fetchall()]
        severity_rows = conn.execute(
            f"SELECT COALESCE(NULLIF(severity, ''), status, 'info') AS severity_label, COUNT(*) AS count FROM audit_logs{where_sql} GROUP BY severity_label",
            params
        ).fetchall()
        event_rows = conn.execute(
            f"SELECT COALESCE(NULLIF(event_type, ''), 'Unknown') AS event_label, COUNT(*) AS count FROM audit_logs{where_sql} GROUP BY event_label ORDER BY count DESC",
            params
        ).fetchall()
        sensitive_where = _append_condition(where_sql, "status IN ('warning', 'critical')")
        usb_where = _append_condition(where_sql, "alert_type = 'USB Copy'")
        integrity_where = _append_condition(where_sql, "(alert_type = 'Integrity' OR status = 'critical')")
        sensitive_events = conn.execute(f"SELECT COUNT(*) FROM audit_logs{sensitive_where}", params).fetchone()[0] or 0
        usb_transfers = conn.execute(f"SELECT COUNT(*) FROM audit_logs{usb_where}", params).fetchone()[0] or 0
        integrity_violations = conn.execute(f"SELECT COUNT(*) FROM audit_logs{integrity_where}", params).fetchone()[0] or 0

    severity_counts = {'info': 0, 'warning': 0, 'critical': 0}
    for row in severity_rows:
        label = (row['severity_label'] or 'info').lower()
        if label not in severity_counts:
            label = 'info'
        severity_counts[label] += row['count']

    return {
        'logs': logs,
        'total_events': len(logs),
        'sensitive_events': sensitive_events,
        'usb_transfers': usb_transfers,
        'integrity_violations': integrity_violations,
        'severity_counts': severity_counts,
        'event_counts': {row['event_label']: row['count'] for row in event_rows}
    }

# ==================================================
# API ENDPOINTS (Real Database Queries)
# ==================================================
@app.route('/api/stats')
@login_required
def api_stats():
    global observer
    watcher_active = observer.is_alive() if observer else False
    
    db_size = 0
    try:
        if os.path.exists(_db_path()):
            db_size = os.path.getsize(_db_path())
    except Exception:
        pass
    
    if db_size < 1024:
        db_size_str = f"{db_size} B"
    elif db_size < 1024 * 1024:
        db_size_str = f"{db_size / 1024:.1f} KB"
    else:
        db_size_str = f"{db_size / (1024 * 1024):.1f} MB"

    with get_db() as conn:
        total_events = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] or 0
        integrity_violations = conn.execute("SELECT COUNT(*) FROM integrity_files WHERE status = 'failed'").fetchone()[0] or 0
        usb_events = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE alert_type = 'USB Copy'").fetchone()[0] or 0
        sensitive_access = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE status IN ('warning', 'critical')").fetchone()[0] or 0
        dlp_hits = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE alert_type = 'DLP Policy'").fetchone()[0] or 0
        critical_events = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'critical'").fetchone()[0] or 0
        warning_events = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'warning'").fetchone()[0] or 0
        
        last_log_row = conn.execute("SELECT timestamp FROM audit_logs ORDER BY id DESC LIMIT 1").fetchone()
        last_log_time = last_log_row['timestamp'] if last_log_row else "N/A"
        
        registered_files = conn.execute("SELECT COUNT(*) FROM integrity_files").fetchone()[0] or 0
        
    return jsonify({
        'total_events': total_events,
        'integrity_violations': integrity_violations,
        'usb_events': usb_events,
        'sensitive_access': sensitive_access,
        'watcher_active': watcher_active,
        'db_size': db_size_str,
        'last_log_time': last_log_time,
        'registered_files': registered_files,
        'dlp_hits': dlp_hits,
        'critical_events': critical_events,
        'warning_events': warning_events
    })

@app.route('/api/sensitive-files')
@login_required
def api_sensitive_files():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM sensitive_files").fetchall()
        files = [dict(row) for row in rows]
    return jsonify(files)

@app.route('/api/sensitive-files/add', methods=['POST'])
@login_required
def add_sensitive_file_route():
    data = request.json
    name = data.get('name')
    location = data.get('location')
    status = data.get('status', 'Medium')
    classification = data.get('classification', 'Confidential')
    
    if not name or not location:
        return jsonify({"success": False, "message": "Name and location are required."}), 400
        
    try:
        add_sensitive_file(name, location, status, classification)
        return jsonify({"success": True, "message": "Sensitive file added successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/sensitive-files/remove/<int:file_id>', methods=['DELETE'])
@login_required
def remove_sensitive_file_route(file_id):
    try:
        remove_sensitive_file(file_id)
        return jsonify({"success": True, "message": "Sensitive file removed successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/directories')
@login_required
def api_directories():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM monitored_directories").fetchall()
        dirs = []
        for r in rows:
            path = r['path']
            files_monitored = 0
            if os.path.exists(path):
                if bool(r['recursive']):
                    for root, _, files in os.walk(path):
                        files_monitored += len(files)
                else:
                    files_monitored = len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])
            dirs.append({
                'id': r['id'],
                'name': r['name'],
                'path': r['path'],
                'recursive': 'Yes' if bool(r['recursive']) else 'No',
                'filesMonitored': files_monitored
            })
    return jsonify(dirs)

@app.route('/api/directories/add', methods=['POST'])
@login_required
def add_directory_route():
    data = request.json
    name = data.get('name')
    path = data.get('path')
    recursive = 1 if data.get('recursive', 'Yes') == 'Yes' else 0
    
    if not name or not path:
        return jsonify({"success": False, "message": "Name and path are required."}), 400
        
    try:
        add_monitored_directory(name, path, recursive)
        start_file_monitoring(app)
        return jsonify({"success": True, "message": "Directory added successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/directories/remove/<int:dir_id>', methods=['DELETE'])
@login_required
def remove_directory_route(dir_id):
    try:
        remove_monitored_directory(dir_id)
        start_file_monitoring(app)
        return jsonify({"success": True, "message": "Directory removed successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/integrity-files')
@login_required
def api_integrity_files():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM integrity_files").fetchall()
        files = []
        for r in rows:
            files.append({
                'id': r['id'],
                'fileName': r['file_name'],
                'originalHash': r['original_hash'],
                'currentHash': r['current_hash'],
                'status': r['status'],
                'lastVerified': r['last_verified']
            })
    return jsonify(files)

@app.route('/api/verify-integrity', methods=['POST'])
@login_required
def verify_integrity():
    try:
        run_integrity_scan()
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM integrity_files").fetchall()
            files = []
            for r in rows:
                files.append({
                    'id': r['id'],
                    'fileName': r['file_name'],
                    'originalHash': r['original_hash'],
                    'currentHash': r['current_hash'],
                    'status': r['status'],
                    'lastVerified': r['last_verified']
                })
        return jsonify({"success": True, "message": "Integrity verification completed", "files": files})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/usb-devices')
@login_required
def api_usb_devices():
    devices = []
    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            if 'removable' in part.opts or 'cdrom' in part.opts:
                drive = part.mountpoint
                label = "Removable Disk"
                try:
                    if win32api is not None:
                        vol = win32api.GetVolumeInformation(drive)
                        if vol[0]:
                            label = vol[0]
                except Exception:
                    pass
                
                with get_db() as conn:
                    copied_count = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE destination_path LIKE ?", (f"{drive}%",)).fetchone()[0] or 0
                
                devices.append({
                    'id': len(devices) + 1,
                    'name': label,
                    'driveLetter': drive.rstrip('\\'),
                    'connectionTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'filesCopied': copied_count,
                    'status': 'active',
                    'manufacturer': 'Generic',
                    'serialNumber': 'Removable'
                })
    except Exception as e:
        print(f"[USB Detect Error] {e}")
        
    return jsonify(devices)

@app.route('/api/audit-logs')
@login_required
def api_audit_logs():
    limit = request.args.get('limit', default=100, type=int)
    severity = request.args.get('severity', default=None, type=str)
    event_type = request.args.get('event_type', default=None, type=str)
    file_filter = request.args.get('file_name', default=None, type=str)
    
    with get_db() as conn:
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params = []
        if severity and severity != 'all':
            query += " AND status = ?"
            params.append(severity)
        if event_type and event_type != 'all':
            query += " AND event_type = ?"
            params.append(event_type)
        if file_filter:
            query += " AND file_name LIKE ?"
            params.append(f"%{file_filter}%")
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        logs = [dict(row) for row in rows]
    return jsonify(logs)

@app.route('/api/chart-data')
@login_required
def api_chart_data():
    with get_db() as conn:
        internal_count = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE alert_type != 'USB Copy'").fetchone()[0] or 0
        usb_count = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE alert_type = 'USB Copy'").fetchone()[0] or 0
        sensitive_count = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE status IN ('warning', 'critical')").fetchone()[0] or 0
        external_count = usb_count
        event_rows = conn.execute("""
            SELECT COALESCE(NULLIF(event_type, ''), 'Unknown') AS label, COUNT(*) AS count
            FROM audit_logs
            GROUP BY label
            ORDER BY count DESC
        """).fetchall()
        severity_rows = conn.execute("""
            SELECT COALESCE(NULLIF(severity, ''), status, 'info') AS label, COUNT(*) AS count
            FROM audit_logs
            GROUP BY label
        """).fetchall()
        
        import datetime as dt
        today = dt.date.today()
        dates = [(today - dt.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
        labels = [(today - dt.timedelta(days=i)).strftime('%b %d') for i in range(29, -1, -1)]
        
        total_data = []
        sensitive_data = []
        for date_str in dates:
            t_cnt = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE timestamp LIKE ?", (f"{date_str}%",)).fetchone()[0] or 0
            s_cnt = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE status IN ('warning', 'critical') AND timestamp LIKE ?", (f"{date_str}%",)).fetchone()[0] or 0
            total_data.append(t_cnt)
            sensitive_data.append(s_cnt)
            
    return jsonify({
        'categories': [internal_count, external_count, sensitive_count, usb_count],
        'event_type_counts': {
            'labels': [row['label'] for row in event_rows],
            'data': [row['count'] for row in event_rows]
        },
        'severity_counts': {
            'info': sum(row['count'] for row in severity_rows if (row['label'] or 'info').lower() == 'info'),
            'warning': sum(row['count'] for row in severity_rows if (row['label'] or '').lower() == 'warning'),
            'critical': sum(row['count'] for row in severity_rows if (row['label'] or '').lower() == 'critical')
        },
        'labels': labels,
        'total_trend': total_data,
        'sensitive_trend': sensitive_data
    })

@app.route('/api/reports/summary')
@login_required
def api_report_summary():
    def month_label(year, month):
        return datetime(year, month, 1).strftime('%b %Y')

    def previous_month(year, month, offset):
        total_months = year * 12 + month - 1 - offset
        return divmod(total_months, 12)

    summary = []
    with get_db() as conn:
        now = datetime.now()
        for offset in range(5, -1, -1):
            y, m = previous_month(now.year, now.month, offset)
            m += 1
            period = f"{y:04d}-{m:02d}"
            total_events = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE strftime('%Y-%m', timestamp) = ?", (period,)).fetchone()[0] or 0
            integrity_violations = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE strftime('%Y-%m', timestamp) = ? AND status = 'critical'", (period,)).fetchone()[0] or 0
            usb_events = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE strftime('%Y-%m', timestamp) = ? AND alert_type = 'USB Copy'", (period,)).fetchone()[0] or 0
            sensitive_access = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE strftime('%Y-%m', timestamp) = ? AND status IN ('warning','critical')", (period,)).fetchone()[0] or 0
            compliance_score = 100
            if total_events > 0:
                defect_ratio = (integrity_violations * 2 + sensitive_access) / total_events
                compliance_score = max(70, min(100, round(100 - defect_ratio * 100)))

            summary.append({
                'month': month_label(y, m),
                'totalEvents': total_events,
                'integrityViolations': integrity_violations,
                'usbEvents': usb_events,
                'sensitiveAccess': sensitive_access,
                'complianceScore': compliance_score
            })
    return jsonify(summary)

@app.route('/api/reports/history')
@login_required
def api_report_history():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM report_history ORDER BY generated_at DESC LIMIT 20").fetchall()
        reports = [dict(row) for row in rows]
    return jsonify(reports)

@app.route('/api/reports/history/download/<int:report_id>')
@login_required
def api_report_history_download(report_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM report_history WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return jsonify({"success": False, "message": "Report not found."}), 404
        file_path = row['file_path']
        file_name = row['file_name']

    if not _is_safe_report_path(file_path):
        logger.warning("Blocked unavailable or unsafe report download path: %s", file_path)
        return jsonify({"success": False, "message": "Report file unavailable."}), 404

    return send_file(
        os.path.abspath(file_path),
        as_attachment=True,
        download_name=file_name,
        mimetype='application/pdf' if file_name.lower().endswith('.pdf') else 'text/csv',
        conditional=True
    )

@app.route('/api/reports/download')
@login_required
def download_report_api():
    fmt = request.args.get('format', 'csv').lower()
    report_type = request.args.get('type', 'Comprehensive_Security_Report')
    time_period = request.args.get('timePeriod', 'Last_30_Days')
    notes = request.args.get('notes', '')

    if fmt not in ('csv', 'pdf'):
        return jsonify({"success": False, "message": "Unsupported report format."}), 400

    dataset = _fetch_report_dataset(report_type, time_period)
    logs = dataset['logs']

    if fmt == 'csv':
        import io
        import csv
        from flask import Response

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Timestamp', 'Event Type', 'File Name', 'Source Path', 'Destination Path', 'User', 'Process Name', 'Status', 'SHA-256', 'Alert Type', 'Details'])
        for log in logs:
            writer.writerow([
                log['id'], log['timestamp'], log['event_type'], log['file_name'],
                log['source_path'], log['destination_path'], log['user'],
                log['process_name'], log['status'], log['sha256_hash'],
                log['alert_type'], log['details']
            ])
        output.seek(0)
        filename = _safe_report_filename(report_type, 'csv')
        output_path = os.path.join(_reports_dir(), filename)
        try:
            with open(output_path, 'w', encoding='utf-8', newline='') as csv_file:
                csv_file.write(output.getvalue())
            _record_report_history(filename, output_path, report_type, time_period, 'csv', len(logs))
        except Exception:
            logger.exception("Failed to persist CSV report history for %s", report_type)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )

    elif fmt == 'pdf':
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception as exc:
            logger.exception("ReportLab import failed")
            return jsonify({"success": False, "message": f"PDF export requires the 'reportlab' package: {exc}"}), 500

        filename = _safe_report_filename(report_type, 'pdf')
        output_path = os.path.abspath(os.path.join(_reports_dir(), filename))
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=14 * mm,
                leftMargin=14 * mm,
                topMargin=14 * mm,
                bottomMargin=14 * mm
            )
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'SentinelTitle',
                parent=styles['Title'],
                alignment=TA_CENTER,
                textColor=colors.HexColor('#0B5ED7'),
                fontName='Helvetica-Bold',
                fontSize=18,
                leading=22,
                spaceAfter=12
            )
            section_style = ParagraphStyle(
                'SentinelSection',
                parent=styles['Heading2'],
                textColor=colors.HexColor('#111827'),
                fontName='Helvetica-Bold',
                fontSize=12,
                leading=15,
                spaceBefore=10,
                spaceAfter=6
            )
            body_style = ParagraphStyle(
                'SentinelBody',
                parent=styles['BodyText'],
                fontName='Helvetica',
                fontSize=9,
                leading=12,
                textColor=colors.HexColor('#374151')
            )

            story = [
                Paragraph('SentinelTransfer Security Audit Report', title_style),
                Paragraph(f"<b>Report Type:</b> {report_type.replace('_', ' ')}", body_style),
                Paragraph(f"<b>Generation Date:</b> {generated_at}", body_style),
                Paragraph(f"<b>Time Period:</b> {time_period.replace('_', ' ')}", body_style),
            ]
            if notes:
                story.append(Paragraph(f"<b>Analyst Notes:</b> {notes}", body_style))
            story.append(Spacer(1, 8))

            summary_rows = [
                ['Metric', 'Count'],
                ['Total Events', dataset['total_events']],
                ['Sensitive Events', dataset['sensitive_events']],
                ['USB Transfers', dataset['usb_transfers']],
                ['Integrity Violations', dataset['integrity_violations']],
            ]
            summary_table = Table(summary_rows, colWidths=[115 * mm, 45 * mm])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B5ED7')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F3F6FA')),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
                ('PADDING', (0, 0), (-1, -1), 7),
            ]))
            story.append(summary_table)

            alert_summary = {}
            for log in logs:
                reason = log.get('alert_reason') or log.get('severity_reason') or 'General event'
                alert_summary[reason] = alert_summary.get(reason, 0) + 1

            story.append(Paragraph('Audit Log Summary', section_style))
            severity_counts = dataset['severity_counts']
            severity_text = (
                f"Info: {severity_counts['info']} | "
                f"Warning: {severity_counts['warning']} | "
                f"Critical: {severity_counts['critical']}"
            )
            story.append(Paragraph(severity_text, body_style))

            if alert_summary:
                top_reasons = sorted(alert_summary.items(), key=lambda item: item[1], reverse=True)[:6]
                reason_rows = [['Alert Reason', 'Events']] + [[reason, count] for reason, count in top_reasons]
                reason_table = Table(reason_rows, colWidths=[130 * mm, 30 * mm])
                reason_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('PADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(Spacer(1, 6))
                story.append(reason_table)

            story.append(Paragraph('Recent Audit Events', section_style))
            event_rows = [['Timestamp', 'Event', 'File', 'Severity', 'Alert Reason']]
            for log in logs[:60]:
                event_rows.append([
                    log['timestamp'],
                    log['event_type'] or '',
                    log['file_name'] or '',
                    (log.get('severity') or log.get('status') or 'info').upper(),
                    log.get('alert_reason') or log.get('severity_reason') or ''
                ])
            if len(event_rows) == 1:
                event_rows.append(['No events recorded for this period', '', '', '', ''])

            event_table = Table(event_rows, repeatRows=1, colWidths=[34 * mm, 24 * mm, 43 * mm, 22 * mm, 37 * mm])
            event_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B5ED7')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(event_table)

            doc.build(story)

            if not _is_safe_report_path(output_path) or os.path.getsize(output_path) == 0:
                raise FileNotFoundError(f"Generated report file not found: {output_path}")

            _record_report_history(filename, output_path, report_type, time_period, 'pdf', len(logs))

            return send_file(output_path, as_attachment=True, download_name=filename, mimetype='application/pdf', conditional=True)
        except Exception as e:
            logger.exception("Failed to generate %s report in %s format", report_type, fmt)
            return jsonify({
                "success": False,
                "message": f"Failed to generate PDF report: {e}"
            }), 500

@app.route('/api/settings')
@login_required
def get_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM system_settings").fetchall()
        settings = {r['key']: r['value'] for r in rows}
    return jsonify(settings)

@app.route('/api/settings/save', methods=['POST'])
@login_required
def save_settings():
    data = request.json
    with get_db() as conn:
        with db_lock:
            for k, v in data.items():
                conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", (k, str(v)))
            conn.commit()
    start_file_monitoring(app)
    return jsonify({"success": True, "message": "Settings saved successfully"})

# ==================================================
# ERROR HANDLERS
# ==================================================
@app.errorhandler(404)
def page_not_found(e):
    if 'user' in session:
        return render_template('dashboard.html', active_page='dashboard'), 404
    return redirect(url_for('login'))

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# ==================================================
# RUNNER
# ==================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(
    debug=True,
    use_reloader=False,
    host='0.0.0.0',
    port=port,
    threaded=True
)
