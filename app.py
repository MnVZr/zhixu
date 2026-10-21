"""知序 — offline research journal. Python standard-library runtime."""
import datetime as dt
from contextlib import contextmanager
import io
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
import tasks
import desktop
import storage
import journals

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
ASSETS = Path(getattr(sys, '_MEIPASS', ROOT)) / 'web'
try:
    DATA = storage.resolve(ROOT)
    STARTUP_ERROR = None
except Exception as e:
    DATA = ROOT / 'data'
    STARTUP_ERROR = str(e)
DATA_LOCK = threading.RLock()
INSTANCE = None
ACTIVE_GUARD = None
SERVICE_URL = ''
TOKEN = secrets.token_urlsafe(32)
MEDIA_TYPES = ('image/jpeg', 'image/png', 'image/gif', 'image/webp', 'video/mp4')
STOP = threading.Event()
TRAY = None
last_seen = time.time()

@contextmanager
def connect():
    DATA_LOCK.acquire()
    try: c = sqlite3.connect(DATA / 'journal.db', timeout=15)
    except Exception:
        DATA_LOCK.release(); raise
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()
        DATA_LOCK.release()

def init():
    (DATA / 'attachments').mkdir(parents=True, exist_ok=True)
    # SQLite's backup API keeps existing journals intact before upgrading the schema.
    if (DATA / 'journal.db').exists():
        with connect() as c:
            if c.execute('PRAGMA user_version').fetchone()[0] < 3:
                folder = DATA / 'upgrade-backups'; folder.mkdir(exist_ok=True)
                destination = sqlite3.connect(folder / ('before-1.3-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db'))
                try: c.backup(destination)
                finally: destination.close()
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS days(date TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', updated TEXT);
        CREATE TABLE IF NOT EXISTS todos(id TEXT PRIMARY KEY, date TEXT NOT NULL, text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY, date TEXT NOT NULL, name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS categories(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS albums(id TEXT PRIMARY KEY, name TEXT NOT NULL, category_id TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS album_items(album_id TEXT NOT NULL, attachment_id TEXT NOT NULL, PRIMARY KEY(album_id,attachment_id));
        CREATE INDEX IF NOT EXISTS album_media_idx ON album_items(attachment_id);
        ''')
        if 'journal_visible' not in [x['name'] for x in c.execute('PRAGMA table_info(attachments)')]:
            c.execute('ALTER TABLE attachments ADD COLUMN journal_visible INTEGER NOT NULL DEFAULT 1')
        columns={x['name'] for x in c.execute('PRAGMA table_info(attachments)')}
        for name,definition in {'annotation':"TEXT NOT NULL DEFAULT ''",'imported_at':"TEXT NOT NULL DEFAULT ''",'imported_estimated':'INTEGER NOT NULL DEFAULT 0'}.items():
            if name not in columns: c.execute(f'ALTER TABLE attachments ADD COLUMN {name} {definition}')
        for row in list(c.execute("SELECT id FROM attachments WHERE imported_at=''")):
            file=DATA/'attachments'/row['id']
            if file.exists():
                stat=file.stat();stamp=getattr(stat,'st_birthtime',stat.st_ctime)
                c.execute('UPDATE attachments SET imported_at=?,imported_estimated=1 WHERE id=?',(dt.datetime.fromtimestamp(stamp).isoformat(timespec='seconds'),row['id']))
        tasks.migrate(c)
        journals.migrate(c)
        c.execute('PRAGMA user_version=3')

def task_tick(now=None):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        tasks.tick(c,now)

def scheduler():
    while not STOP.is_set():
        try:
            task_tick()
            if TRAY is not None:
                with connect() as c:
                    notices=[x for x in tasks.notifications(c) if not x['delivered']]
                    sound=tasks.value(c,'reminder_sound',True)
                if notices:
                    first=notices[0]
                    text=f"{first['start_time']}–{first['end_time']}  {first['text']}"
                    if len(notices)>1: text+=f"\n另有 {len(notices)-1} 项待办到时。打开知序查看。"
                    TRAY.notify(text[:240],'知序 · 待办提醒')
                    if sound:
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    with connect() as c:
                        for item in notices: c.execute('UPDATE reminder_events SET delivered=1 WHERE todo_id=? AND schedule_key=?',(item['todo_id'],item['schedule_key']))
        except Exception as e:
            (DATA/'background-error.log').write_text(dt.datetime.now().isoformat()+' '+str(e),encoding='utf-8')
        STOP.wait(5)

def require_album(c, id):
    if not c.execute('SELECT id FROM albums WHERE id=?', (id,)).fetchone():
        raise ValueError('相册不存在')

def name_value(data):
    name = data['name'].strip()
    if not name or len(name) > 100: raise ValueError('名称需要 1 至 100 个字符')
    return name

def gallery_change(c, path, data):
    if path == '/api/media/update':
        row=c.execute('SELECT * FROM attachments WHERE id=?',(data['id'],)).fetchone()
        if not row or row['mime'] not in MEDIA_TYPES: raise ValueError('图片或视频不存在')
        name=data.get('name',row['name']).strip();note=data.get('annotation',row['annotation']).strip()
        if not name or len(name)>240 or any(ch in name for ch in '\\/:*?"<>|\r\n') or name in ('.','..'): raise ValueError('文件名不能为空，也不能包含路径或特殊字符')
        suffix=Path(row['name']).suffix
        if Path(name).suffix.lower()!=suffix.lower():
            if Path(name).suffix.lower() in ('.jpg','.jpeg','.png','.gif','.webp','.mp4'): raise ValueError('不能更改媒体类型')
            name+=suffix
        if len(note)>10000: raise ValueError('批注最多 10000 个字符')
        c.execute('UPDATE attachments SET name=?,annotation=? WHERE id=?',(name,note,data['id']))
        if note!=row['annotation']:
            import re
            from html import escape
            for entry in list(c.execute('SELECT id,date,body FROM entries WHERE body LIKE ?',('%'+row['id']+'%',))):
                pattern=r'(<figure\b[^>]*data-media-id=[\"\x27]'+re.escape(row['id'])+r'[\"\x27][^>]*>)(.*?)(</figure>)'
                def replace_caption(match):
                    middle=re.sub(r'<figcaption\b[^>]*>.*?</figcaption>',lambda _: '<figcaption>'+escape(note)+'</figcaption>',match[2],flags=re.S)
                    return match[1]+middle+match[3]
                body=re.sub(pattern,replace_caption,entry['body'],flags=re.S)
                c.execute('UPDATE entries SET body=? WHERE id=?',(body,entry['id']));journals.sync_day(c,entry['date'])
    elif path == '/api/category/save':
        name = name_value(data)
        if data.get('id'):
            c.execute('UPDATE categories SET name=? WHERE id=?', (name, data['id']))
        else: c.execute('INSERT INTO categories VALUES(?,?)', (uuid.uuid4().hex, name))
    elif path == '/api/category/delete':
        c.execute("UPDATE albums SET category_id='' WHERE category_id=?", (data['id'],))
        c.execute('DELETE FROM categories WHERE id=?', (data['id'],))
    elif path == '/api/album/save':
        name = name_value(data); category = data.get('category_id', '')
        if category and not c.execute('SELECT id FROM categories WHERE id=?', (category,)).fetchone(): raise ValueError('分类不存在')
        id = data.get('id') or uuid.uuid4().hex
        if data.get('id'):
            require_album(c, id)
            c.execute('UPDATE albums SET name=?,category_id=? WHERE id=?', (name, category, id))
        else: c.execute('INSERT INTO albums VALUES(?,?,?,?)', (id, name, category, dt.datetime.now().isoformat()))
        return {'ok': True, 'id': id}
    elif path == '/api/album/delete':
        require_album(c, data['id'])
        c.execute('DELETE FROM album_items WHERE album_id=?', (data['id'],))
        c.execute('DELETE FROM albums WHERE id=?', (data['id'],))
    elif path == '/api/album/add':
        require_album(c, data['album_id'])
        ids = data['attachment_ids']
        if not isinstance(ids, list) or not ids: raise ValueError('请选择图片或视频')
        for id in ids:
            row = c.execute('SELECT mime FROM attachments WHERE id=?', (id,)).fetchone()
            if not row or row['mime'] not in MEDIA_TYPES: raise ValueError('只能加入图片或 MP4 视频')
            c.execute('INSERT OR IGNORE INTO album_items VALUES(?,?)', (data['album_id'], id))
    elif path == '/api/album/remove':
        require_album(c, data['album_id'])
        c.execute('DELETE FROM album_items WHERE album_id=? AND attachment_id=?', (data['album_id'], data['attachment_id']))
    else: return None
    return {'ok': True}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, data, status=200, mime='application/json; charset=utf-8', extra=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        elif isinstance(data, str):
            data = data.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            self.get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply({'error': '读取失败，请重试'}, 500)

    def get(self):
        with DATA_LOCK: self.get_locked()

    def get_locked(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)
        if p.path == '/api/storage':
            self.reply({'path':str(DATA),'version':3})
        elif p.path == '/api/export':
            kind=q.get('kind',['journals'])[0]
            with connect() as c: payload=storage.export(c,DATA,kind)
            self.reply(payload,mime='application/zip',extra={'Content-Disposition':'attachment; filename=Zhixu-'+kind+'.zip'})
        elif p.path == '/api/entries':
            date=q.get('date',[''])[0];dt.date.fromisoformat(date)
            with connect() as c:
                attachments=[dict(x) for x in c.execute('SELECT a.*, (SELECT count(*) FROM album_items i WHERE i.attachment_id=a.id) AS album_count FROM attachments a WHERE date=?',(date,))]
                entries=[journals.embed_legacy(dict(x),attachments) for x in c.execute('SELECT * FROM entries WHERE date=? ORDER BY created,id',(date,))]
                self.reply({'entries':entries,'attachments':attachments})
        elif p.path == '/api/state':
            date=q.get('date',[dt.date.today().isoformat()])[0];dt.date.fromisoformat(date)
            with connect() as c:
                self.reply({'settings':tasks.settings(c),'categories':[dict(x) for x in c.execute('SELECT * FROM todo_categories ORDER BY name')],
                    'notifications':tasks.notifications(c),'server_date':dt.date.today().isoformat(),
                    'todos':[dict(x) for x in c.execute('SELECT * FROM todos WHERE date=? ORDER BY created,id',(date,))],
                    'native_notifications':TRAY is not None})
        elif p.path == '/api/day':
            date = q.get('date', [''])[0]
            dt.date.fromisoformat(date)
            with connect() as c:
                row = c.execute('SELECT * FROM days WHERE date=?', (date,)).fetchone()
                self.reply({'day': dict(row) if row else {'date': date, 'title': '', 'body': ''},
                    'todos': [dict(x) for x in c.execute('SELECT * FROM todos WHERE date=? ORDER BY created,id', (date,))],
                    'attachments': [dict(x) for x in c.execute('SELECT a.*, (SELECT count(*) FROM album_items i WHERE i.attachment_id=a.id) AS album_count FROM attachments a WHERE date=? AND journal_visible=1 ORDER BY a.rowid', (date,))]})
        elif p.path == '/api/library':
            with connect() as c:
                self.reply({'categories': [dict(x) for x in c.execute('SELECT * FROM categories ORDER BY name')],
                    'albums': [dict(x) for x in c.execute('''SELECT a.*, (SELECT count(*) FROM album_items i WHERE i.album_id=a.id) AS count,
                    (SELECT attachment_id FROM album_items i WHERE i.album_id=a.id ORDER BY rowid LIMIT 1) AS cover,
                    (SELECT mime FROM attachments t JOIN album_items i ON t.id=i.attachment_id WHERE i.album_id=a.id ORDER BY i.rowid LIMIT 1) AS cover_mime
                    FROM albums a ORDER BY created DESC''')]})
        elif p.path == '/api/album':
            with connect() as c:
                id = q.get('id', [''])[0]; require_album(c, id)
                order={'time_desc':'t.imported_at DESC,t.rowid DESC','time_asc':'t.imported_at,t.rowid','size_desc':'t.size DESC,t.rowid DESC','size_asc':'t.size,t.rowid','name_asc':'t.name COLLATE NOCASE,t.rowid','name_desc':'t.name COLLATE NOCASE DESC,t.rowid DESC'}.get(q.get('sort',['time_desc'])[0],'t.imported_at DESC,t.rowid DESC')
                self.reply({'album': dict(c.execute('SELECT * FROM albums WHERE id=?', (id,)).fetchone()),
                    'items': [dict(x) for x in c.execute('''SELECT t.*,d.title AS journal_title,d.body AS journal_body
                    FROM attachments t JOIN album_items i ON i.attachment_id=t.id LEFT JOIN entries d ON d.id=t.entry_id
                    WHERE i.album_id=? ORDER BY '''+order, (id,))]})
        elif p.path == '/api/history':
            with connect() as c:
                self.reply([dict(x) for x in c.execute('''SELECT d.id,d.date,d.title,d.body,d.created,
                    (SELECT count(*) FROM todos t WHERE t.date=d.date) AS total,
                    (SELECT count(*) FROM todos t WHERE t.date=d.date AND t.done=1) AS done
                    FROM (SELECT id,date,title,body,created FROM entries UNION ALL
                    SELECT '',date,'','','' FROM todos WHERE date NOT IN (SELECT date FROM entries) GROUP BY date) d
                    ORDER BY d.date DESC,d.created DESC,d.id DESC''')])
        elif p.path == '/api/info':
            self.reply({'token': TOKEN, 'data': str(DATA), 'version': '1.35.0'})
        elif p.path == '/api/backup':
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
                memory = sqlite3.connect(':memory:')
                with connect() as c:
                    c.backup(memory)
                tmp = DATA / ('backup-' + uuid.uuid4().hex + '.db')
                try:
                    dest = sqlite3.connect(tmp)
                    memory.backup(dest)
                    dest.close()
                    memory.close()
                    z.write(tmp, 'data/journal.db')
                    for file in (DATA / 'attachments').iterdir():
                        if file.is_file(): z.write(file, 'data/attachments/' + file.name)
                finally:
                    tmp.unlink(missing_ok=True)
            self.reply(buffer.getvalue(), mime='application/zip', extra={'Content-Disposition': 'attachment; filename="Zhixu-backup-' + dt.date.today().isoformat() + '.zip"'})
        elif p.path.startswith('/files/'):
            id = p.path.split('/')[-1]
            with connect() as c:
                row = c.execute('SELECT * FROM attachments WHERE id=?', (id,)).fetchone()
            if not row: return self.reply({'error': '附件不存在'}, 404)
            file = DATA / 'attachments' / id
            # Stream large videos, including browser seek requests.
            size = file.stat().st_size
            start, end, status = 0, size - 1, 200
            if self.headers.get('Range', '').startswith('bytes='):
                spec = self.headers['Range'][6:].split(',')[0]
                a, b = spec.split('-', 1)
                start = int(a) if a else max(0, size - int(b))
                end = min(int(b), size - 1) if b and a else size - 1
                status = 206
            if start > end or start >= size:
                self.send_response(416); self.send_header('Content-Range', f'bytes */{size}'); self.end_headers(); return
            preview = row['mime'] in MEDIA_TYPES and not q.get('download')
            self.send_response(status)
            self.send_header('Content-Type', row['mime'] if preview else 'application/octet-stream')
            self.send_header('Content-Disposition', ('inline' if preview else 'attachment') + "; filename*=UTF-8''" + __import__('urllib.parse', fromlist=['quote']).quote(row['name']))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(end-start+1))
            if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            with file.open('rb') as f:
                f.seek(start)
                left = end-start+1
                while left > 0:
                    chunk = f.read(min(left, 1024*1024))
                    if not chunk: break
                    self.wfile.write(chunk); left -= len(chunk)
        elif p.path in ('/', '/app.js', '/style.css', '/gallery.css', '/v11.js', '/v11.css', '/v12.js', '/v12.css', '/zhixu.ico', '/v13.js', '/v13.css', '/v135.js', '/v135.css'):
            name = 'index.html' if p.path == '/' else p.path[1:]
            self.reply((ASSETS / name).read_bytes(), mime=('text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8' if name.endswith('.css') else 'image/x-icon' if name.endswith('.ico') else 'text/html; charset=utf-8'))
        else:
            self.reply({'error': '页面不存在'}, 404)

    def do_POST(self):
        with DATA_LOCK: self.post_locked()

    def post_locked(self):
        if self.headers.get('X-Zhixu-Token') != TOKEN:
            return self.reply({'error': '会话已失效，请刷新页面'}, 403)
        try:
            p = urlparse(self.path)
            q = parse_qs(p.query)
            if p.path == '/api/storage/pick':
                import tkinter as tk
                from tkinter import filedialog
                root=tk.Tk();root.withdraw();root.attributes('-topmost',True)
                try: selected=filedialog.askdirectory(title='选择知序数据文件夹',parent=root)
                finally:root.destroy()
                return self.reply({'path':selected})
            if p.path == '/api/restore':
                length=int(self.headers.get('Content-Length',0))
                if length<=0 or length>4*1024**3: raise ValueError('备份文件为空或超过 4 GB，可改用打开数据目录')
                target=storage.restore_zip(self.rfile.read(length),DATA.parent)
                switch_storage(target,'open')
                return self.reply({'ok':True,'path':str(DATA)})
            if p.path == '/api/storage/change':
                data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
                raw=data.get('path','').strip()
                if not raw or not Path(raw).is_absolute():raise ValueError('请输入完整的本地目录路径')
                switch_storage(Path(raw).resolve(),data.get('mode','open'))
                return self.reply({'ok':True,'path':str(DATA)})
            if p.path == '/api/upload':
                date = q.get('date', [''])[0]
                album = q.get('album', [''])[0]
                entry_id=q.get('entry',[''])[0]
                if date: dt.date.fromisoformat(date)
                if not date and not album: raise ValueError('请选择日志或相册')
                name = q['name'][0].replace('\\', '/').split('/')[-1][:240]
                mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
                with connect() as c:
                    if entry_id:
                        entry=c.execute('SELECT date FROM entries WHERE id=?',(entry_id,)).fetchone()
                        if not entry or entry['date']!=date:raise ValueError('来源日志不存在')
                    if album:
                        require_album(c, album)
                        if mime not in MEDIA_TYPES: raise ValueError('相册仅支持图片和 MP4 视频')
                size = int(self.headers.get('Content-Length', 0))
                if size <= 0 or size > 1024**3:
                    return self.reply({'error': '附件不能为空，单个附件最大 1 GB'}, 400)
                id = uuid.uuid4().hex
                file = DATA / 'attachments' / id
                try:
                    with file.open('wb') as f:
                        remaining = size
                        while remaining:
                            chunk = self.rfile.read(min(1024*1024, remaining))
                            if not chunk: raise ValueError('上传中断')
                            f.write(chunk); remaining -= len(chunk)
                    with connect() as c:
                        if album: require_album(c, album)
                        c.execute('INSERT INTO attachments(id,date,name,mime,size,journal_visible,imported_at) VALUES(?,?,?,?,?,?,?)', (id, date, name, mime, size, int(bool(date)),dt.datetime.now().isoformat(timespec='microseconds')))
                        if date:
                            if not entry_id:entry_id=journals.ensure(c,date)
                            c.execute('UPDATE attachments SET entry_id=? WHERE id=?',(entry_id,id))
                        if album: c.execute('INSERT INTO album_items VALUES(?,?)', (album, id))
                except Exception:
                    file.unlink(missing_ok=True); raise
                return self.reply({'ok': True, 'id': id})
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            with connect() as c:
                result = gallery_change(c, p.path, data)
                if result is None: result=tasks.category_change(c,p.path,data)
                if result is not None:
                    # Commit before sending the response: subsequent UI requests see the change.
                    c.commit()
                    return self.reply(result)
                if p.path == '/api/entry/save':
                    id=journals.save(c,data);c.commit();return self.reply({'ok':True,'id':id})
                elif p.path == '/api/entry/fold':
                    c.execute('UPDATE entries SET collapsed=? WHERE id=?',(int(bool(data['collapsed'])),data['id']))
                elif p.path == '/api/settings':
                    tasks.save_settings(c,data)
                elif p.path == '/api/notification/read':
                    c.execute('UPDATE reminder_events SET is_read=1 WHERE todo_id=? AND schedule_key=?',(data['todo_id'],data['schedule_key']))
                elif p.path == '/api/app/quit':
                    STOP.set()
                elif p.path == '/api/save':
                    dt.date.fromisoformat(data['date'])
                    existing=journals.primary(c,data['date']);journals.save(c,{**data,'id':existing['id'] if existing else ''})
                elif p.path == '/api/todo':
                    tasks.create(c,data)
                elif p.path == '/api/todo/update':
                    tasks.update(c,data)
                elif p.path == '/api/todo/delete':
                    c.execute('DELETE FROM reminder_events WHERE todo_id=?',(data['id'],))
                    c.execute('DELETE FROM todos WHERE id=?', (data['id'],))
                elif p.path == '/api/attachment/delete':
                    row = c.execute('SELECT id FROM attachments WHERE id=?', (data['id'],)).fetchone()
                    if row:
                        if c.execute('SELECT 1 FROM album_items WHERE attachment_id=?', (row['id'],)).fetchone():
                            c.execute('UPDATE attachments SET journal_visible=0 WHERE id=?', (row['id'],))
                            c.commit()
                            return self.reply({'ok': True})
                        # Keep a recoverable copy until the next manual cleanup.
                        trash = DATA / 'recycle'; trash.mkdir(exist_ok=True)
                        (DATA / 'attachments' / row['id']).replace(trash / row['id'])
                        c.execute('DELETE FROM attachments WHERE id=?', (data['id'],))
                else: return self.reply({'error': '接口不存在'}, 404)
            self.reply({'ok': True})
        except (ValueError, KeyError) as e:
            self.reply({'error': str(e) if isinstance(e, ValueError) else '内容格式有误，请检查后重试'}, 400)
        except sqlite3.IntegrityError:
            self.reply({'error': '名称已存在，请换一个名称'}, 409)
        except Exception:
            self.reply({'error': '保存失败，请检查磁盘空间并重试'}, 500)

def switch_storage(target,mode):
    global DATA,INSTANCE,ACTIVE_GUARD
    if mode not in ('open','move'):raise ValueError('未知的数据操作')
    if target==DATA:return
    previous=DATA
    storage.snapshot(previous,'before-data-switch')
    if mode=='move':storage.copy_to(previous,target)
    storage.validate(target)
    guard=storage.exclusive_target(target);guard.__enter__()
    try:
        DATA=target
        init()
        storage.remember(ROOT,target)
        if SERVICE_URL:(DATA/'runtime.json').write_text(json.dumps({'url':SERVICE_URL,'pid':os.getpid(),'version':'1.35.0'}),encoding='utf-8')
    except Exception:
        DATA=previous;guard.__exit__(None,None,None);raise
    if INSTANCE:INSTANCE.close();INSTANCE=None
    if ACTIVE_GUARD:ACTIVE_GUARD.__exit__(None,None,None)
    ACTIVE_GUARD=guard


def main():
    global TRAY,INSTANCE,SERVICE_URL
    if STARTUP_ERROR:raise RuntimeError(STARTUP_ERROR)
    INSTANCE=desktop.instance_guard(DATA)
    if INSTANCE is None: return
    init()
    storage.remember(ROOT,DATA)
    task_tick()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    SERVICE_URL=url
    (DATA / 'runtime.json').write_text(json.dumps({'url': url, 'pid': os.getpid(), 'version': '1.35.0'}), encoding='utf-8')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    headless='--serve' in sys.argv
    if not headless or '--native-test' in sys.argv:
        try: TRAY=desktop.start_tray(ASSETS,url,STOP)
        except Exception as e: (DATA/'tray-error.log').write_text(str(e),encoding='utf-8')
    threading.Thread(target=scheduler,daemon=True).start()
    if not headless: desktop.launch_window(url)
    elif sys.stdout is not None: print(url,flush=True)
    while not STOP.wait(2):
        with connect() as c: background=tasks.value(c,'background_enabled',True)
        if not headless and not background and time.time()-last_seen>120: break
    STOP.set()
    server.shutdown()
    server.server_close()
    if TRAY is not None: TRAY.stop()
    if INSTANCE:INSTANCE.close()
    if ACTIVE_GUARD:ACTIVE_GUARD.__exit__(None,None,None)

# Heartbeat extends service lifetime while the window is open.
original_get = Handler.get
def heartbeat_get(self):
    global last_seen
    last_seen = time.time()
    if urlparse(self.path).path == '/api/ping': self.reply({'ok': True})
    else: original_get(self)
Handler.get = heartbeat_get

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, '知序启动失败：'+str(e)+'\n请将程序放在可写入的文件夹中重试。', '知序', 16)

