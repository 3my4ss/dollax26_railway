import os, sqlite3, secrets, hashlib, hmac, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

DATA_DIR = Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", os.getenv("DATA_DIR", "./data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "dollax.db"

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def now():
    return datetime.now(timezone.utc).isoformat()

def hash_password(p):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(p.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + digest.hex()

def verify_password(p, stored):
    try:
        salt, digest = stored.split("$", 1)
        got = hashlib.scrypt(p.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(got, digest)
    except Exception:
        return False

def _add_column(c, table, column, definition):
    cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS admins(
          username TEXT PRIMARY KEY,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'admin',
          created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inbounds(
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          protocol TEXT NOT NULL DEFAULT 'vless',
          network TEXT NOT NULL DEFAULT 'ws',
          security TEXT NOT NULL DEFAULT 'tls',
          address TEXT NOT NULL DEFAULT '',
          port INTEGER NOT NULL DEFAULT 443,
          path TEXT NOT NULL UNIQUE,
          host_header TEXT NOT NULL DEFAULT '',
          sni TEXT NOT NULL DEFAULT '',
          alpn TEXT NOT NULL DEFAULT 'http/1.1',
          fingerprint TEXT NOT NULL DEFAULT 'chrome',
          limit_bytes INTEGER NOT NULL DEFAULT 0,
          expires_at TEXT NOT NULL DEFAULT '',
          ip_limit INTEGER NOT NULL DEFAULT 0,
          connection_limit INTEGER NOT NULL DEFAULT 0,
          client_limit INTEGER NOT NULL DEFAULT 0,
          note TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clients(
          id TEXT PRIMARY KEY,
          inbound_id TEXT NOT NULL,
          name TEXT NOT NULL,
          uuid TEXT NOT NULL UNIQUE,
          limit_bytes INTEGER NOT NULL DEFAULT 0,
          expires_at TEXT NOT NULL DEFAULT '',
          ip_limit INTEGER NOT NULL DEFAULT 0,
          connection_limit INTEGER NOT NULL DEFAULT 0,
          speed_limit_mbps REAL NOT NULL DEFAULT 0,
          clean_ips TEXT NOT NULL DEFAULT '[]',
          note TEXT NOT NULL DEFAULT '',
          enabled INTEGER NOT NULL DEFAULT 1,
          created TEXT NOT NULL,
          FOREIGN KEY(inbound_id) REFERENCES inbounds(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS settings(
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """)
        # Migration from the earlier Dollax schema.
        migrations = [
            ("inbounds", "network", "TEXT NOT NULL DEFAULT 'ws'"),
            ("inbounds", "security", "TEXT NOT NULL DEFAULT 'tls'"),
            ("inbounds", "address", "TEXT NOT NULL DEFAULT ''"),
            ("inbounds", "port", "INTEGER NOT NULL DEFAULT 443"),
            ("inbounds", "host_header", "TEXT NOT NULL DEFAULT ''"),
            ("inbounds", "sni", "TEXT NOT NULL DEFAULT ''"),
            ("inbounds", "alpn", "TEXT NOT NULL DEFAULT 'http/1.1'"),
            ("inbounds", "fingerprint", "TEXT NOT NULL DEFAULT 'chrome'"),
            ("inbounds", "limit_bytes", "INTEGER NOT NULL DEFAULT 0"),
            ("inbounds", "expires_at", "TEXT NOT NULL DEFAULT ''"),
            ("inbounds", "ip_limit", "INTEGER NOT NULL DEFAULT 0"),
            ("inbounds", "connection_limit", "INTEGER NOT NULL DEFAULT 0"),
            ("inbounds", "client_limit", "INTEGER NOT NULL DEFAULT 0"),
            ("inbounds", "note", "TEXT NOT NULL DEFAULT ''"),
            ("clients", "limit_bytes", "INTEGER NOT NULL DEFAULT 0"),
            ("clients", "expires_at", "TEXT NOT NULL DEFAULT ''"),
            ("clients", "ip_limit", "INTEGER NOT NULL DEFAULT 0"),
            ("clients", "connection_limit", "INTEGER NOT NULL DEFAULT 0"),
            ("clients", "speed_limit_mbps", "REAL NOT NULL DEFAULT 0"),
            ("clients", "clean_ips", "TEXT NOT NULL DEFAULT '[]'"),
            ("clients", "note", "TEXT NOT NULL DEFAULT ''"),
        ]
        for table, col, definition in migrations:
            _add_column(c, table, col, definition)

        admin = os.getenv("ADMIN_USERNAME", "dollax26").strip() or "dollax26"
        pw = os.getenv("ADMIN_PASSWORD", "admin")
        row = c.execute("SELECT username FROM admins WHERE username=?", (admin,)).fetchone()
        if not row:
            c.execute("INSERT INTO admins(username,password_hash,role,created) VALUES(?,?,?,?)",
                      (admin, hash_password(pw), "owner", now()))
        for k, v in {
            "panel_name": "Dollax Panel",
            "public_base_url": os.getenv("PUBLIC_BASE_URL", ""),
        }.items():
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        c.commit()

def setting(key, default=""):
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

def set_setting(key, value):
    with conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, str(value)))
        c.commit()

def clean_ips(value):
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").replace(",", "\n").splitlines()
    out=[]
    for item in items:
        item=str(item).strip()
        if item and item not in out:
            out.append(item[:253])
    return out[:100]

def json_list(value):
    try:
        return clean_ips(json.loads(value or "[]"))
    except Exception:
        return clean_ips(value)
