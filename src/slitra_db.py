# -*- coding: utf-8 -*-
"""
slitra_db.py  --  the Slitra data layer ("the app never forgets").

One SQLite file holds everything: consignments and their coils, the stock ledger (credit / debit),
every calculation, every job order and the event log.  Python standard library only, no Qt.

Safety rules built into the database itself (not just into the screens):
  * Nothing is ever deleted.  Deleting rows from any table is blocked by triggers; use "archived" or an adjustment.
  * The ledger and the event log are append-only: rows can be neither changed nor deleted.
  * The identity of a coil (code, consignment, thickness, width, received weight) can never change.
  * A calculation's inputs can never change (only the formula chosen from it can be recorded).
  * Stock movements, job completion and consignment entry are all-or-nothing transactions.
  * WAL journal + synchronous=FULL: a power cut cannot corrupt the file or lose a committed entry.
  * Automatic backup: at most one per 24 hours, verified, the newest N kept, optional mirror folder (another drive).

Usage:
    db = SlitraDB(r"C:\\Slitra\\data\\slitra.db", mirror_dir=r"D:\\SlitraBackup")
    cid = db.add_consignment("HI", [dict(thickness_mm=2.0, width_mm=1260, weight_kg=10050), ...])   # HI-1, HI-2, ...
"""
import json
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime

SCHEMA_VERSION = 1


class SlitraDBError(Exception):
    pass


class StockError(SlitraDBError):
    """Not enough stock on a coil for a debit."""


class DuplicateName(SlitraDBError):
    """A consignment with this name already exists."""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _r3(x):
    return round(float(x) + 0.0, 3)


SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE consignments(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    supplier TEXT NOT NULL DEFAULT '',
    material TEXT NOT NULL DEFAULT '',
    received_on TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE coils(
    id INTEGER PRIMARY KEY,
    consignment_id INTEGER NOT NULL REFERENCES consignments(id),
    seq INTEGER NOT NULL,
    code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    thickness_mm REAL NOT NULL,
    width_mm REAL NOT NULL,
    weight_kg REAL NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(consignment_id, seq)
);

CREATE TABLE calculations(
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    combos INTEGER NOT NULL,
    lowest_scrap_mm REAL,
    seconds REAL,
    consignment_id INTEGER REFERENCES consignments(id),
    selected_formula TEXT,
    selected_json TEXT
);

CREATE TABLE jobs(
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('planned','done','cancelled')),
    calc_id INTEGER REFERENCES calculations(id),
    formula TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    done_at TEXT
);

CREATE TABLE job_coils(
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    coil_id INTEGER NOT NULL REFERENCES coils(id),
    kg REAL NOT NULL CHECK(kg > 0),
    PRIMARY KEY(job_id, coil_id)
);

CREATE TABLE ledger(
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    coil_id INTEGER NOT NULL REFERENCES coils(id),
    kind TEXT NOT NULL CHECK(kind IN ('receipt','job','adjust','return')),
    kg REAL NOT NULL CHECK(kg <> 0),
    job_id INTEGER REFERENCES jobs(id),
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ledger_coil ON ledger(coil_id);

CREATE TABLE events(
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT ''
);
CREATE INDEX events_kind ON events(kind);

-- nothing is ever deleted
CREATE TRIGGER no_delete_consignments BEFORE DELETE ON consignments BEGIN SELECT RAISE(ABORT, 'nothing is ever deleted: archive it'); END;
CREATE TRIGGER no_delete_coils        BEFORE DELETE ON coils        BEGIN SELECT RAISE(ABORT, 'nothing is ever deleted'); END;
CREATE TRIGGER no_delete_calculations BEFORE DELETE ON calculations BEGIN SELECT RAISE(ABORT, 'nothing is ever deleted'); END;
CREATE TRIGGER no_delete_jobs         BEFORE DELETE ON jobs         BEGIN SELECT RAISE(ABORT, 'nothing is ever deleted: cancel it'); END;
CREATE TRIGGER no_delete_job_coils    BEFORE DELETE ON job_coils    BEGIN SELECT RAISE(ABORT, 'nothing is ever deleted'); END;
CREATE TRIGGER no_delete_ledger       BEFORE DELETE ON ledger       BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
CREATE TRIGGER no_delete_events       BEFORE DELETE ON events       BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;

-- append-only
CREATE TRIGGER no_update_ledger BEFORE UPDATE ON ledger BEGIN SELECT RAISE(ABORT, 'the ledger is append-only'); END;
CREATE TRIGGER no_update_events BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'the event log is append-only'); END;
CREATE TRIGGER no_update_job_coils BEFORE UPDATE ON job_coils BEGIN SELECT RAISE(ABORT, 'job coils cannot change'); END;

