"""Durable local application records. No third-party dependencies."""
import json
import sqlite3
import threading
import uuid
from company_logos import validate_logo
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

STATUSES = ['待投递', '已投递', '筛选中', '测评', '笔试', '一面', '二面', '终面', 'HR面', 'Offer', '已结束', '待确认']
TERMINAL = {'已结束'}
COMPANY_TYPES = ['央企', '国企', '民企', '外企', '合资企业', '事业单位', '其他']
INDUSTRIES = ['互联网', '人工智能', '金融', '制造业', '能源', '通信', '医疗健康', '教育科研', '消费零售', '其他']
FIELDS = ('company', 'role', 'status', 'priority', 'applied_on', 'city', 'channel', 'url', 'resume', 'note', 'next_action', 'due_at', 'company_type', 'industry', 'batch', 'job_code')

PERSONALIZATION_DEFAULTS = {
    'tagline': '今天也按自己的节奏来',
    'title': '留一点空间给自己',
    'body': '安排记在这里，精力留给准备。\n完成一件，就轻轻划掉一件。',
    'icon': 'leaf',
}
PERSONALIZATION_ICONS = {'leaf': '叶子', 'sun': '太阳', 'star': '星星', 'heart': '爱心', 'coffee': '咖啡', 'compass': '指南针'}


class ValidationError(ValueError):
    pass


class DuplicateApplication(ValidationError):
    def __init__(self, matches):
        super().__init__('这个公司的同名岗位已有记录，请选择更新已有投递或明确新增一次')
        self.matches = matches


def company_key(value):
    return value.strip().lower()


def now():
    return datetime.now().isoformat(timespec='microseconds')


def text(value, name, limit=1000):
    if not isinstance(value, str):
        raise ValidationError(name + '必须是文字')
    value = value.strip()
    if len(value) > limit:
        raise ValidationError(name + '过长')
    return value


def normalize_personalization(data, base=None):
    if not isinstance(data, dict) or set(data) - PERSONALIZATION_DEFAULTS.keys():
        raise ValidationError('个性化设置格式不正确')
    result = dict(PERSONALIZATION_DEFAULTS if base is None else base)
    for key, value in data.items():
        result[key] = text(value, '个性化内容', {'tagline':80, 'title':40, 'body':300, 'icon':20}[key])
        if not result[key]:
            raise ValidationError('请填写内容，或使用恢复默认')
    if result['icon'] not in PERSONALIZATION_ICONS:
        raise ValidationError('请选择提供的图标')
    return result


def valid_date(value, name, with_time=False, optional=False):
    value = text(value, name, 32)
    if not value and optional:
        return ''
    try:
        if with_time:
            parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M')
            if parsed.strftime('%Y-%m-%dT%H:%M') != value:
                raise ValueError()
        else:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError()
    except ValueError:
        raise ValidationError(name + '格式不正确，请使用有效日期')
    return value


