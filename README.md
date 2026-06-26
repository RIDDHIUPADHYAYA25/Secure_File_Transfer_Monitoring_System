# 🛡️ SentinelTransfer — Secure File Transfer & Monitoring System

> **Version 3.2.1** · Python / Flask · AES-256 Encrypted Database · Real-Time File Monitoring

SentinelTransfer is a full-stack cybersecurity web application that provides real-time file-system monitoring, USB transfer detection, file integrity verification, DLP (Data Loss Prevention) policy enforcement, and encrypted-at-rest data storage — all behind a custom authentication system with email OTP verification.

---

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Database Schema](#-database-schema)
- [Setup & Installation](#-setup--installation)
- [Environment Variables](#-environment-variables)
- [Running the Application](#-running-the-application)
- [Authentication Flow](#-authentication-flow)
- [Database Encryption](#-database-encryption)
- [API Reference](#-api-reference)
- [Reports](#-reports)
- [Security Design](#-security-design)

---

## ✨ Features

| Module | Description |
|--------|-------------|
| 🔐 **Custom Auth** | Registration, login, email OTP verification, password reset via 4-digit OTP |
| 📁 **Live File Monitor** | Real-time watchdog-based monitoring of configured directories (recursive/non-recursive) |
| 🔍 **Sensitive File Tracking** | Mark files or directories as sensitive; auto-detects keyword-based sensitive filenames |
| 🧮 **Integrity Checking** | SHA-256 hash registry with automatic and manual scan; detects tampering instantly |
| 🔌 **USB Monitoring** | Dynamic detection and watching of removable drives; alerts on any file copied to USB |
| 📊 **Audit Logs** | Full event trail — Created, Modified, Deleted, Moved — with severity, process name, and SHA-256 |
| 📧 **Email Alerts** | Sends HTML alert emails to admin on warning/critical events via Flask-Mail / SMTP |
| 📑 **Reports** | Export audit logs as **CSV** or styled **PDF** (via ReportLab) with time-period filtering |
| 🗄️ **Encrypted Database** | AES-256 database at rest; auto-decrypts on startup, auto-encrypts on clean shutdown |
| ⚙️ **Settings** | Persistent key-value settings store; re-applies monitoring configuration on save |

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.10+, Flask 3.0 |
| **Database** | SQLite 3 (WAL mode) with AES-256 encryption at rest |
| **Auth** | Custom (Werkzeug `PBKDF2-SHA256` password hashing + email OTP) |
| **File Monitoring** | `watchdog` + `psutil` |
| **USB Detection** | `psutil` disk partitions + optional `pywin32` (`win32file`, `win32api`) |
| **Encryption** | `cryptography` — Fernet (AES-256) + PBKDF2-HMAC-SHA256 |
| **Email** | `Flask-Mail` (Gmail / Outlook / Yahoo SMTP) |
| **Reports** | `reportlab` (PDF), Python `csv` (CSV) |
| **Frontend** | HTML5 / Jinja2 templates, Vanilla CSS, JavaScript |
| **Config** | `python-dotenv` (`.env` file) |

---

## 🗂️ Project Structure

```
SentinelTransfer/
├── app.py                  # Main Flask application (~2 000 lines)
├── db_crypto.py            # AES-256 DB encrypt / decrypt module
├── admin_decrypt.py        # CLI tool for manual DB encryption management
├── requirements.txt        # Python dependencies
├── sensitive_files.txt     # Plain-text list of sensitive filename keywords
├── .env                    # ⚠️  Secret config (never committed)
├── .env.example            # Template for .env
├── .gitignore
│
├── instance/               # Flask instance folder
│   ├── sentinel.db         # Live SQLite database (decrypted, runtime only)
│   ├── sentinel.db.enc     # AES-256 encrypted database (committed to Git)
│   ├── monitored_folder/   # Default monitored directory
│   └── reports/            # Generated report files (CSV / PDF)
│
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Authenticated layout (sidebar + navbar)
│   ├── base_auth.html      # Auth pages layout
│   ├── dashboard.html      # Overview stats & charts
│   ├── live_monitor.html   # Real-time event feed
│   ├── sensitive_files.html
│   ├── integrity_check.html
│   ├── usb_monitoring.html
│   ├── audit_logs.html
│   ├── reports.html
│   ├── settings.html
│   ├── login.html
│   ├── signup.html
│   ├── verify_email.html
│   ├── forgot_password.html
│   ├── reset_password.html
│   └── db_encrypted.html
│
└── static/
    ├── css/                # Stylesheets
    └── js/                 # JavaScript files
```

---

## 🗄️ Database Schema

| Table | Purpose |
|-------|---------|
| `users` | Accounts — name, email, username, hashed password, OTP fields, verification status |
| `monitored_directories` | Paths watched by the file-system observer |
| `sensitive_files` | Files/locations flagged as sensitive with classification and protection level |
| `audit_logs` | All file-system events — type, path, user, process, severity, SHA-256, alert type |
| `integrity_files` | SHA-256 hash registry for integrity verification |
| `system_settings` | Key-value store for application settings |
| `report_history` | Metadata of generated reports (file name, path, type, format, record count) |

---

## ⚙️ Setup & Installation

### Prerequisites

- Python 3.10 or newer
- pip
- (Windows) Optional: `pywin32` for enhanced USB drive-type detection

### 1. Clone the repository

```bash
git clone <repo-url>
cd Secure_file_transfer_system/SentinelTransfer
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Optional (Windows only)** — for accurate USB drive type detection:
> ```bash
> pip install pywin32
> ```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values (see Environment Variables section)
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask secret key — use a long random string in production |
| `ADMIN_EMAIL` | Administrator email — **only this address** can encrypt/decrypt the database |
| `MAIL_SERVER` | SMTP server (default: `smtp.gmail.com`) |
| `MAIL_PORT` | SMTP port (default: `587`) |
| `MAIL_USE_TLS` | Enable TLS (default: `True`) |
| `MAIL_USE_SSL` | Enable SSL (default: `False`) |
| `MAIL_USERNAME` | Your SMTP email address (Gmail: use an App Password) |
| `MAIL_PASSWORD` | SMTP app password |
| `MAIL_DEFAULT_SENDER` | Display name + address for outgoing emails |

> 💡 If `MAIL_USERNAME` is left **blank**, the app operates in **demo mode** and prints OTPs to the terminal console instead of sending real emails.

### Gmail App Password Setup
1. Enable 2-Factor Auth on your Google account
2. Go to `myaccount.google.com → Security → App Passwords`
3. Generate an App Password and use it as `MAIL_PASSWORD`

---

## 🚀 Running the Application

```bash
# Ensure your virtual environment is active
python app.py
```

The application starts at **http://localhost:5000**.

On startup the app will:
1. Auto-detect `sentinel.db.enc` and decrypt it using `ADMIN_EMAIL` if set
2. Initialise the database schema (and run any pending column migrations)
3. Start the Watchdog file-system observer on all configured monitored directories
4. Start a background USB poller thread (polls every 3 seconds for new/removed drives)

On clean shutdown, the database is automatically **re-encrypted** via an `atexit` hook.

---

## 🔐 Authentication Flow

```
Register → Email OTP (6-digit, 10 min expiry) → Verified Account
                                                        ↓
                                                  Login → Dashboard

Forgot Password → Email OTP (4-digit, 5 min expiry) → Reset Password → Login
```

- Passwords are hashed with **Werkzeug PBKDF2-SHA256** before storage — never stored in plain text.
- Sessions persist for **30 days** when "Remember Me" is checked.
- All feature routes are protected by the `@login_required` decorator.
- Email enumeration is **prevented** on the forgot-password flow (always shows "sent").
- Verification codes can be resent; each resend generates a fresh code with a new 10-minute expiry.

---

## 🔒 Database Encryption

The SQLite database is encrypted **at rest** using AES-256 (Fernet) with a key derived from `ADMIN_EMAIL + SECRET_KEY` via **PBKDF2-HMAC-SHA256 (300,000 iterations, 32-byte random salt)**.

### Encryption Details

| Property | Value |
|----------|-------|
| Algorithm | AES-256 (Fernet) |
| Key derivation | PBKDF2-HMAC-SHA256 |
| Iterations | 300,000 |
| Salt | 32-byte random (unique per encryption) |
| Key material | `ADMIN_EMAIL + SECRET_KEY` (never stored in repository) |

### What Is Protected

| Data | Protection |
|------|------------|
| Passwords | Werkzeug PBKDF2-SHA256 one-way hash |
| Usernames, emails, names | AES-256 database encryption |
| Mobile numbers, countries | AES-256 database encryption |
| Verification & reset OTPs | AES-256 database encryption |

### Manual Database Management (Admin Only)

```bash
# Decrypt for local development
python admin_decrypt.py --action decrypt --email your-admin@email.com

# Re-encrypt before committing to Git
python admin_decrypt.py --action encrypt --email your-admin@email.com
```

> ⚠️ Access is denied to anyone whose email does not match `ADMIN_EMAIL` in `.env`.

---

## 📡 API Reference

All API endpoints require an authenticated session (`@login_required`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stats` | Dashboard statistics (events, violations, USB events, DB size, watcher status) |
| `GET` | `/api/audit-logs` | Paginated audit log — filters: `severity`, `event_type`, `file_name`, `limit` |
| `GET` | `/api/chart-data` | 30-day event trend + severity and event-type breakdowns for charts |
| `GET` | `/api/sensitive-files` | List all registered sensitive files |
| `POST` | `/api/sensitive-files/add` | Register a sensitive file (`name`, `location`, `status`, `classification`) |
| `DELETE` | `/api/sensitive-files/remove/<id>` | Remove a sensitive file registration |
| `GET` | `/api/directories` | List monitored directories with live file counts |
| `POST` | `/api/directories/add` | Add a monitored directory (`name`, `path`, `recursive`) |
| `DELETE` | `/api/directories/remove/<id>` | Remove a monitored directory |
| `GET` | `/api/integrity-files` | List integrity-registered files with hash status |
| `POST` | `/api/verify-integrity` | Trigger a full SHA-256 integrity scan across all monitored directories |
| `GET` | `/api/usb-devices` | Detect currently connected USB/removable drives |
| `GET` | `/api/reports/summary` | 6-month monthly summary for Reports page |
| `GET` | `/api/reports/history` | List of previously generated reports (last 20) |
| `GET` | `/api/reports/history/download/<id>` | Download a previously generated report file |
| `GET` | `/api/reports/download` | Generate & download report (`format`, `type`, `timePeriod`, `notes`) |
| `GET` | `/api/settings` | Retrieve all system settings |
| `POST` | `/api/settings/save` | Save system settings (key-value pairs) |

---

## 📑 Reports

Reports can be exported via the **Reports** page or the `/api/reports/download` endpoint.

| Option | Details |
|--------|---------|
| **Formats** | CSV, PDF |
| **Time Periods** | Today, Yesterday, Last 7 Days, Last 30 Days, Last 90 Days, Last 12 Months |
| **PDF Content** | Summary metrics table, alert-reason breakdown, recent events table (up to 60 rows) |
| **CSV Content** | Full audit log with all fields: ID, Timestamp, Event Type, File, Paths, User, Process, Status, SHA-256, Alert Type, Details |
| **History** | Last 20 generated reports tracked in `report_history` with re-download links |

---

## 🛡️ Security Design

| Measure | Implementation |
|---------|---------------|
| No plain-text passwords | Werkzeug PBKDF2-SHA256 hashing before DB write |
| No plain-text OTPs at rest | OTPs are short-lived (5–10 min) and cleared after use |
| Database encrypted at rest | AES-256 Fernet — `.enc` file is unreadable without admin credentials |
| Thread-safe DB writes | `threading.Lock` (`db_lock`) on every write operation |
| Concurrent read safety | SQLite WAL (Write-Ahead Logging) mode |
| Duplicate event prevention | 1-second debounce on filesystem events |
| Path traversal prevention | Report download paths validated against reports directory root |
| Email enumeration prevention | Forgot-password always returns success regardless of account existence |
| Admin-gated CLI | `admin_decrypt.py` validates `ADMIN_EMAIL` before encrypt/decrypt |
| Auto-encrypt on exit | `atexit` hook re-encrypts the database on clean shutdown |

---

> 🚫 Unauthorised access to or decryption of the database is strictly prohibited.
> This is a cybersecurity project — data protection is not optional.

And important points are as follows:
1. The OTP's coming during authentication will be visible on the terminal of the project folder after execution so for verification and proper authentication you need to see the terminal.

   
2.Database is encrypted so the access to see the database is denied  for user safety.





<img width="1920" height="962" alt="Screenshot (353)" src="https://github.com/user-attachments/assets/f04381ad-98fe-4683-a23a-3da255c7f824" />



