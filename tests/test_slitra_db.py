# -*- coding: utf-8 -*-
"""Tests for slitra_db.py.   Run:  python test_slitra_db.py"""
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from slitra_db import DuplicateName, SlitraDB, SlitraDBError, StockError


def coils(*weights, t=2.0, w=1260):
    return [dict(thickness_mm=t, width_mm=w, weight_kg=x) for x in weights]


class DBTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "data", "slitra.db")
        self.mirror = os.path.join(self.dir, "mirror")
        self.db = SlitraDB(self.path, mirror_dir=self.mirror)

    def tearDown(self):
        try:
            self.db.db.close()
        except Exception:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    # ---- consignments and coils
    def test_consignment_names_its_coils(self):
        cid = self.db.add_consignment("HI", coils(10050, 9980, 10120), supplier="Hadeed", material="CR")
        cs = self.db.coils(cid)
        self.assertEqual([c["code"] for c in cs], ["HI-1", "HI-2", "HI-3"])
        self.assertEqual([c["weight_kg"] for c in cs], [10050.0, 9980.0, 10120.0])
        self.assertTrue(all(c["thickness_mm"] == 2.0 and c["width_mm"] == 1260 for c in cs))

    def test_average_is_kept_separate(self):
        self.db.add_consignment("HI", coils(10000, 10100, 9900))
        g = self.db.consignments()[0]
        self.assertEqual(g["coils"], 3)
        self.assertEqual(g["received_kg"], 30000.0)
        self.assertEqual(g["avg_received_kg"], 10000.0)
        self.assertEqual(g["remaining_kg"], 30000.0)

    def test_more_coils_continue_the_numbering(self):
        cid = self.db.add_consignment("HI", coils(10000, 10000))
        codes = self.db.add_coils(cid, coils(9000, 9500))
        self.assertEqual(codes, ["HI-3", "HI-4"])
        self.assertEqual(self.db.consignments()[0]["coils"], 4)

    def test_duplicate_name_is_refused_even_in_other_case(self):
        self.db.add_consignment("HI", coils(10000))
        with self.assertRaises(DuplicateName):
            self.db.add_consignment("hi", coils(10000))

    def test_bad_input_is_refused_and_nothing_is_saved(self):
        with self.assertRaises(SlitraDBError):
            self.db.add_consignment("X", [dict(thickness_mm=2, width_mm=1260, weight_kg=0)])
        with self.assertRaises(SlitraDBError):
            self.db.add_consignment("", coils(1000))
        self.assertEqual(self.db.consignments(include_archived=True), [])

    def test_big_consignment(self):
        t0 = time.time()
        self.db.add_consignment("BIG", coils(*[10000 + i for i in range(200)]))
        self.assertLess(time.time() - t0, 3)
        self.assertEqual(self.db.consignments()[0]["coils"], 200)
        self.assertEqual(len(self.db.coils(self.db.consignments()[0]["id"])), 200)

    # ---- stock
    def test_credit_and_debit_and_remaining(self):
        cid = self.db.add_consignment("HI", coils(10000))
        coil = self.db.coils(cid)[0]["id"]
        self.db.debit(coil, 2500.5, "test cut")
        self.assertEqual(self.db.remaining(coil), 7499.5)
        self.db.credit(coil, 500, "returned offcut", kind="return")
        self.assertEqual(self.db.remaining(coil), 7999.5)
        g = self.db.consignments()[0]
        self.assertEqual(g["remaining_kg"], 7999.5)
        kinds = [r["kind"] for r in self.db.ledger(coil_id=coil)]
        self.assertEqual(kinds, ["return", "adjust", "receipt"])

    def test_cannot_take_more_than_there_is(self):
        cid = self.db.add_consignment("HI", coils(1000))
        coil = self.db.coils(cid)[0]["id"]
        with self.assertRaises(StockError):
            self.db.debit(coil, 1000.5)
        self.assertEqual(self.db.remaining(coil), 1000.0)

    def test_a_used_up_coil_leaves_the_available_list(self):
        cid = self.db.add_consignment("HI", coils(1000, 2000))
        c1 = self.db.coils(cid)[0]["id"]
        self.db.debit(c1, 1000)
        self.assertEqual([c["code"] for c in self.db.coils(cid, only_available=True)], ["HI-2"])
        g = self.db.consignments()[0]
        self.assertEqual((g["remaining_coils"], g["remaining_kg"], g["avg_remaining_kg"]), (1, 2000.0, 2000.0))

    # ---- nothing is forgotten or changed
    def test_ledger_cannot_be_changed_or_deleted(self):
        cid = self.db.add_consignment("HI", coils(1000))
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.db.execute("UPDATE ledger SET kg = 5")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.db.execute("DELETE FROM ledger")
        self.assertEqual(self.db.consignments()[0]["remaining_kg"], 1000.0)

    def test_nothing_is_ever_deleted(self):
        cid = self.db.add_consignment("HI", coils(1000))
        calc = self.db.save_calculation({"w": 1}, 1, 0, 0.0)
        self.db.create_job(calc, "F1", {}, {self.db.coils(cid)[0]["id"]: 100})
        for t in ("consignments", "coils", "calculations", "jobs", "job_coils", "events"):
            with self.assertRaises(sqlite3.DatabaseError):
                self.db.db.execute("DELETE FROM %s" % t)

    def test_coil_identity_cannot_change_but_notes_can(self):
        cid = self.db.add_consignment("HI", coils(1000))
        coil = self.db.coils(cid)[0]["id"]
        for sql in ("UPDATE coils SET weight_kg=5", "UPDATE coils SET code='X-1'", "UPDATE coils SET width_mm=1"):
            with self.assertRaises(sqlite3.DatabaseError):
                self.db.db.execute(sql)
        self.db.db.execute("UPDATE coils SET notes='scratched edge' WHERE id=?", (coil,))
        self.assertEqual(self.db.coils(cid)[0]["notes"], "scratched edge")

    def test_events_are_append_only(self):
        self.db.log("test", "hello")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.db.execute("UPDATE events SET message='x'")
        self.assertEqual(self.db.events(kind="test")[0]["message"], "hello")

    def test_archive_instead_of_delete(self):
        cid = self.db.add_consignment("OLD", coils(1000))
        self.db.archive_consignment(cid)
        self.assertEqual(self.db.consignments(), [])
        self.assertEqual(len(self.db.consignments(include_archived=True)), 1)
        self.db.archive_consignment(cid, False)
        self.assertEqual(len(self.db.consignments()), 1)

    # ---- calculations
    def test_every_calculation_is_kept_and_searchable(self):
        a = self.db.save_calculation({"width": 1290, "sizes": [111, 250, 79]}, 8, 2, 0.01)
        b = self.db.save_calculation({"width": 1260, "sizes": [225, 235]}, 3, 5, 0.01)
        self.assertEqual([c["id"] for c in self.db.calculations()], [b, a])
        self.assertEqual([c["id"] for c in self.db.calculations(search="1290")], [a])
        self.assertEqual(self.db.calculations()[1]["inputs"]["sizes"], [111, 250, 79])

    def test_choice_can_be_recorded_but_inputs_cannot_change(self):
        a = self.db.save_calculation({"width": 1290}, 8, 2, 0.01)
        self.db.set_selected_formula(a, "F4", {"qty": [4, 3, 1]})
        c = self.db.calculations()[0]
        self.assertEqual((c["selected_formula"], c["selected"]["qty"]), ("F4", [4, 3, 1]))
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.db.execute("UPDATE calculations SET inputs_json='{}'")

    # ---- jobs
    def _job_setup(self, weights=(10000, 10000)):
        cid = self.db.add_consignment("HI", coils(*weights))
        ids = [c["id"] for c in self.db.coils(cid)]
        calc = self.db.save_calculation({"width": 1260}, 8, 2, 0.01, consignment_id=cid)
        return cid, ids, calc

    def test_planned_job_does_not_touch_stock_then_done_debits(self):
        cid, ids, calc = self._job_setup()
        jid, code = self.db.create_job(calc, "F4", {"qty": [4, 3, 1]}, {ids[0]: 10000, ids[1]: 9000})
        self.assertTrue(code.startswith("J-") and code.endswith("-0001"))
        self.assertEqual(self.db.consignments()[0]["remaining_kg"], 20000.0)
        self.db.complete_job(jid)
        self.assertEqual(self.db.remaining(ids[0]), 0.0)
        self.assertEqual(self.db.remaining(ids[1]), 1000.0)
        self.assertEqual(self.db.jobs()[0]["status"], "done")
        self.assertEqual([r["kind"] for r in self.db.ledger(coil_id=ids[0])], ["job", "receipt"])

    def test_job_cannot_be_completed_twice_or_cancelled_after(self):
        cid, ids, calc = self._job_setup()
        jid, _ = self.db.create_job(calc, "F1", {}, {ids[0]: 1000})
        self.db.complete_job(jid)
        with self.assertRaises(SlitraDBError):
            self.db.complete_job(jid)
        with self.assertRaises(SlitraDBError):
            self.db.cancel_job(jid)
        self.assertEqual(self.db.remaining(ids[0]), 9000.0)

    def test_cancel_a_planned_job(self):
        cid, ids, calc = self._job_setup()
        jid, _ = self.db.create_job(calc, "F1", {}, {ids[0]: 1000})
        self.db.cancel_job(jid)
        self.assertEqual(self.db.jobs()[0]["status"], "cancelled")
        self.assertEqual(self.db.remaining(ids[0]), 10000.0)

    def test_completing_is_all_or_nothing(self):
        cid, ids, calc = self._job_setup()
        jid, _ = self.db.create_job(calc, "F1", {}, {ids[0]: 4000, ids[1]: 12000})      # the second coil is short
        with self.assertRaises(StockError):
            self.db.complete_job(jid)
        self.assertEqual(self.db.remaining(ids[0]), 10000.0)        # the first debit was rolled back
        self.assertEqual(self.db.jobs()[0]["status"], "planned")

    def test_job_numbers_count_up(self):
        cid, ids, calc = self._job_setup()
        codes = [self.db.create_job(calc, "F1", {}, {ids[0]: 100})[1] for _ in range(3)]
        self.assertEqual([c.rsplit("-", 1)[1] for c in codes], ["0001", "0002", "0003"])

    def test_job_remembers_its_coils(self):
        cid, ids, calc = self._job_setup()
        self.db.create_job(calc, "F4", {"qty": [4, 3, 1]}, {ids[0]: 10000, ids[1]: 9000})
        j = self.db.jobs()[0]
        self.assertEqual([(c["code"], c["kg"]) for c in j["coils"]], [("HI-1", 10000.0), ("HI-2", 9000.0)])
        self.assertEqual(j["plan"]["qty"], [4, 3, 1])

    # ---- the log
    def test_log_and_speed(self):
        t0 = time.time()
        self.db.db.execute("BEGIN")
        for i in range(20000):
            self.db.log("bulk", "event %d" % i)
        self.db.db.execute("COMMIT")
        self.assertLess(time.time() - t0, 6)
        self.assertEqual(len(self.db.events(limit=50, kind="bulk")), 50)

    # ---- persistence and backups
    def test_data_survives_closing_and_opening(self):
        cid = self.db.add_consignment("HI", coils(10000, 9000))
        self.db.debit(self.db.coils(cid)[0]["id"], 1000)
        self.db.close()
        again = SlitraDB(self.path, mirror_dir=self.mirror)
        g = again.consignments()[0]
        self.assertEqual((g["name"], g["coils"], g["remaining_kg"]), ("HI", 2, 18000.0))
        again.close()

    def test_backup_is_verified_complete_and_mirrored(self):
        self.db.add_consignment("HI", coils(10000))
        dest = self.db.backup_now("test")
        self.assertTrue(self.db.integrity_check(dest))
        con = sqlite3.connect(dest)
        self.assertEqual(con.execute("SELECT name FROM consignments").fetchone()[0], "HI")
        con.close()
        self.assertTrue(os.path.exists(os.path.join(self.mirror, os.path.basename(dest))))

    def test_automatic_backup_happens_once_a_day_and_old_ones_are_pruned(self):
        self.assertEqual(len(os.listdir(self.db.backup_dir)), 1)       # made when the database was created
        self.db.keep_backups = 3
        for _ in range(6):
            self.db.backup_now("t")
        self.assertEqual(len(os.listdir(self.db.backup_dir)), 3)
        before = len(os.listdir(self.db.backup_dir))
        self.db._auto_backup()                                           # one is younger than 24 h: nothing new
        self.assertEqual(len(os.listdir(self.db.backup_dir)), before)

    def test_export_json_is_readable(self):
        self.db.add_consignment("HI", coils(10000))
        out = self.db.export_json(os.path.join(self.dir, "all.json"))
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["consignments"][0]["name"], "HI")
        self.assertEqual(data["coils"][0]["code"], "HI-1")
        self.assertEqual(data["ledger"][0]["kind"], "receipt")

    def test_schema_version_and_integrity(self):
        self.assertEqual(self.db.schema_version, 1)
        self.assertTrue(self.db.integrity_check())

    def test_arabic_names_work(self):
        cid = self.db.add_consignment("الرسالة-١", coils(10000), supplier="مصنع")
        self.assertEqual(self.db.consignments()[0]["name"], "الرسالة-١")
        self.assertEqual(self.db.coils(cid)[0]["code"], "الرسالة-١-1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
