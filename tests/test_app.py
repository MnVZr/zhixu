import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import zipfile
import io
import sqlite3
import datetime as dt
import releases

spec = importlib.util.spec_from_file_location('zhixu', Path(__file__).parents[1] / 'app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class JournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        app.DATA = Path(cls.tmp.name)
        app.init()
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        h = {'X-Zhixu-Token': app.TOKEN, **(headers or {})}
        body = None if data is None else data if isinstance(data, bytes) else json.dumps(data).encode()
        return urllib.request.urlopen(urllib.request.Request(self.url+path, body, h))

    def test_full_workflow(self):
        day = '2026-10-20'
        payload = {'date':day, 'title':'科研日志：你好', 'body':'<h3>实验结果</h3><p>已完成。</p>'}
        self.request('/api/save', payload).close()
        self.request('/api/todo', {'date':day,'text':'阅读论文'}).close()
        result = json.load(self.request('/api/day?date='+day))
        self.assertEqual(result['day']['body'],payload['body'])
        self.assertEqual(result['day']['title'],payload['title'])
        todo = result['todos'][0]['id']
        self.request('/api/todo/update', {'id':todo,'done':True}).close()
        self.request('/api/todo/update', {'id':todo,'text':'阅读两篇论文'}).close()
        self.request('/api/upload?date='+day+'&name=test.mp4', b'0123456789').close()
        result = json.load(self.request('/api/day?date='+day))
        self.assertEqual(result['todos'][0]['done'],1)
        self.assertEqual(result['todos'][0]['text'],'阅读两篇论文')
        attachment = result['attachments'][0]
        r = self.request('/files/'+attachment['id'], headers={'Range':'bytes=2-5'})
        self.assertEqual(r.status,206)
        self.assertEqual(r.read(),b'2345')
        other = json.load(self.request('/api/day?date=2026-10-19'))
        self.assertEqual(other['day']['body'],'')
        self.assertFalse(other['todos'])
        # Reopening a fresh database connection preserves all saved content.
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT title FROM days WHERE date=?',(day,)).fetchone()[0],payload['title'])
        archive=zipfile.ZipFile(io.BytesIO(self.request('/api/backup').read()))
        self.assertIn('data/journal.db',archive.namelist())
        self.assertEqual(archive.read('data/attachments/'+attachment['id']),b'0123456789')
        self.request('/api/attachment/delete', {'id':attachment['id']}).close()
        self.assertTrue((app.DATA/'recycle'/attachment['id']).exists())
        self.request('/api/todo/delete', {'id':todo}).close()
        self.assertFalse(json.load(self.request('/api/day?date='+day))['todos'])

    def test_rejects_untrusted_write(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request('/api/save', {'date':'2026-10-20','title':'x','body':'x'}, {'X-Zhixu-Token':'wrong'})
        self.assertEqual(e.exception.code,403)
        e.exception.close()

    def test_validates_date(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request('/api/save', {'date':'invalid','title':'x','body':'x'})
        self.assertEqual(e.exception.code,400)
        e.exception.close()

    def test_album_lifecycle_and_log_link(self):
        day='2026-10-21'
        self.request('/api/save', {'date':day,'title':'荧光实验','body':'<p>第一次实验结果</p>'}).close()
        self.request('/api/category/save', {'name':'科研'}).close()
        category=json.load(self.request('/api/library'))['categories'][0]
        album=json.load(self.request('/api/album/save', {'name':'实验图像','category_id':category['id']}))['id']
        second=json.load(self.request('/api/album/save', {'name':'待复核'}))['id']
        media=json.load(self.request('/api/upload?date='+day+'&name=sample.png', b'PNG-fixture'))['id']
        for a in (album, album, second):
            self.request('/api/album/add', {'album_id':a,'attachment_ids':[media]}).close()
        result=json.load(self.request('/api/album?id='+album))
        self.assertEqual(len(result['items']),1)  # Repeated add is idempotent.
        self.assertEqual(result['items'][0]['journal_title'],'荧光实验')
        self.request('/api/save', {'date':day,'title':'实验更新','body':'<p>重新统计后更新结果</p>'}).close()
        self.assertEqual(json.load(self.request('/api/album?id='+album))['items'][0]['journal_title'],'实验更新')
        self.request('/api/attachment/delete', {'id':media}).close()
        self.assertEqual(json.load(self.request('/api/day?date='+day))['attachments'],[])
        self.assertEqual(self.request('/files/'+media).read(),b'PNG-fixture')
        self.assertEqual(json.load(self.request('/api/album?id='+album))['items'][0]['date'],day)
        direct=json.load(self.request('/api/upload?album='+album+'&name=direct.jpg', b'JPEG-fixture'))['id']
        direct_item=next(x for x in json.load(self.request('/api/album?id='+album))['items'] if x['id']==direct)
        self.assertEqual(direct_item['date'],'')
        self.assertIsNone(direct_item['journal_title'])
        self.request('/api/album/save', {'id':album,'name':'观察记录','category_id':category['id']}).close()
        self.request('/api/category/save', {'id':category['id'],'name':'研究'}).close()
        archive=zipfile.ZipFile(io.BytesIO(self.request('/api/backup').read()))
        dbpath=app.DATA/'restored.db'; dbpath.write_bytes(archive.read('data/journal.db'))
        restored=sqlite3.connect(dbpath)
        try:
            self.assertEqual(restored.execute('SELECT count(*) FROM album_items WHERE album_id=?',(album,)).fetchone()[0],2)
            self.assertEqual(restored.execute('SELECT name FROM categories WHERE id=?',(category['id'],)).fetchone()[0],'研究')
        finally: restored.close()
        self.assertEqual(archive.read('data/attachments/'+direct),b'JPEG-fixture')
        self.request('/api/category/delete', {'id':category['id']}).close()
        self.assertEqual(json.load(self.request('/api/album?id='+album))['album']['category_id'],'')
        self.request('/api/album/remove', {'album_id':album,'attachment_id':media}).close()
        self.assertEqual(len(json.load(self.request('/api/album?id='+second))['items']),1)
        self.request('/api/album/delete', {'id':album}).close()
        self.assertNotIn(album,[x['id'] for x in json.load(self.request('/api/library'))['albums']])

    def test_invalid_album_and_nonmedia_rejected(self):
        album=json.load(self.request('/api/album/save', {'name':'测试相册'}))['id']
        for path,body in [('/api/upload?album='+album+'&name=document.pdf',b'PDF'),('/api/album/add',{'album_id':'missing','attachment_ids':['unknown']})]:
            with self.assertRaises(urllib.error.HTTPError) as e: self.request(path,body)
            self.assertEqual(e.exception.code,400);e.exception.close()
        self.assertFalse(json.load(self.request('/api/album?id='+album))['items'])

    def test_import_into_journal_and_album_together(self):
        day='2026-10-22'
        album=json.load(self.request('/api/album/save', {'name':'同步导入'}))['id']
        id=json.load(self.request('/api/upload?date='+day+'&album='+album+'&name=clip.mp4',b'video-fixture'))['id']
        self.assertEqual(json.load(self.request('/api/day?date='+day))['attachments'][0]['id'],id)
        result=json.load(self.request('/api/album?id='+album))['items'][0]
        self.assertEqual(result['date'],day)
        self.assertEqual(result['id'],id)
        self.request('/api/album/delete',{'id':album}).close()
        self.assertEqual(json.load(self.request('/api/day?date='+day))['attachments'][0]['id'],id)

    def test_upgrade_preserves_demo_database(self):
        old=app.DATA
        with tempfile.TemporaryDirectory() as directory:
            app.DATA=Path(directory)
            try:
                db=sqlite3.connect(app.DATA/'journal.db')
                db.executescript("CREATE TABLE attachments(id TEXT PRIMARY KEY,date TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,size INTEGER NOT NULL); CREATE TABLE days(date TEXT PRIMARY KEY,title TEXT NOT NULL DEFAULT '',body TEXT NOT NULL DEFAULT '',updated TEXT);")
                db.execute('INSERT INTO days VALUES(?,?,?,?)',('2026-10-01','旧日志','<b>旧内容</b>',''))
                db.execute('INSERT INTO attachments VALUES(?,?,?,?,?)',('old-image','2026-10-01','旧图片.png','image/png',10))
                db.commit();db.close()
                app.init();app.init()
                with app.connect() as c:
                    self.assertEqual(c.execute('SELECT body FROM days').fetchone()[0],'<b>旧内容</b>')
                    self.assertEqual(c.execute('SELECT journal_visible FROM attachments').fetchone()[0],1)
                    self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],3)
                self.assertEqual(len(list((app.DATA/'upgrade-backups').glob('*.db'))),1)
            finally: app.DATA=old

    def test_media_metadata_sort_and_shared_reference(self):
        day='2026-11-01'
        album=json.load(self.request('/api/album/save',{'name':'元信息测试'}))['id']
        ids=[]
        for name,body in [('b.jpg',b'1234'),('a.jpg',b'123456789'),('c.jpg',b'12')]:
            ids.append(json.load(self.request('/api/upload?date='+day+'&album='+album+'&name='+name,body))['id'])
        with app.connect() as c:
            for i,id in enumerate(ids): c.execute('UPDATE attachments SET imported_at=? WHERE id=?',(f'2026-10-{20+i}T10:00:00',id))
        self.request('/api/media/update',{'id':ids[0],'name':'观察.jpg','annotation':'第一组：信号增强。'}).close()
        result=json.load(self.request('/api/album?id='+album+'&sort=size_desc'))['items']
        self.assertEqual([x['id'] for x in result],[ids[1],ids[0],ids[2]])
        self.assertEqual(result[1]['annotation'],'第一组：信号增强。')
        self.assertEqual(result[1]['imported_at'],'2026-10-20T10:00:00')
        self.assertEqual(json.load(self.request('/api/album?id='+album+'&sort=time_desc'))['items'][0]['id'],ids[2])
        names=[x['name'] for x in json.load(self.request('/api/album?id='+album+'&sort=name_asc'))['items']]
        self.assertEqual(names[0],'a.jpg')
        self.assertEqual(json.load(self.request('/api/day?date='+day))['attachments'][0]['name'],'观察.jpg')
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/api/media/update',{'id':ids[0],'name':'wrong.mp4'})
        self.assertEqual(e.exception.code,400);e.exception.close()

    def test_todo_metadata_api(self):
        self.request('/api/todo/category/save',{'name':'项目A','color':'#5986c1'}).close()
        state=json.load(self.request('/api/state?date=2026-11-02'))
        category=next(x for x in state['categories'] if x['name']=='项目A')['id']
        self.request('/api/todo',{'date':'2026-11-02','text':'定时实验','start_time':'09:00','end_time':'10:00','remind':True,'priority':'urgent','category_id':category}).close()
        row=json.load(self.request('/api/day?date=2026-11-02'))['todos'][0]
        self.assertEqual((row['start_time'],row['priority'],row['category_id'],row['remind']),('09:00','urgent',category,1))
        self.request('/api/todo/update',{'id':row['id'],'text':'定时实验（修改）'}).close()
        updated=json.load(self.request('/api/day?date=2026-11-02'))['todos'][0]
        self.assertEqual(updated['end_time'],'10:00')
        self.request('/api/todo/category/delete',{'id':category}).close()
        self.assertEqual(json.load(self.request('/api/day?date=2026-11-02'))['todos'][0]['category_id'],'')
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/api/todo',{'date':'2026-11-02','text':'不合法时段','start_time':'10:00','end_time':'09:00'})
        self.assertEqual(e.exception.code,400);e.exception.close()

class TaskEngineTests(unittest.TestCase):
    def setUp(self):
        self.original=app.DATA;self.tmp=tempfile.TemporaryDirectory();app.DATA=Path(self.tmp.name);app.init()
    def tearDown(self):
        app.DATA=self.original;self.tmp.cleanup()
    def test_v12_preferences_and_custom_colors_survive_restart(self):
        expected={'font_size':'larger','task_sort':'time','default_priority':'urgent','hide_completed':True,'show_stats':False,'show_inspiration':True}
        with app.connect() as c:
            app.tasks.save_settings(c,expected)
            app.tasks.category_change(c,'/api/todo/category/save',{'name':'自定义','color':'#123abc'})
            for bad in [{'font_size':'huge'},{'hide_completed':'true'},{'task_sort':'invalid'}]:
                with self.assertRaises(ValueError):app.tasks.save_settings(c,bad)
            for bad in ['red','#123','url(x)',None]:
                with self.assertRaises(ValueError):app.tasks.category_change(c,'/api/todo/category/save',{'name':'错误','color':bad})
        app.init()
        with app.connect() as c:
            for key,value in expected.items():self.assertEqual(app.tasks.settings(c)[key],value)
            self.assertEqual(c.execute("SELECT color FROM todo_categories WHERE name='自定义'").fetchone()[0],'#123abc')
    def test_midnight_rollover_is_durable_and_idempotent(self):
        with app.connect() as c:
            category=c.execute('SELECT id FROM todo_categories LIMIT 1').fetchone()[0]
            id=app.tasks.create(c,{'date':'2026-10-21','text':'未完成','priority':'high','category_id':category,'start_time':'10:00','end_time':'11:00','remind':True})
            completed=app.tasks.create(c,{'date':'2026-10-21','text':'已完成'})
            app.tasks.update(c,{'id':completed,'done':True})
            app.tasks.save_settings(c,{'rollover_enabled':True},dt.datetime(2026,10,21,23,59))
        app.task_tick(dt.datetime(2026,10,21,23,59,59))
        with app.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM todos WHERE date='2026-10-22'").fetchone()[0],0)
        app.task_tick(dt.datetime(2026,10,22,0,0,0));app.task_tick(dt.datetime(2026,10,22,0,0,5))
        with app.connect() as c:
            rows=list(c.execute("SELECT * FROM todos WHERE date='2026-10-22'"));self.assertEqual(len(rows),1)
            self.assertEqual((rows[0]['root_id'],rows[0]['priority'],rows[0]['category_id'],rows[0]['start_time'],rows[0]['remind']),(id,'high',category,'10:00',1))
        # Simulate restart after two missed midnights.
        app.init();app.task_tick(dt.datetime(2026,10,24,8))
        with app.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM todos WHERE date='2026-10-24'").fetchone()[0],1)
            app.tasks.save_settings(c,{'rollover_enabled':False},dt.datetime(2026,10,24,8))
        app.task_tick(dt.datetime(2026,10,25,0))
        with app.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM todos WHERE date='2026-10-25'").fetchone()[0],0)
    def test_reminder_only_once_and_only_within_period(self):
        with app.connect() as c:
            id=app.tasks.create(c,{'date':'2026-10-21','text':'提醒实验','start_time':'10:00','end_time':'11:00','remind':True})
            app.tasks.create(c,{'date':'2026-10-21','text':'不提醒','start_time':'10:00','end_time':'11:00','remind':False})
            app.tasks.create(c,{'date':'2026-10-21','text':'无时段'})
            done=app.tasks.create(c,{'date':'2026-10-21','text':'已完成不提醒','start_time':'10:00','end_time':'11:00','remind':True})
            app.tasks.update(c,{'id':done,'done':True})
        app.task_tick(dt.datetime(2026,10,21,9,59))
        with app.connect() as c:self.assertEqual(app.tasks.notifications(c),[])
        app.task_tick(dt.datetime(2026,10,21,10));app.task_tick(dt.datetime(2026,10,21,10,5))
        with app.connect() as c:
            items=app.tasks.notifications(c);self.assertEqual(len(items),1);self.assertEqual(items[0]['todo_id'],id)
            app.tasks.update(c,{'id':id,'done':True})
            self.assertEqual(app.tasks.notifications(c),[])
        with app.connect() as c:app.tasks.create(c,{'date':'2026-10-21','text':'错过时段','start_time':'09:00','end_time':'09:30','remind':True})
        app.task_tick(dt.datetime(2026,10,21,11))
        with app.connect() as c:self.assertEqual(app.tasks.notifications(c),[])
    def test_archive_keeps_existing_diary_and_does_not_duplicate(self):
        with app.connect() as c:
            c.execute('INSERT INTO days(date,title,body) VALUES(?,?,?)',('2026-10-21','我的日志','<p>保留原文</p>'))
            releases.append_updates(c);releases.append_updates(c)
            row=c.execute("SELECT * FROM days WHERE date='2026-10-21'").fetchone()
            self.assertEqual(row['title'],'我的日志');self.assertTrue(row['body'].startswith('<p>保留原文</p>'))
            self.assertEqual(row['body'].count('知序版本归档 · 1.0'),1);self.assertEqual(row['body'].count('知序版本归档 · 1.1'),1)
            self.assertIn('Demo',c.execute("SELECT body FROM days WHERE date='2026-10-20'").fetchone()[0])

if __name__ == '__main__':
    unittest.main(verbosity=2)
