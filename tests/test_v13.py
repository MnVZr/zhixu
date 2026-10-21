import datetime as dt
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request as request
import urllib.error
import zipfile
import app
import storage
import journals

class Version13Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.previous=app.DATA;app.DATA=self.root/'original';app.init()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);self.url='http://127.0.0.1:'+str(self.server.server_port)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.config=patch.object(storage,'config_path',return_value=self.root/'storage.json');self.config.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close()
        if app.ACTIVE_GUARD:app.ACTIVE_GUARD.__exit__(None,None,None);app.ACTIVE_GUARD=None
        app.DATA=self.previous;self.config.stop();self.tmp.cleanup()
    def api(self,path,data=None):
        body=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None
        with request.urlopen(request.Request(self.url+path,body,{'X-Zhixu-Token':app.TOKEN})) as response:
            value=response.read();return json.loads(value) if 'json' in response.headers['Content-Type'] else value
    def test_multi_entry_inline_media_and_export(self):
        one=self.api('/api/entry/save',{'date':'2026-10-21','title':'第一篇','body':'<p>早晨</p>'})['id']
        two=self.api('/api/entry/save',{'date':'2026-10-21','title':'第二篇','body':'<p>晚上</p>'})['id']
        media=self.api('/api/upload?date=2026-10-21&entry='+two+'&name=picture.png',b'test-picture')['id']
        body=f'<p>观察之前</p><figure data-media-id="{media}"><img src="/files/{media}" onerror="alert(1)"><figcaption>图注内容</figcaption></figure><p>观察之后</p><script>bad()</script>'
        self.api('/api/entry/save',{'id':two,'date':'2026-10-21','title':'第二篇','body':body})
        self.api('/api/entry/fold',{'id':one,'collapsed':True})
        rows=self.api('/api/entries?date=2026-10-21')['entries'];self.assertEqual(len(rows),2);self.assertEqual(rows[0]['collapsed'],1)
        self.assertIn('figcaption',rows[1]['body']);self.assertNotIn('onerror',rows[1]['body']);self.assertNotIn('bad()',rows[1]['body'])
        album=self.api('/api/album/save',{'name':'测试相册'})['id'];self.api('/api/album/add',{'album_id':album,'attachment_ids':[media]})
        item=self.api('/api/album?id='+album)['items'][0];self.assertEqual(item['entry_id'],two);self.assertEqual(item['journal_title'],'第二篇')
        self.api('/api/media/update',{'id':media,'name':'重命名无需后缀','annotation':'共享图注'})
        self.assertEqual(self.api('/api/album?id='+album)['items'][0]['name'],'重命名无需后缀.png')
        self.assertIn('共享图注',self.api('/api/entries?date=2026-10-21')['entries'][1]['body'])
        with zipfile.ZipFile(io.BytesIO(self.api('/api/export?kind=journals'))) as z:
            self.assertEqual(len(z.namelist()),2);self.assertTrue(any('观察之后' in z.read(n).decode('utf-8-sig') for n in z.namelist()))
        with zipfile.ZipFile(io.BytesIO(self.api('/api/export?kind=albums'))) as z:
            self.assertTrue(any(n.endswith('.png') for n in z.namelist()));self.assertIn('共享图注',z.read('相册信息.json').decode())
        self.api('/api/entry/save',{'id':two,'date':'2026-10-21','title':'第二篇','body':'<p>移出正文后保留文件</p>'})
        self.assertNotIn('<figure',self.api('/api/entries?date=2026-10-21')['entries'][1]['body'])
        self.assertEqual(len(self.api('/api/album?id='+album)['items']),1)
    def test_migrate_switch_restore_preserve_original(self):
        self.api('/api/entry/save',{'date':'2026-10-21','title':'需要保留','body':'<p>我的原文</p>'})
        self.api('/api/settings',{'theme':'#5986c1'})
        original=app.DATA;target=self.root/'new-data'
        self.api('/api/storage/change',{'mode':'move','path':str(target)})
        self.assertEqual(app.DATA,target);self.assertTrue((original/'journal.db').is_file())
        self.assertEqual(self.api('/api/entries?date=2026-10-21')['entries'][0]['title'],'需要保留')
        with self.assertRaises(urllib.error.HTTPError):self.api('/api/storage/change',{'mode':'move','path':str(original)})
        backup=self.api('/api/backup');self.api('/api/restore',backup)
        self.assertNotEqual(app.DATA,target);self.assertTrue((target/'journal.db').is_file());self.assertTrue((original/'journal.db').is_file())
        self.assertEqual(self.api('/api/state?date=2026-10-21')['settings']['theme'],'#5986c1')
        self.api('/api/storage/change',{'mode':'open','path':str(original)})
        self.assertEqual(app.DATA,original);self.assertIn('我的原文',self.api('/api/entries?date=2026-10-21')['entries'][0]['body'])
    def test_legacy_media_migration_and_unsafe_backup_rejection(self):
        legacy=self.root/'old-data';legacy.mkdir();(legacy/'attachments').mkdir();id='a'*32;(legacy/'attachments'/id).write_bytes(b'old-picture')
        from contextlib import closing
        with closing(sqlite3.connect(legacy/'journal.db')) as c:
            c.executescript("CREATE TABLE days(date TEXT PRIMARY KEY,title TEXT NOT NULL DEFAULT '',body TEXT NOT NULL DEFAULT '',updated TEXT);CREATE TABLE todos(id TEXT PRIMARY KEY,date TEXT,text TEXT,done INTEGER,created TEXT);CREATE TABLE attachments(id TEXT PRIMARY KEY,date TEXT,name TEXT,mime TEXT,size INTEGER);")
            c.execute('INSERT INTO days VALUES(?,?,?,?)',('2026-10-20','旧标题','<p>旧内容</p>',None));c.execute('INSERT INTO attachments VALUES(?,?,?,?,?)',(id,'2026-10-20','old.png','image/png',11));c.commit()
        self.api('/api/storage/change',{'mode':'open','path':str(legacy)})
        row=self.api('/api/entries?date=2026-10-20')['entries'][0];self.assertEqual(row['title'],'旧标题');self.assertIn(id,row['body']);self.assertIn('旧内容',row['body'])
        self.assertTrue(list((legacy/'upgrade-backups').glob('before-1.3-*.db')))
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('data/../../outside.txt','no')
        with self.assertRaises(urllib.error.HTTPError):self.api('/api/restore',buffer.getvalue())
        self.assertEqual(app.DATA,legacy);self.assertFalse((self.root/'outside.txt').exists())

if __name__=='__main__':unittest.main()
