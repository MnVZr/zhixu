import json,io,zipfile,unittest,urllib.error
from pathlib import Path
import app,annotations,storage
import test_v13 as fixtures
class Version145Tests(unittest.TestCase):
    setUp=fixtures.Version13Tests.setUp
    tearDown=fixtures.Version13Tests.tearDown
    api=fixtures.Version13Tests.api
    def test_multiple_notes_rename_cover_source_and_backup(self):
        day='2026-10-21'
        entry=self.api('/api/entry/save',{'date':day,'title':'来源','body':'<p>原文</p>'})['id']
        album=self.api('/api/album/save',{'name':'相册'})['id']
        ids=[self.api('/api/upload?date='+day+'&entry='+entry+'&album='+album+'&name='+str(i)+'.png',b'image'+bytes([i]))['id'] for i in range(2)]
        notes=[{'id':'one','text':'图注甲','x':.2,'y':.4,'size':24,'color':'#ffffff','background':'#123456','opacity':.5},{'id':'two','text':'图注乙','x':.8,'y':.7,'size':16,'color':'#000000','background':'#ffffff','opacity':1}]
        self.api('/api/media/update',{'id':ids[1],'name':'改名','captions':notes})
        self.api('/api/album/cover',{'album_id':album,'attachment_id':ids[1]})
        item=next(x for x in self.api('/api/album?id='+album)['items'] if x['id']==ids[1]);self.assertEqual(item['name'],'改名.png');self.assertEqual(json.loads(item['captions']),notes);self.assertEqual(item['entry_id'],entry);self.assertEqual(item['journal_title'],'来源');self.assertTrue(item['imported_at'])
        self.assertEqual(self.api('/api/library')['albums'][0]['cover'],ids[1])
        self.api('/api/day-context',{'date':day,'mood':'开心','weather':'晴'})
        self.api('/api/ui-state',{'position':{'x':.25,'y':.7}})
        self.api('/api/settings',{'show_mood':True,'show_weather':True})
        backup=self.api('/api/backup');restored=self.api('/api/restore',backup)['path']
        self.assertNotEqual(Path(restored),self.root/'original')
        self.assertEqual(self.api('/api/day-context?date='+day)['mood'],'开心');self.assertEqual(self.api('/api/ui-state')['position'],{'x':.25,'y':.7});self.assertTrue(self.api('/api/state')['settings']['show_weather'])
        self.assertEqual(json.loads(next(x for x in self.api('/api/album?id='+album)['items'] if x['id']==ids[1])['captions']),notes)
        z=zipfile.ZipFile(io.BytesIO(self.api('/api/export?kind=albums')))
        manifest=next(json.loads(z.read(n)) for n in z.namelist() if n.endswith('.json'));self.assertIn('图注乙',json.dumps(manifest,ensure_ascii=False))
        self.api('/api/media/update',{'id':ids[1],'captions':[]});app.init();self.assertEqual(json.loads(next(x for x in self.api('/api/album?id='+album)['items'] if x['id']==ids[1])['captions']),[])
        self.assertTrue((self.root/'original'/'journal.db').exists())
    def test_legacy_single_caption_migration_and_idempotence(self):
        id=self.api('/api/upload?date=2026-10-21&name=old.png',b'old')['id']
        with app.connect() as c:
            c.execute('ALTER TABLE attachments DROP COLUMN captions')
            c.execute('UPDATE attachments SET annotation=?,caption_style=? WHERE id=?',('旧图注',json.dumps({'x':.3,'size':28}),id))
            annotations.migrate(c);first=c.execute('SELECT captions FROM attachments WHERE id=?',(id,)).fetchone()[0];annotations.migrate(c)
            self.assertEqual(c.execute('SELECT captions FROM attachments WHERE id=?',(id,)).fetchone()[0],first)
            note=json.loads(first)[0];self.assertEqual(note['text'],'旧图注');self.assertEqual(note['x'],.3);self.assertEqual(note['size'],28)
    def test_validation_rejects_bad_notes_positions_and_unrelated_cover(self):
        album=self.api('/api/album/save',{'name':'相册'})['id'];id=self.api('/api/upload?date=2026-10-21&name=a.png',b'a')['id']
        for path,payload in [('/api/media/update',{'id':id,'captions':[{'text':'bad','x':float('nan')}]}),('/api/album/cover',{'album_id':album,'attachment_id':id}),('/api/day-context',{'date':'2026-10-21','mood':'not-a-mood'}),('/api/ui-state',{'position':{'x':2,'y':0}})]:
            with self.assertRaises(urllib.error.HTTPError) as e:self.api(path,payload)
            e.exception.close()
