import io,json,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import app,journals,releases,install_support
import test_v13 as fixtures
class Version15Tests(unittest.TestCase):
    setUp=fixtures.Version13Tests.setUp
    tearDown=fixtures.Version13Tests.tearDown
    api=fixtures.Version13Tests.api
    def test_delete_last_entry_never_resurrects_and_media_survives(self):
        day='2026-10-22';id=self.api('/api/entry/save',{'date':day,'title':'删除测试','body':'<p>保留为可撤销数据</p>'})['id']
        album=self.api('/api/album/save',{'name':'照片'})['id'];media=self.api('/api/upload?date='+day+'&entry='+id+'&album='+album+'&name=p.png',b'original-bytes')['id']
        self.api('/api/entry/delete',{'id':id});self.assertEqual(self.api('/api/entries?date='+day)['entries'],[])
        app.init();self.assertEqual(self.api('/api/entries?date='+day)['entries'],[])
        self.assertFalse(any(e['id']==id for e in self.api('/api/history')))
        item=self.api('/api/album?id='+album)['items'][0];self.assertEqual(item['id'],media);self.assertEqual(item['entry_id'],'');self.assertEqual((app.DATA/'attachments'/media).read_bytes(),b'original-bytes')
        backup=self.api('/api/backup');self.api('/api/restore',backup)
        self.api('/api/entry/restore',{'id':id});entry=self.api('/api/entries?date='+day)['entries'][0];self.assertEqual(entry['title'],'删除测试');self.assertEqual(self.api('/api/album?id='+album)['items'][0]['entry_id'],id)
    def test_delete_one_entry_preserves_other_entries_and_legacy_cache(self):
        day='2026-10-22';ids=[self.api('/api/entry/save',{'date':day,'title':str(i),'body':'<p>'+str(i)+'</p>'})['id'] for i in range(2)]
        self.api('/api/entry/delete',{'id':ids[0]});app.init()
        self.assertEqual([x['id'] for x in self.api('/api/entries?date='+day)['entries']],[ids[1]])
        self.assertEqual(self.api('/api/day?date='+day)['day']['title'],'1')
    def test_onboarding_once_and_shortcut_opt_in_endpoint(self):
        self.assertFalse(self.api('/api/welcome')['completed']);self.api('/api/welcome',{'completed':True});app.init();self.assertTrue(self.api('/api/welcome')['completed'])
        with patch.object(install_support,'create_shortcut',return_value=Path('desktop/知序.lnk')) as create:
            self.api('/api/desktop-shortcut',{});create.assert_called_once()
    def test_archive_creates_named_entry_without_replacing_oct22_user_log(self):
        id=self.api('/api/entry/save',{'date':'2026-10-22','title':'我的日常','body':'<p>私人内容</p>'})['id']
        with app.connect() as c:releases.append_updates(c);releases.append_updates(c)
        rows=self.api('/api/entries?date=2026-10-22')['entries'];old=next(e for e in rows if e['id']==id);self.assertEqual(old['title'],'我的日常');self.assertEqual(old['body'],'<p>私人内容</p>')
        archive=next(e for e in rows if e['title']=='知序 · 版本更新归档');self.assertEqual(archive['body'].count('<h3>知序版本归档 · 1.5</h3>'),1)
    def test_installer_keeps_data_and_can_skip_shortcut(self):
        package=self.root/'package.zip';target=self.root/'program';(target/'data').mkdir(parents=True);(target/'data/journal.db').write_bytes(b'personal');(target/'知序.exe').write_bytes(b'old')
        with zipfile.ZipFile(package,'w') as z:z.writestr('知序.exe',b'new');z.writestr('README.md','docs')
        with patch.object(install_support,'create_shortcut') as create:
            executable=install_support.install_package(package,target,False);create.assert_not_called();self.assertEqual(executable.read_bytes(),b'new');self.assertEqual((target/'data/journal.db').read_bytes(),b'personal')
            install_support.install_package(package,target,True);create.assert_called_once()
        with zipfile.ZipFile(package,'w') as z:z.writestr('知序.exe',b'new');z.writestr('data/journal.db',b'bad')
        with self.assertRaises(ValueError):install_support.install_package(package,target,False)
        self.assertEqual((target/'data/journal.db').read_bytes(),b'personal')
