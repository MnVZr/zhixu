"""Durable focus/break timer. All transitions run under the application's DB lock."""
import datetime as dt
import time
import tasks

DEFAULTS={'focus_minutes':25,'break_minutes':5,'rounds':1,'notify':True}
def migrate(c):
    c.execute('CREATE TABLE IF NOT EXISTS pomodoro_events(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,message TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS pomodoro_schedules(schedule_key TEXT PRIMARY KEY,result TEXT NOT NULL)')
def config(c):return {**DEFAULTS,**tasks.value(c,'pomodoro_config',{})}
def state(c):return tasks.value(c,'pomodoro_state',{'phase':'idle','paused':False,'round':0})
def status(c,now=None):
    now=time.time() if now is None else now;s=state(c)
    remaining=s.get('remaining',0) if s.get('paused') else max(0,s.get('deadline',now)-now)
    return {'config':config(c),'timer':s,'remaining':remaining,'server_now':now}
def event(c,title,message,now):
    if config(c)['notify']:c.execute('INSERT INTO pomodoro_events(title,message,created) VALUES(?,?,?)',(title,message,now))
def save_config(c,data):
    result=config(c)
    for key,max_value in [('focus_minutes',180),('break_minutes',60),('rounds',12)]:
        if key in data:
            value=data[key]
            if type(value) is not int or not 1<=value<=max_value:raise ValueError('专注 1–180 分钟，休息 1–60 分钟，轮数 1–12')
            result[key]=value
    if 'notify' in data:
        if type(data['notify']) is not bool:raise ValueError('通知选项须为开或关')
        result['notify']=data['notify']
    tasks.put(c,'pomodoro_config',result)
    if not result['notify']:c.execute('UPDATE pomodoro_events SET delivered=1')
def start(c,now,task=None):
    if state(c)['phase']!='idle':raise ValueError('已有番茄钟正在进行，请先结束当前计时')
    cfg=config(c);s={'phase':'focus','paused':False,'round':1,'focus_seconds':cfg['focus_minutes']*60,'break_seconds':cfg['break_minutes']*60,'rounds':cfg['rounds'],'deadline':now+cfg['focus_minutes']*60,'task_id':task['id'] if task else '', 'task_title':task['text'] if task else ''}
    if task:
        s['task_end']=dt.datetime.fromisoformat(task['date']+'T'+task['end_time']).timestamp()
        s['task_schedule']=task['date']+' '+task['start_time']+' '+task['end_time']
    tasks.put(c,'pomodoro_state',s);event(c,'专注开始',(s['task_title']+' · ' if task else '')+str(cfg['focus_minutes'])+' 分钟',now)
def command(c,data,now=None):
    now=time.time() if now is None else now;action=data.get('action');s=state(c)
    if action=='config':save_config(c,data)
    elif action=='start':start(c,now)
    elif action=='pause':
        if s['phase']=='idle' or s.get('paused'):raise ValueError('当前没有可暂停的计时')
        s['remaining']=max(0,s['deadline']-now);s['paused']=True;tasks.put(c,'pomodoro_state',s)
    elif action=='resume':
        if not s.get('paused'):raise ValueError('当前没有暂停的计时')
        if s.get('task_end',now+1)<=now:raise ValueError('待办时段已结束')
        s['deadline']=now+s['remaining'];s['paused']=False;tasks.put(c,'pomodoro_state',s)
    elif action=='stop':
        tasks.put(c,'pomodoro_state',{'phase':'idle','paused':False,'round':0});
        if s['phase']!='idle':event(c,'番茄钟已结束','本次计时已停止',now)
    else:raise ValueError('未知番茄钟操作')
    return status(c,now)
def tick(c,now=None):
    now=time.time() if now is None else now;local=dt.datetime.fromtimestamp(now);s=state(c)
    if s['phase']!='idle':
        task=c.execute('SELECT * FROM todos WHERE id=?',(s.get('task_id',''),)).fetchone() if s.get('task_id') else None
        changed=task and s.get('task_schedule')!=task['date']+' '+task['start_time']+' '+task['end_time']
        if s.get('task_end',now+1)<=now or (s.get('task_id') and (not task or task['done'] or not task['pomodoro'] or changed)):
            tasks.put(c,'pomodoro_state',{'phase':'idle','paused':False,'round':0});event(c,'番茄钟已结束','关联待办已完成、取消或到达时段结束时间',now)
        elif not s.get('paused') and now>=s['deadline']:
            if s['phase']=='focus':s['phase']='break';s['deadline']=now+s['break_seconds'];event(c,'专注结束 · 休息开始',str(s['break_seconds']//60)+' 分钟休息',now)
            elif s['round']<s['rounds']:s['phase']='focus';s['round']+=1;s['deadline']=now+s['focus_seconds'];event(c,'休息结束 · 专注开始','第 '+str(s['round'])+' 轮',now)
            else:s={'phase':'idle','paused':False,'round':0};event(c,'休息结束','番茄钟已完成',now)
            tasks.put(c,'pomodoro_state',s)
    for row in c.execute("SELECT * FROM todos WHERE date=? AND done=0 AND pomodoro=1 AND start_time!='' ORDER BY start_time,created,id",(local.date().isoformat(),)):
        begin=dt.datetime.fromisoformat(row['date']+'T'+row['start_time']).timestamp();end=dt.datetime.fromisoformat(row['date']+'T'+row['end_time']).timestamp();key=row['id']+' '+row['date']+' '+row['start_time']+' '+row['end_time']
        if not begin<=now<end or c.execute('SELECT 1 FROM pomodoro_schedules WHERE schedule_key=?',(key,)).fetchone():continue
        busy=state(c)['phase']!='idle';c.execute('INSERT INTO pomodoro_schedules VALUES(?,?)',(key,'busy' if busy else 'started'))
        if busy:event(c,'待办番茄钟未启动',row['text']+'：当前已有计时，保留正在进行的番茄钟',now)
        else:start(c,now,row)
