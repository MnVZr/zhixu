import datetime as dt
import json
import unittest
import pomodoro
import test_v13 as _fixtures

class Version14Tests(unittest.TestCase):
    setUp=_fixtures.Version13Tests.setUp
    tearDown=_fixtures.Version13Tests.tearDown
    api=_fixtures.Version13Tests.api
    def test_pomodoro_lifecycle_pause_restart_and_notifications(self):
        now=dt.datetime(2026,10,21,9).timestamp()
        with self.app_connection() as c:
            pomodoro.command(c,{'action':'config','focus_minutes':1,'break_minutes':1,'rounds':2},now)
            pomodoro.command(c,{'action':'start'},now);self.assertEqual(pomodoro.state(c)['phase'],'focus')
            pomodoro.command(c,{'action':'pause'},now+10);pomodoro.tick(c,now+600);self.assertEqual(pomodoro.state(c)['remaining'],50)
            pomodoro.command(c,{'action':'resume'},now+600);pomodoro.tick(c,now+650);self.assertEqual(pomodoro.state(c)['phase'],'break')
            pomodoro.tick(c,now+710);self.assertEqual(pomodoro.state(c)['phase'],'focus');self.assertEqual(pomodoro.state(c)['round'],2)
            pomodoro.tick(c,now+770);pomodoro.tick(c,now+830);self.assertEqual(pomodoro.state(c)['phase'],'idle')
            titles=[x[0] for x in c.execute('SELECT title FROM pomodoro_events')];self.assertIn('专注开始',titles);self.assertIn('休息结束',titles)
    def app_connection(self):
        import app
        return app.connect()
    def test_timer_survives_reinitialization_and_native_dispatch(self):
        import app,time,threading
        from unittest.mock import patch
        now=time.time()
        with app.connect() as c:
            app.tasks.save_settings(c,{'reminder_sound':False})
            pomodoro.command(c,{'action':'start'},now)
        app.init()
        with app.connect() as c:self.assertEqual(pomodoro.state(c)['deadline'],now+1500)
        stop=threading.Event();notices=[]
        class Tray:
            def notify(self,message,title):notices.append((title,message));stop.set()
        with patch.object(app,'TRAY',Tray()),patch.object(app,'STOP',stop):app.scheduler()
        self.assertEqual(notices[0][0],'专注开始')
        with app.connect() as c:self.assertEqual(c.execute('SELECT delivered FROM pomodoro_events LIMIT 1').fetchone()[0],1)
    def test_scheduled_pomodoro_once_end_boundaries_and_conflict(self):
        import app
        now=dt.datetime(2026,10,21,10).timestamp()
        with app.connect() as c:
            id=app.tasks.create(c,{'date':'2026-10-21','text':'任务番茄','start_time':'10:00','end_time':'10:02','pomodoro':True})
            pomodoro.tick(c,now-1);self.assertEqual(pomodoro.state(c)['phase'],'idle')
            pomodoro.tick(c,now);self.assertEqual(pomodoro.state(c)['task_id'],id)
            pomodoro.command(c,{'action':'stop'},now+10);pomodoro.tick(c,now+11);self.assertEqual(pomodoro.state(c)['phase'],'idle')
            app.tasks.update(c,{'id':id,'start_time':'10:01','end_time':'10:03'})
            pomodoro.command(c,{'action':'start'},now+20);pomodoro.tick(c,now+60);self.assertEqual(pomodoro.state(c)['task_id'],'')
            pomodoro.command(c,{'action':'stop'},now+70)
            app.tasks.update(c,{'id':id,'start_time':'10:02','end_time':'10:04'})
            pomodoro.tick(c,now+120);self.assertEqual(pomodoro.state(c)['task_id'],id)
            pomodoro.tick(c,now+240);self.assertEqual(pomodoro.state(c)['phase'],'idle')
            pomodoro.tick(c,now+241);self.assertEqual(pomodoro.state(c)['phase'],'idle')
    def test_caption_style_validation_export_and_old_fields(self):
        album=self.api('/api/album/save',{'name':'样式'})['id']
        id=self.api('/api/upload?album='+album+'&name=a.png',b'image')['id']
        style={'x':.1,'y':.7,'size':28,'color':'#123456','background':'#abcdef','opacity':.5}
        self.api('/api/media/update',{'id':id,'annotation':'任意位置图注','caption_style':style})
        item=self.api('/api/album?id='+album)['items'][0];self.assertEqual(json.loads(item['caption_style']),style)
        self.api('/api/media/update',{'id':id,'name':'新名字'})
        self.assertEqual(json.loads(self.api('/api/album?id='+album)['items'][0]['caption_style']),style)
        import urllib.error
        for bad in [{'x':2},{'size':0},{'color':'url(x)'},{'opacity':float('nan')}]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.api('/api/media/update',{'id':id,'caption_style':bad})
            error.exception.close()
    def test_timer_api_config_validation_and_task_requires_time(self):
        import urllib.error
        self.api('/api/pomodoro',{'action':'config','focus_minutes':30,'break_minutes':8,'rounds':3,'notify':False})
        self.assertEqual(self.api('/api/pomodoro')['config']['focus_minutes'],30)
        for data in [{'action':'config','focus_minutes':0},{'action':'config','rounds':99},{'action':'config','notify':'yes'}]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.api('/api/pomodoro',data)
            error.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as error:self.api('/api/todo',{'date':'2026-10-21','text':'无时段','pomodoro':True})
        error.exception.close()