def normalize(data, base=None):
    if not isinstance(data, dict):
        raise ValidationError('记录格式不正确')
    result = {key: '' for key in FIELDS}
    result.update(status='已投递', priority='普通', applied_on=date.today().isoformat())
    if base:
        result.update({key: base.get(key, '') for key in FIELDS})
    result.update({key: data[key] for key in FIELDS if key in data})
    for key in FIELDS:
        result[key] = text(result[key], key, 20000 if key == 'note' else 2000)
    if not result['company'] or not result['role']:
        raise ValidationError('请填写公司和岗位')
    if len(result['company']) > 160 or len(result['role']) > 200:
        raise ValidationError('公司或岗位名称过长')
    result['batch'] = text(result['batch'], '批次', 80)
    result['job_code'] = text(result['job_code'], '岗位编号', 100)
    if result['status'] not in STATUSES:
        raise ValidationError('请选择有效阶段')
    if result['priority'] not in ('普通', '重点关注'):
        raise ValidationError('请选择有效优先级')
    for key, label, values in [('company_type','企业性质',COMPANY_TYPES), ('industry','所属行业',INDUSTRIES)]:
        if result[key] and result[key] not in values:
            raise ValidationError('请选择有效的' + label)
    result['applied_on'] = valid_date(result['applied_on'], '投递日期')
    result['due_at'] = valid_date(result['due_at'], '安排时间', True, True)
    if result['url']:
        parsed = urlsplit(result['url'])
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValidationError('岗位链接请以 http:// 或 https:// 开头')
    if result['due_at'] and not result['next_action']:
        raise ValidationError('设置时间时，请填写下一步要做什么')
    if result['status'] in TERMINAL:
        result['next_action'] = result['due_at'] = ''
    return result


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._migrate_company_groups()
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS applications (
                    id TEXT PRIMARY KEY,
                    company TEXT NOT NULL COLLATE NOCASE,
                    role TEXT NOT NULL COLLATE NOCASE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_application_id ON events(application_id);
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                PRAGMA user_version = 2;
            ''')

    def _migrate_company_groups(self):
        # SQLite cannot drop a table-level UNIQUE constraint in place. Keep IDs
        # and row order, with foreign keys disabled only on this migration connection.
        if not self.path.exists():
            return
        with self.connect() as con:
            row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='applications'").fetchone()
        if not row or 'UNIQUE' not in row[0].upper():
            return
        self.backup('before-company-groups')
        con = sqlite3.connect(str(self.path), timeout=10)
        try:
            con.execute('PRAGMA foreign_keys=OFF')
            with con:
                con.execute('BEGIN IMMEDIATE')
                con.execute('CREATE TABLE applications_v2(id TEXT PRIMARY KEY, company TEXT NOT NULL COLLATE NOCASE, role TEXT NOT NULL COLLATE NOCASE, payload TEXT NOT NULL)')
                con.execute('INSERT INTO applications_v2 SELECT id,company,role,payload FROM applications ORDER BY rowid')
                con.execute('DROP TABLE applications')
                con.execute('ALTER TABLE applications_v2 RENAME TO applications')
                if con.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValidationError('旧数据关联检查失败，原数据库未修改')
                con.execute('PRAGMA user_version=2')
        finally:
            con.close()

    @contextmanager
    def connect(self):
        con = sqlite3.connect(str(self.path), timeout=10)
        con.execute('PRAGMA foreign_keys = ON')
        try:
            with con:
                yield con
        finally:
            con.close()

    def personalization(self):
        with self.connect() as con:
            row = con.execute("SELECT payload FROM preferences WHERE key='personalization'").fetchone()
            return normalize_personalization(json.loads(row[0]) if row else {})

    def set_personalization(self, data):
        with self.lock:
            result = normalize_personalization(data, self.personalization())
            with self.connect() as con:
                con.execute("INSERT INTO preferences(key,payload) VALUES('personalization',?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload", (json.dumps(result, ensure_ascii=False),))
            return result

    def company_logos(self):
        with self.connect() as con:
            return {key[len('company-logo:'):]:json.loads(payload) for key,payload in
                    con.execute("SELECT key,payload FROM preferences WHERE key LIKE 'company-logo:%'")}

    def set_company_logo(self, company, value):
        company = text(company, '公司', 160)
        if not company:
            raise ValidationError('请先填写公司名称')
        try:
            logo = validate_logo(value) if value is not None else None
        except ValueError as error:
            raise ValidationError(str(error))
        key = 'company-logo:' + company_key(company)
        with self.lock, self.connect() as con:
            if logo is None:
                con.execute('DELETE FROM preferences WHERE key=?', (key,))
            else:
                con.execute('INSERT INTO preferences(key,payload) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload', (key,json.dumps(logo, ensure_ascii=False)))
        return logo

    def _get(self, con, app_id):
        row = con.execute('SELECT payload FROM applications WHERE id=?', (app_id,)).fetchone()
        if row is None:
            raise KeyError('这条投递已不存在，请刷新列表')
        app = json.loads(row[0])
        app.setdefault('company_type', '')
        app.setdefault('industry', '')
        app.setdefault('batch', '')
        app.setdefault('job_code', '')
        app['events'] = [json.loads(r[0]) for r in con.execute('SELECT payload FROM events WHERE application_id=? ORDER BY rowid', (app_id,))]
        return app

    def get(self, app_id):
        with self.connect() as con:
            return self._get(con, app_id)

    def list(self):
        with self.connect() as con:
            return [self._get(con, r[0]) for r in con.execute('SELECT id FROM applications ORDER BY rowid DESC').fetchall()]

    def _save(self, con, app):
        payload = {key: value for key, value in app.items() if key != 'events'}
        # The first stored spelling is the canonical display name for an exact match.
        for (name,) in con.execute('SELECT company FROM applications ORDER BY rowid'):
            if company_key(name) == company_key(app['company']):
                app['company'] = name.strip()
                payload['company'] = app['company']
                break
        con.execute('''INSERT INTO applications(id, company, role, payload) VALUES(?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET company=excluded.company, role=excluded.role, payload=excluded.payload''',
            (app['id'], app['company'], app['role'], json.dumps(payload, ensure_ascii=False)))

    def _duplicates(self, con, app):
        return [self._get(con, row[0]) for row in con.execute('SELECT id,company,role FROM applications').fetchall()
                if row[0] != app.get('id') and company_key(row[1]) == company_key(app['company'])
                and company_key(row[2]) == company_key(app['role'])]

    def _event(self, con, app_id, status, note, occurred_on=None, kind='progress', **metadata):
        event = {'id': str(uuid.uuid4()), 'status': status, 'note': note,
                 'occurred_on': occurred_on or date.today().isoformat(), 'created_at': now(), 'kind': kind, **metadata}
        con.execute('INSERT INTO events VALUES(?,?,?)', (event['id'], app_id, json.dumps(event, ensure_ascii=False)))

    def create(self, data):
        app = normalize(data)
        if type(data.get('allow_repeat', False)) is not bool:
            raise ValidationError('新增一次投递的确认值必须为布尔值')
        app.update(id=str(uuid.uuid4()), created_at=now(), updated_at=now())
        with self.lock, self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            matches = self._duplicates(con, app)
            if matches and not data.get('allow_repeat', False):
                raise DuplicateApplication(matches)
            self._save(con, app)
            self._event(con, app['id'], app['status'], '建立投递记录', app['applied_on'])
            return self._get(con, app['id'])

    def update(self, app_id, data):
        with self.lock, self.connect() as con:
            old = self._get(con, app_id)
            app = {**old, **normalize(data, old), 'updated_at': now()}
            self._save(con, app)
            if old['status'] != app['status']:
                self._event(con, app_id, app['status'], '阶段更新：' + old['status'] + ' → ' + app['status'])
            return self._get(con, app_id)

    def add_event(self, app_id, data):
        if not isinstance(data, dict):
            raise ValidationError('进展格式不正确')
        note = text(data.get('note', ''), '进展记录', 20000)
        day = valid_date(data.get('occurred_on', date.today().isoformat()), '发生日期')
        with self.lock, self.connect() as con:
            old = self._get(con, app_id)
            changes = {'status': data.get('status', old['status'])}
            for key in ('next_action', 'due_at'):
                if key in data:
                    changes[key] = data[key]
            app = {**old, **normalize(changes, old), 'updated_at': now()}
            self._save(con, app)
            self._event(con, app_id, app['status'], note or '更新了投递进展', day)
            return self._get(con, app_id)

    def complete(self, app_id):
        with self.lock, self.connect() as con:
            app = self._get(con, app_id)
            if app['next_action']:
                self._event(con, app_id, app['status'], '已完成：' + app['next_action'], kind='task', task_title=app['next_action'], task_due_at=app['due_at'])
                app.update(next_action='', due_at='', updated_at=now())
                self._save(con, app)
            return self._get(con, app_id)

    def reopen_task(self, app_id, event_id):
        event_id = text(event_id, '待办编号', 100)
        with self.lock, self.connect() as con:
            app = self._get(con, app_id)
            event = next((e for e in app['events'] if e['id'] == event_id and e['kind'] == 'task'), None)
            if event is None:
                raise ValidationError('没有找到这条已完成事项')
            if event.get('task_reopened'):
                return app
            if app['next_action']:
                raise ValidationError('这个岗位已有新的待办，请先处理当前待办，再恢复这条事项')
            if app['status'] == '已结束':
                raise ValidationError('这份投递已结束，请先更新阶段，再恢复待办')
            title = event.get('task_title') or event['note'].removeprefix('已完成：')
            if not title:
                raise ValidationError('这条历史记录没有待办内容')
            app.update(next_action=title, due_at=event.get('task_due_at', ''), updated_at=now())
            event['task_reopened'] = True
            con.execute('UPDATE events SET payload=? WHERE id=? AND application_id=?',
                        (json.dumps(event, ensure_ascii=False), event_id, app_id))
            self._save(con, app)
            return self._get(con, app_id)

    def backup(self, label='manual'):
        folder = self.path.parent / 'backups'
        folder.mkdir(exist_ok=True)
        filename = (date.today().isoformat() + '-daily.sqlite3' if label == 'daily' else datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + label + '.sqlite3')
        target = folder / filename
        with self.lock:
            if label == 'daily' and target.exists():
                return target
            with self.connect() as source:
                dest = sqlite3.connect(str(target))
                try:
                    source.backup(dest)
                finally:
                    dest.close()
        return target

    def delete(self, app_id):
        with self.lock:
            self.get(app_id)
            self.backup('before-delete')
            with self.connect() as con:
                con.execute('DELETE FROM applications WHERE id=?', (app_id,))

    def export(self):
        return {'format': 'autumn-workbench', 'version': 2, 'exported_at': now(), 'applications': self.list(), 'personalization': self.personalization(), 'company_logos': self.company_logos()}

    def import_data(self, data):
        if not isinstance(data, dict) or data.get('format') != 'autumn-workbench' or data.get('version') not in (1, 2):
            raise ValidationError('请选择本工作台导出的 JSON 备份文件')
        preferences = normalize_personalization(data['personalization']) if 'personalization' in data else None
        raw_logos = data.get('company_logos', {})
        if not isinstance(raw_logos, dict) or len(raw_logos)>10000:
            raise ValidationError('公司图标备份格式不正确')
        logos = {}
        for company, value in raw_logos.items():
            key = company_key(text(company, '图标公司名称', 160))
            if not key:
                raise ValidationError('图标公司名称不能为空')
            try:
                logos[key] = validate_logo(value)
            except ValueError as error:
                raise ValidationError(str(error))
        apps = data.get('applications')
        if not isinstance(apps, list):
            raise ValidationError('备份记录列表不正确')
        validated, seen_ids, seen_event_ids = [], set(), set()
        for item in apps:
            app = normalize(item)
            app_id = text(item.get('id'), '记录编号', 100)
            if not app_id or app_id in seen_ids:
                raise ValidationError('备份存在空编号或重复编号')
            seen_ids.add(app_id)
            app.update(id=app_id, created_at=text(item.get('created_at', now()), '创建时间', 40), updated_at=text(item.get('updated_at', now()), '更新时间', 40))
            events = item.get('events', [])
            if not isinstance(events, list):
                raise ValidationError('时间线格式不正确')
            app['events'] = []
            for entry in events:
                if not isinstance(entry, dict):
                    raise ValidationError('时间线格式不正确')
                event_id = text(entry.get('id'), '进展编号', 100)
                if not event_id or event_id in seen_event_ids or entry.get('status') not in STATUSES:
                    raise ValidationError('时间线编号或阶段不正确')
                seen_event_ids.add(event_id)
                app['events'].append({'id': event_id, 'status': entry['status'], 'note': text(entry.get('note', ''), '进展记录', 20000), 'occurred_on': valid_date(entry.get('occurred_on'), '进展日期'), 'created_at': text(entry.get('created_at', now()), '进展创建时间', 40), 'kind': 'task' if entry.get('kind') == 'task' else 'progress'})
                if app['events'][-1]['kind'] == 'task':
                    event = app['events'][-1]
                    if 'task_title' in entry:
                        event['task_title'] = text(entry['task_title'], '已完成事项', 2000)
                    if 'task_due_at' in entry:
                        event['task_due_at'] = valid_date(entry['task_due_at'], '原安排时间', with_time=True, optional=True)
                    if 'task_reopened' in entry:
                        if type(entry['task_reopened']) is not bool:
                            raise ValidationError('待办恢复状态不正确')
                        event['task_reopened'] = entry['task_reopened']
            validated.append(app)
        with self.lock:
            self.backup('before-import')
            imported = skipped = 0
            with self.connect() as con:
                for app in validated:
                    if con.execute('SELECT 1 FROM applications WHERE id=?', (app['id'],)).fetchone() or (data['version'] == 1 and self._duplicates(con, app)):
                        skipped += 1
                        continue
                    for event in app['events']:
                        if con.execute('SELECT 1 FROM events WHERE id=?', (event['id'],)).fetchone():
                            raise ValidationError('进展编号与现有记录冲突，未导入任何记录')
                    self._save(con, app)
                    for event in app['events']:
                        con.execute('INSERT INTO events VALUES(?,?,?)', (event['id'], app['id'], json.dumps(event, ensure_ascii=False)))
                    imported += 1
                for company, logo in logos.items():
                    con.execute('INSERT OR IGNORE INTO preferences(key,payload) VALUES(?,?)', ('company-logo:'+company,json.dumps(logo,ensure_ascii=False)))
                if preferences is not None:
                    con.execute("INSERT OR IGNORE INTO preferences(key,payload) VALUES('personalization',?)", (json.dumps(preferences, ensure_ascii=False),))
            return {'imported': imported, 'skipped': skipped}