-- identities never change
CREATE TRIGGER coil_identity BEFORE UPDATE ON coils
WHEN NEW.consignment_id IS NOT OLD.consignment_id OR NEW.seq IS NOT OLD.seq OR NEW.code IS NOT OLD.code
  OR NEW.thickness_mm IS NOT OLD.thickness_mm OR NEW.width_mm IS NOT OLD.width_mm
  OR NEW.weight_kg IS NOT OLD.weight_kg OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'a coil''s identity never changes: use an adjustment'); END;

CREATE TRIGGER consignment_identity BEFORE UPDATE ON consignments
WHEN NEW.name IS NOT OLD.name OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'a consignment name never changes'); END;

CREATE TRIGGER calc_inputs_fixed BEFORE UPDATE ON calculations
WHEN NEW.ts IS NOT OLD.ts OR NEW.inputs_json IS NOT OLD.inputs_json OR NEW.combos IS NOT OLD.combos
  OR NEW.lowest_scrap_mm IS NOT OLD.lowest_scrap_mm OR NEW.seconds IS NOT OLD.seconds
  OR NEW.consignment_id IS NOT OLD.consignment_id
BEGIN SELECT RAISE(ABORT, 'a calculation''s inputs never change'); END;

CREATE TRIGGER job_fixed BEFORE UPDATE ON jobs
WHEN NEW.code IS NOT OLD.code OR NEW.created_at IS NOT OLD.created_at OR NEW.calc_id IS NOT OLD.calc_id
  OR NEW.formula IS NOT OLD.formula OR NEW.plan_json IS NOT OLD.plan_json
  OR (OLD.status <> 'planned' AND NEW.status IS NOT OLD.status)
