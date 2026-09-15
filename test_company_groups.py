"""Company grouping, repeat applications and legacy database compatibility."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from store import Store, ValidationError


class CompanyGroupsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'records.sqlite3'
        self.store = Store(self.path)

    def test_exact_company_normalization_and_explicit_repeat(self):
        first = self.store.create({'company':' Acme ', 'role':'算法', 'batch':'提前批'})
        other = self.store.create({'company':'ACME', 'role':'后端'})
        self.assertEqual(other['company'], 'Acme')
        with self.assertRaises(ValidationError):
            self.store.create({'company':'acme', 'role':'算法', 'batch':'正式批'})
        again = self.store.create({'company':'acme', 'role':'算法', 'batch':'正式批', 'allow_repeat':True})
        self.assertNotEqual(first['id'], again['id'])
        self.assertEqual(again['batch'], '正式批')
        self.store.add_event(first['id'], {'status':'已结束'})
        self.store.add_event(again['id'], {'status':'一面', 'next_action':'技术面试', 'due_at':'2027-03-10T14:00'})
        self.assertEqual(self.store.get(first['id'])['status'], '已结束')
        self.assertEqual(self.store.get(other['id'])['status'], '已投递')
        self.assertEqual(len(self.store.get(again['id'])['events']), 2)
        self.store.delete(first['id'])
        self.assertEqual(self.store.get(again['id'])['next_action'], '技术面试')

    def test_repeat_backup_roundtrip_and_legacy_import(self):
        first = self.store.create({'company':'示例', 'role':'算法'})
        second = self.store.create({'company':'示例', 'role':'算法', 'allow_repeat':True})
        exported = self.store.export()
        self.assertEqual(exported['version'], 2)
        restored = Store(Path(self.temp.name) / 'restored.sqlite3')
        self.assertEqual(restored.import_data(exported), {'imported':2, 'skipped':0})
        self.assertEqual(restored.import_data(exported), {'imported':0, 'skipped':2})
        self.assertEqual(restored.get(second['id'])['events'], second['events'])
        legacy = {'format':'autumn-workbench', 'version':1, 'applications':[{**first, 'id':'legacy-copy', 'events':[]}]}
        self.assertEqual(restored.import_data(legacy), {'imported':0, 'skipped':1})

    def test_invalid_repeat_and_batch_are_rejected(self):
        for changes in ({'allow_repeat':'true'}, {'batch':None}, {'batch':'a'*81}):
            with self.assertRaises(ValidationError):
                self.store.create({'company':'示例', 'role':'算法', **changes})

    def test_migrate_unique_schema_preserves_ids_events_and_preferences(self):
        legacy_path = Path(self.temp.name) / 'legacy.sqlite3'
        record = self.store.create({'company':'旧公司', 'role':'旧岗位'})
        payload = {k:v for k,v in record.items() if k not in ('events','batch')}
        with sqlite3.connect(legacy_path) as con:
            con.executescript('''CREATE TABLE applications(id TEXT PRIMARY KEY, company TEXT NOT NULL COLLATE NOCASE, role TEXT NOT NULL COLLATE NOCASE, payload TEXT NOT NULL, UNIQUE(company, role));
CREATE TABLE events(id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE, payload TEXT NOT NULL);
CREATE TABLE preferences(key TEXT PRIMARY KEY, payload TEXT NOT NULL);
PRAGMA user_version=1;''')
            con.execute('INSERT INTO applications VALUES(?,?,?,?)',(record['id'],record['company'],record['role'],json.dumps(payload)))
            for event in record['events']:
                con.execute('INSERT INTO events VALUES(?,?,?)',(event['id'],record['id'],json.dumps(event)))
            con.execute('INSERT INTO preferences VALUES(?,?)',('personalization',json.dumps({'icon':'sun'})))
        migrated = Store(legacy_path)
        self.assertEqual(migrated.get(record['id'])['events'], record['events'])
        self.assertEqual(migrated.get(record['id'])['batch'], '')
        self.assertEqual(migrated.personalization()['icon'], 'sun')
        repeated = migrated.create({'company':'旧公司','role':'旧岗位','allow_repeat':True})
        self.assertNotEqual(repeated['id'], record['id'])
        with migrated.connect() as con:
            self.assertEqual(con.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertTrue(list(legacy_path.parent.glob('backups/*before-company-groups.sqlite3')))
        self.assertEqual(len(Store(legacy_path).list()), 2)
