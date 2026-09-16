import json
import tempfile
import unittest
from pathlib import Path
from store import Store, ValidationError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'records.sqlite3'
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def create(self, **fields):
        return self.store.create({'company': '示例公司', 'role': '算法工程师', **fields})

    def test_personalization_defaults_persist_and_reset(self):
        defaults = self.store.personalization()
        self.assertEqual(defaults['icon'], 'leaf')
        updated = self.store.set_personalization({'tagline': '慢慢来，也在前进', 'icon': 'star'})
        self.assertEqual(updated['title'], defaults['title'])
        self.assertEqual(Store(self.path).personalization(), updated)
        self.assertEqual(self.store.set_personalization(defaults), defaults)
        for data in ({'icon': 'javascript:bad'}, {'body': None}, {'tagline': 'a'*81}, {'unexpected': 'value'}):
            with self.assertRaises(ValidationError):
                self.store.set_personalization(data)
        self.assertEqual(self.store.personalization(), defaults)

    def test_personalization_backup_restore_and_old_backup_compatibility(self):
        preferences = self.store.set_personalization({'title': '给自己一点耐心', 'body': '先做好今天的事。', 'icon': 'sun'})
        backup = self.store.export()
        restored = Store(Path(self.temp.name) / 'restored.sqlite3')
        restored.import_data(backup)
        self.assertEqual(restored.personalization(), preferences)
        restored.set_personalization({'title': '自己的寄语'})
        restored.import_data(backup)
        self.assertEqual(restored.personalization()['title'], '自己的寄语')
        old_backup = {k:v for k,v in backup.items() if k != 'personalization'}
        restored.import_data(old_backup)
        self.assertEqual(restored.personalization()['title'], '自己的寄语')
        backup['personalization']['icon'] = '<script>'
        with self.assertRaises(ValidationError):
            restored.import_data(backup)

    def test_company_classification_persists_and_survives_backup(self):
        app = self.create(company_type='外企', industry='互联网')
        self.assertEqual(app.get('company_type'), '外企')
        self.store.update(app['id'], {'note':'更新备注'})
        self.assertEqual(Store(self.path).get(app['id'])['industry'], '互联网')
        restored = Store(Path(self.temp.name) / 'restore.sqlite3')
        restored.import_data(self.store.export())
        self.assertEqual(restored.get(app['id'])['company_type'], '外企')
        self.assertEqual(self.store.update(app['id'], {'company_type':''})['company_type'], '')

    def test_old_records_and_backups_remain_editable(self):
        app = self.create()
        old = {k:v for k,v in app.items() if k not in ('company_type','industry','events')}
        with self.store.connect() as con:
            con.execute('UPDATE applications SET payload=? WHERE id=?', (json.dumps(old),app['id']))
        self.assertEqual(self.store.get(app['id']).get('company_type'), '')
        self.assertEqual(self.store.update(app['id'], {'industry':'制造业'})['industry'], '制造业')
        restored = Store(Path(self.temp.name) / 'old.sqlite3')
        restored.import_data({'format':'autumn-workbench','version':1,'applications':[old]})
        self.assertEqual(restored.get(app['id'])['industry'], '')

    def test_classification_rejects_unknown_values(self):
        for changes in ({'company_type':'上市公司'}, {'industry':'随便填'}, {'company_type':None}):
            with self.assertRaises(ValidationError):
                self.create(**changes)

    def test_job_code_roundtrip_edit_and_old_record_default(self):
        app = self.create(job_code='  001-AI-26  ')
        self.assertEqual(app.get('job_code'), '001-AI-26')
        self.store.update(app['id'], {'note':'其他修改'})
        self.assertEqual(Store(self.path).get(app['id'])['job_code'], '001-AI-26')
        restored = Store(Path(self.temp.name) / 'code-restore.sqlite3')
        restored.import_data(self.store.export())
        self.assertEqual(restored.get(app['id'])['job_code'], '001-AI-26')
        self.assertEqual(self.store.update(app['id'], {'job_code':''})['job_code'], '')
        with self.store.connect() as con:
            payload = json.loads(con.execute('SELECT payload FROM applications WHERE id=?', (app['id'],)).fetchone()[0])
            payload.pop('job_code')
            con.execute('UPDATE applications SET payload=? WHERE id=?', (json.dumps(payload), app['id']))
        self.assertEqual(self.store.get(app['id'])['job_code'], '')
        for value in (123, None, 'x'*101):
            with self.assertRaises(ValidationError):
                self.store.update(app['id'], {'job_code':value})

    def test_persist_and_keep_different_roles_separate(self):
        first = self.create()
        self.create(role='后端工程师')
        self.assertEqual(len(Store(self.path).list()), 2)
        self.assertEqual(Store(self.path).get(first['id'])['company'], '示例公司')
        with self.assertRaises(ValidationError):
            self.create(company=' 示例公司 ')

    def test_event_updates_next_action_without_erasing_history(self):
        app = self.create()
        updated = self.store.add_event(app['id'], {'status': '一面', 'note': '项目追问', 'occurred_on': '2026-09-15', 'next_action': '准备二面', 'due_at': '2026-09-18T14:00'})
        self.assertEqual(updated['status'], '一面')
        self.assertEqual(updated['due_at'], '2026-09-18T14:00')
        self.assertEqual(len(updated['events']), 2)
        self.store.update(app['id'], {'note': '保留面试复盘'})
        self.assertEqual(len(self.store.get(app['id'])['events']), 2)
        finished = self.store.update(app['id'], {'status': '已结束'})
        self.assertEqual(finished['next_action'], '')
        self.assertEqual(len(finished['events']), 3)

    def test_complete_task_leaves_a_history_entry(self):
        app = self.create(next_action='完成测评', due_at='2026-09-16T19:00')
        result = self.store.complete(app['id'])
        self.assertEqual(result['next_action'], '')
        self.assertEqual(result['due_at'], '')
        self.assertIn('完成测评', result['events'][-1]['note'])

    def test_import_roundtrip_and_skip_existing_without_overwriting(self):
        app = self.create()
        self.store.add_event(app['id'], {'status': '二面', 'note': '复盘', 'occurred_on': '2026-09-15'})
        backup = self.store.export()
        second = Store(Path(self.temp.name) / 'second.sqlite3')
        result = second.import_data(backup)
        self.assertEqual(result, {'imported': 1, 'skipped': 0})
        self.assertEqual(second.get(app['id'])['events'], self.store.get(app['id'])['events'])
        self.assertEqual(second.import_data(backup), {'imported': 0, 'skipped': 1})
        self.assertTrue(list(second.path.parent.glob('backups/*.sqlite3')))

    def test_bad_import_is_atomic_and_dates_are_validated(self):
        valid = self.create()
        backup = self.store.export()
        self.store.delete(valid['id'])
        backup['applications'].append({**valid, 'id': 'bad-record', 'company': '另一家公司', 'due_at': 'not-a-date'})
        with self.assertRaises(ValidationError):
            self.store.import_data(backup)
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(ValidationError):
            self.create(due_at='2026-09-31T14:00')
        with self.assertRaises(ValidationError):
            self.create(url='javascript:alert(1)')
        with self.assertRaises(ValidationError):
            self.create(company=' ')

    def test_delete_cascades_history_and_backup_contains_original(self):
        app = self.create()
        self.store.delete(app['id'])
        self.assertEqual(self.store.list(), [])
        snapshots = list(self.path.parent.glob('backups/*.sqlite3'))
        self.assertTrue(snapshots)
        self.assertTrue(any(Store(p).list() for p in snapshots))


if __name__ == '__main__':
    unittest.main()