BEGIN SELECT RAISE(ABORT, 'a job can only go from planned to done or cancelled'); END;
"""


class SlitraDB:
    def __init__(self, path, auto_backup=True, backup_dir=None, mirror_dir=None, keep_backups=30):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.backup_dir = backup_dir or os.path.join(os.path.dirname(self.path), "backups")
        self.mirror_dir = mirror_dir
        self.keep_backups = keep_backups
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=10000")
        self._migrate()
        self._auto = auto_backup
        if auto_backup:
            self._auto_backup()

    # ------------------------------------------------------------------ plumbing
    def _migrate(self):
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            existing = self.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            if existing:
                raise SlitraDBError("this file is not an empty or Slitra database")
            self.db.executescript("BEGIN;" + SCHEMA + "COMMIT;")
            self.db.execute("INSERT INTO meta VALUES('created_at', ?)", (_now(),))
            self.db.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)
            self.log("db", "database created (schema %d)" % SCHEMA_VERSION)
        elif version > SCHEMA_VERSION:
            raise SlitraDBError("this database is newer (%d) than this program (%d)" % (version, SCHEMA_VERSION))
        # future versions: if version < 2: apply migration 2 here, never destructive

    @property
    def schema_version(self):
        return self.db.execute("PRAGMA user_version").fetchone()[0]

    @contextmanager
    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def close(self):
        if self._auto:
            try:
                self._auto_backup()
            except Exception:
                pass
        self.db.close()

    # ------------------------------------------------------------------ backups
    def integrity_check(self, path=None):
        con = self.db if path is None else sqlite3.connect(path)
        try:
            return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            if path is not None:
                con.close()

    def backup_now(self, reason="manual"):
        """Copy the whole database with SQLite's online backup, verify it, prune old ones, mirror it."""
        os.makedirs(self.backup_dir, exist_ok=True)
        name = "slitra_%s_%s.db" % (datetime.now().strftime("%Y%m%d_%H%M%S"), reason)
        dest = os.path.join(self.backup_dir, name)
        n = 1
        while os.path.exists(dest):
            n += 1
            dest = os.path.join(self.backup_dir, name.replace(".db", "_%d.db" % n))
        target = sqlite3.connect(dest)
        try:
            self.db.backup(target)
        finally:
            target.close()
        if not self.integrity_check(dest):
            os.remove(dest)
            raise SlitraDBError("the backup failed its integrity check and was discarded")
        if self.mirror_dir:
            try:
                os.makedirs(self.mirror_dir, exist_ok=True)
                shutil.copy2(dest, os.path.join(self.mirror_dir, os.path.basename(dest)))
            except OSError as e:
                self.log("backup", "could not copy the backup to the mirror folder: %s" % e, level="warning")
        files = sorted(f for f in os.listdir(self.backup_dir) if f.startswith("slitra_") and f.endswith(".db"))
        for old in files[:-self.keep_backups]:
            os.remove(os.path.join(self.backup_dir, old))
        self.log("backup", "backup written: %s" % os.path.basename(dest), {"reason": reason})
        return dest

    def last_backup_age_hours(self):
        if not os.path.isdir(self.backup_dir):
            return None
        files = [os.path.join(self.backup_dir, f) for f in os.listdir(self.backup_dir) if f.startswith("slitra_")]
        if not files:
            return None
        return (time.time() - max(os.path.getmtime(f) for f in files)) / 3600.0

    def _auto_backup(self):
        age = self.last_backup_age_hours()
        if age is None or age >= 24:
            self.backup_now("auto")

    # ------------------------------------------------------------------ consignments and coils
    @staticmethod
    def _check_coil(c):
        for k in ("thickness_mm", "width_mm", "weight_kg"):
            if k not in c or float(c[k]) <= 0:
                raise SlitraDBError("every coil needs a thickness, a width and a weight above 0 (%s)" % k)

    def add_consignment(self, name, coils, supplier="", material="", received_on="", notes=""):
        """New consignment with its coils NAME-1, NAME-2, ...; every coil is credited to stock. One transaction."""
        name = (name or "").strip()
        if not name:
            raise SlitraDBError("the consignment needs a name")
        if not coils:
            raise SlitraDBError("a consignment needs at least one coil")
        for c in coils:
            self._check_coil(c)
        with self._tx():
            try:
                cur = self.db.execute(
                    "INSERT INTO consignments(name,supplier,material,received_on,notes,created_at) VALUES(?,?,?,?,?,?)",
                    (name, supplier, material, received_on, notes, _now()))
            except sqlite3.IntegrityError:
                raise DuplicateName("a consignment named '%s' already exists" % name)
            cid = cur.lastrowid
            self._insert_coils(cid, name, 0, coils)
        self.log("inventory", "consignment %s received with %d coils" % (name, len(coils)), {"consignment": name})
        return cid

    def add_coils(self, consignment_id, coils):
        """More coils for an existing consignment (credit). Numbering continues. Returns the new codes."""
        for c in coils:
            self._check_coil(c)
        row = self.db.execute("SELECT name FROM consignments WHERE id=?", (consignment_id,)).fetchone()
        if row is None:
            raise SlitraDBError("unknown consignment")
        with self._tx():
            last = self.db.execute("SELECT COALESCE(MAX(seq),0) FROM coils WHERE consignment_id=?", (consignment_id,)).fetchone()[0]
            codes = self._insert_coils(consignment_id, row["name"], last, coils)
        self.log("inventory", "%d coils added to %s" % (len(codes), row["name"]), {"codes": codes})
        return codes

    def _insert_coils(self, cid, name, last_seq, coils):
        codes, ts = [], _now()
        for i, c in enumerate(coils, start=1):
            seq = last_seq + i
            code = "%s-%d" % (name, seq)
            cur = self.db.execute(
                "INSERT INTO coils(consignment_id,seq,code,thickness_mm,width_mm,weight_kg,notes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (cid, seq, code, float(c["thickness_mm"]), float(c["width_mm"]), _r3(c["weight_kg"]), c.get("notes", ""), ts))
            self.db.execute("INSERT INTO ledger(ts,coil_id,kind,kg,note) VALUES(?,?,?,?,?)",
                            (ts, cur.lastrowid, "receipt", _r3(c["weight_kg"]), "received with %s" % name))
            codes.append(code)
        return codes

    def consignments(self, include_archived=False):
        q = """
        SELECT g.id, g.name, g.supplier, g.material, g.received_on, g.notes, g.archived,
               COUNT(c.id) AS coils,
               COALESCE(SUM(c.weight_kg),0) AS received_kg,
               COALESCE(SUM(s.kg),0) AS remaining_kg,
               COALESCE(SUM(CASE WHEN s.kg > 0.0005 THEN 1 ELSE 0 END),0) AS remaining_coils
        FROM consignments g
        LEFT JOIN coils c ON c.consignment_id = g.id
        LEFT JOIN (SELECT coil_id, SUM(kg) AS kg FROM ledger GROUP BY coil_id) s ON s.coil_id = c.id
        %s GROUP BY g.id ORDER BY g.id DESC""" % ("" if include_archived else "WHERE g.archived = 0")
        out = []
        for r in self.db.execute(q):
            d = dict(r)
            d["received_kg"] = _r3(d["received_kg"])
            d["remaining_kg"] = _r3(d["remaining_kg"])
            d["avg_received_kg"] = _r3(d["received_kg"] / d["coils"]) if d["coils"] else 0.0       # the average, kept separate
            d["avg_remaining_kg"] = _r3(d["remaining_kg"] / d["remaining_coils"]) if d["remaining_coils"] else 0.0
            out.append(d)
        return out

    def coils(self, consignment_id, only_available=False):
        q = """SELECT c.id, c.code, c.seq, c.thickness_mm, c.width_mm, c.weight_kg, c.notes,
                      COALESCE((SELECT SUM(kg) FROM ledger WHERE coil_id=c.id),0) AS remaining_kg
               FROM coils c WHERE c.consignment_id=? ORDER BY c.seq"""
        rows = [dict(r) for r in self.db.execute(q, (consignment_id,))]
        for r in rows:
            r["remaining_kg"] = _r3(r["remaining_kg"])
        return [r for r in rows if r["remaining_kg"] > 0.0005] if only_available else rows

    def coil_by_code(self, code):
        r = self.db.execute("SELECT id FROM coils WHERE code=?", (code,)).fetchone()
        return None if r is None else r["id"]

    def remaining(self, coil_id):
        return _r3(self.db.execute("SELECT COALESCE(SUM(kg),0) FROM ledger WHERE coil_id=?", (coil_id,)).fetchone()[0])

    def stock_status(self):
        """Return all coils with remaining stock, grouped by consignment.
        Each entry: code, consignment, thickness_mm, width_mm, weight_kg, remaining_kg, status.
        status is 'full', 'low', or 'empty' based on remaining weight ratio."""
        rows = self.db.execute(
            "SELECT c.id, c.code, g.name as consignment, c.thickness_mm, c.width_mm, c.weight_kg"
            " FROM coils c JOIN consignments g ON g.id=c.consignment_id"
            " ORDER BY g.name, c.seq"
        ).fetchall()
        out = []
        for r in rows:
            remaining = _r3(r["weight_kg"] + self.remaining(r["id"]))
            ratio = remaining / r["weight_kg"] if r["weight_kg"] > 0 else 0
            if remaining <= 0.001:
                status = "empty"
            elif ratio <= 0.10:
                status = "low"
            else:
                status = "full"
            out.append({
                "id": r["id"],
                "code": r["code"],
                "consignment": r["consignment"],
                "thickness_mm": r["thickness_mm"],
                "width_mm": r["width_mm"],
                "weight_kg": r["weight_kg"],
                "remaining_kg": remaining,
                "status": status,
            })
        return out

    def archive_consignment(self, consignment_id, archived=True):
        self.db.execute("UPDATE consignments SET archived=? WHERE id=?", (1 if archived else 0, consignment_id))
        self.log("inventory", "consignment %d %s" % (consignment_id, "archived" if archived else "restored"))

    def next_consignment_code(self, material):
        """Return next available consignment name for material.
        Format: {MATERIAL}-{YY}{MM}{DD}-{SEQ}
        Example: HR-261116-001, CR-261116-002
        This gives: material type, date, and sequence — sortable, unique, informative.
        """
        base = (material or "").strip().upper()
        if not base:
            return "UNKNOWN"
        today = datetime.now().strftime("%y%m%d")  # YYMMDD
        prefix = f"{base}-{today}"
        # Query existing consignments starting with this prefix
        rows = self.db.execute(
            "SELECT name FROM consignments WHERE name LIKE ? ORDER BY id DESC LIMIT 1",
            (prefix + "-%",)
        ).fetchall()
        if not rows:
            return f"{prefix}-001"
        # Parse sequence from last name
        last_name = rows[0]["name"]
        try:
            last_seq = int(last_name.split("-")[-1])
        except (ValueError, IndexError):
            last_seq = 0
        return f"{prefix}-{last_seq + 1:03d}"

    def recent_consignments(self, limit=10):
        """Return list of recent consignment names (most recent first)."""
        rows = self.db.execute(
            "SELECT name FROM consignments ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [r["name"] for r in rows]

    # ------------------------------------------------------------------ stock movements
    def credit(self, coil_id, kg, note="", kind="adjust", job_id=None):
        kg = _r3(kg)
        if kg <= 0:
            raise SlitraDBError("a credit must be above 0 kg")
        with self._tx():
            self._require_coil(coil_id)
            self.db.execute("INSERT INTO ledger(ts,coil_id,kind,kg,job_id,note) VALUES(?,?,?,?,?,?)",
                            (_now(), coil_id, kind, kg, job_id, note))
        self.log("inventory", "credit %.3f kg to coil %d" % (kg, coil_id), {"note": note})

    def debit(self, coil_id, kg, note="", kind="adjust", job_id=None):
        kg = _r3(kg)
        if kg <= 0:
            raise SlitraDBError("a debit must be above 0 kg")
        with self._tx():
            self._require_coil(coil_id)
            self._debit_inside(coil_id, kg, note, kind, job_id)
        self.log("inventory", "debit %.3f kg from coil %d" % (kg, coil_id), {"note": note})

    def _require_coil(self, coil_id):
        if self.db.execute("SELECT 1 FROM coils WHERE id=?", (coil_id,)).fetchone() is None:
            raise SlitraDBError("unknown coil")

    def _debit_inside(self, coil_id, kg, note, kind, job_id):
        left = self.remaining(coil_id)
        if kg > left + 0.0005:
            code = self.db.execute("SELECT code FROM coils WHERE id=?", (coil_id,)).fetchone()["code"]
            raise StockError("%s has only %.3f kg left, %.3f kg were asked" % (code, left, kg))
        self.db.execute("INSERT INTO ledger(ts,coil_id,kind,kg,job_id,note) VALUES(?,?,?,?,?,?)",
                        (_now(), coil_id, kind, -kg, job_id, note))

    def ledger(self, coil_id=None, consignment_id=None, limit=None):
        q = ("SELECT l.id, l.ts, c.code, l.kind, l.kg, l.job_id, l.note FROM ledger l JOIN coils c ON c.id=l.coil_id "
             "WHERE 1=1")
        args = []
        if coil_id is not None:
            q += " AND l.coil_id=?"
            args.append(coil_id)
        if consignment_id is not None:
            q += " AND c.consignment_id=?"
            args.append(consignment_id)
        q += " ORDER BY l.id DESC" + (" LIMIT %d" % int(limit) if limit else "")
        return [dict(r) for r in self.db.execute(q, args)]

    # ------------------------------------------------------------------ calculations (every one is kept)
    def save_calculation(self, inputs, combos, lowest_scrap_mm=None, seconds=None, consignment_id=None):
        cur = self.db.execute(
            "INSERT INTO calculations(ts,inputs_json,combos,lowest_scrap_mm,seconds,consignment_id) VALUES(?,?,?,?,?,?)",
            (_now(), json.dumps(inputs, sort_keys=True, ensure_ascii=False), int(combos), lowest_scrap_mm, seconds, consignment_id))
        self.log("calculation", "calculation %d: %s combinations" % (cur.lastrowid, "{:,}".format(int(combos))), {"calc": cur.lastrowid})
        return cur.lastrowid

    def set_selected_formula(self, calc_id, formula, plan):
        self.db.execute("UPDATE calculations SET selected_formula=?, selected_json=? WHERE id=?",
                        (formula, json.dumps(plan, sort_keys=True, ensure_ascii=False), calc_id))

    def calculations(self, limit=50, search=""):
        q = "SELECT * FROM calculations"
        args = []
        if search:
            q += " WHERE inputs_json LIKE ? OR selected_formula LIKE ?"
            args += ["%" + search + "%"] * 2
        q += " ORDER BY id DESC LIMIT %d" % int(limit)
        out = []
        for r in self.db.execute(q, args):
            d = dict(r)
            d["inputs"] = json.loads(d.pop("inputs_json"))
            d["selected"] = json.loads(d["selected_json"]) if d.get("selected_json") else None
            out.append(d)
        return out

    # ------------------------------------------------------------------ job orders
    def create_job(self, calc_id, formula, plan, coil_kgs, notes=""):
        """A planned job order: the chosen formula and the coils (id -> kg) it will use. Stock is NOT touched yet."""
        if not coil_kgs:
            raise SlitraDBError("a job needs at least one coil")
        with self._tx():
            year = datetime.now().year
            last = self.db.execute("SELECT code FROM jobs WHERE code LIKE ? ORDER BY id DESC LIMIT 1", ("J-%d-%%" % year,)).fetchone()
            n = int(last["code"].rsplit("-", 1)[1]) + 1 if last else 1
            code = "J-%d-%04d" % (year, n)
            cur = self.db.execute(
                "INSERT INTO jobs(code,created_at,status,calc_id,formula,plan_json,notes) VALUES(?,?,?,?,?,?,?)",
                (code, _now(), "planned", calc_id, formula, json.dumps(plan, sort_keys=True, ensure_ascii=False), notes))
            jid = cur.lastrowid
            for coil_id, kg in coil_kgs.items():
                self._require_coil(coil_id)
                self.db.execute("INSERT INTO job_coils(job_id,coil_id,kg) VALUES(?,?,?)", (jid, coil_id, _r3(kg)))
        self.log("job", "job %s planned with formula %s" % (code, formula), {"job": code})
        return jid, code

    def complete_job(self, job_id):
        """The job is done: every coil is debited by the weight it used, all or nothing."""
        with self._tx():
            job = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise SlitraDBError("unknown job")
            if job["status"] != "planned":
                raise SlitraDBError("job %s is already %s" % (job["code"], job["status"]))
            for r in self.db.execute("SELECT coil_id, kg FROM job_coils WHERE job_id=?", (job_id,)).fetchall():
                self._debit_inside(r["coil_id"], r["kg"], "job %s" % job["code"], "job", job_id)
            self.db.execute("UPDATE jobs SET status='done', done_at=? WHERE id=?", (_now(), job_id))
        self.log("job", "job %s completed: stock debited" % job["code"], {"job": job["code"]})

    def cancel_job(self, job_id):
        with self._tx():
            job = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise SlitraDBError("unknown job")
            if job["status"] != "planned":
                raise SlitraDBError("only a planned job can be cancelled (job %s is %s); use an adjustment" % (job["code"], job["status"]))
            self.db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (job_id,))
        self.log("job", "job %s cancelled" % job["code"], {"job": job["code"]})

    def jobs(self, status=None, limit=None):
        q = "SELECT * FROM jobs" + (" WHERE status=?" if status else "") + " ORDER BY id DESC" + (" LIMIT %d" % int(limit) if limit else "")
        out = []
        for r in self.db.execute(q, (status,) if status else ()):
            d = dict(r)
            d["plan"] = json.loads(d.pop("plan_json"))
            d["coils"] = [dict(x) for x in self.db.execute(
                "SELECT c.code, j.kg FROM job_coils j JOIN coils c ON c.id=j.coil_id WHERE j.job_id=? ORDER BY c.seq", (d["id"],))]
            out.append(d)
        return out

    # ------------------------------------------------------------------ the log
    def log(self, kind, message, data=None, level="info"):
        self.db.execute("INSERT INTO events(ts,level,kind,message,data_json) VALUES(?,?,?,?,?)",
                        (_now(), level, kind, message, json.dumps(data, ensure_ascii=False) if data is not None else ""))

    def events(self, limit=200, kind=None):
        q = "SELECT * FROM events" + (" WHERE kind=?" if kind else "") + " ORDER BY id DESC LIMIT %d" % int(limit)
        return [dict(r) for r in self.db.execute(q, (kind,) if kind else ())]

    # ------------------------------------------------------------------ nothing is locked in
    def export_json(self, path):
        """Everything as one readable JSON file (so the data can always leave the program)."""
        dump = {"schema_version": self.schema_version, "exported_at": _now()}
        for t in ("consignments", "coils", "ledger", "calculations", "jobs", "job_coils", "events"):
            dump[t] = [dict(r) for r in self.db.execute("SELECT * FROM %s ORDER BY 1" % t)]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=1)
        return path
