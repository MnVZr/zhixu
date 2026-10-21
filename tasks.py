"""Task metadata, durable midnight rollover and reminder records (local time)."""
import datetime as dt
import json
import re
import uuid

COLORS = ('#4c8c78', '#5986c1', '#c4914d', '#a477bd', '#c46e78', '#7b8a92')
DEFAULTS = {'rollover_enabled': False, 'background_enabled': True, 'reminder_sound': True, 'font_size': 'standard', 'theme': '#2f6859', 'task_sort': 'priority', 'default_priority': 'normal', 'hide_completed': False, 'show_mood': False, 'show_weather': False, 'show_stats': True, 'show_inspiration': False}

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS todo_categories(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,color TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reminder_events(todo_id TEXT NOT NULL,schedule_key TEXT NOT NULL,created_at TEXT NOT NULL,is_read INTEGER NOT NULL DEFAULT 0,delivered INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(todo_id,schedule_key));
    ''')
    existing = {r['name'] for r in c.execute('PRAGMA table_info(todos)')}
    for name, definition in {'start_time':"TEXT NOT NULL DEFAULT ''",'end_time':"TEXT NOT NULL DEFAULT ''",'remind':'INTEGER NOT NULL DEFAULT 0','priority':"TEXT NOT NULL DEFAULT 'normal'",'category_id':"TEXT NOT NULL DEFAULT ''",'root_id':"TEXT NOT NULL DEFAULT ''",'origin_date':"TEXT NOT NULL DEFAULT ''",'pomodoro':'INTEGER NOT NULL DEFAULT 0'}.items():
        if name not in existing: c.execute(f'ALTER TABLE todos ADD COLUMN {name} {definition}')
    c.execute("UPDATE todos SET root_id=id WHERE root_id=''")
    c.execute("UPDATE todos SET origin_date=date WHERE origin_date=''")
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS todo_day_root ON todos(date,root_id)')
    for key, value in DEFAULTS.items():
        c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',(key,json.dumps(value)))
    if not c.execute("SELECT 1 FROM settings WHERE key='task_categories_initialized'").fetchone():
        for name, color in zip(('工作','学习','生活'), COLORS):
            c.execute('INSERT OR IGNORE INTO todo_categories VALUES(?,?,?)',(uuid.uuid4().hex,name,color))
        put(c,'task_categories_initialized',True)

def put(c,key,value):
    c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))

def value(c,key,default=None):
    r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return json.loads(r[0]) if r else default

def settings(c):
    return {key:value(c,key,default) for key,default in DEFAULTS.items()}

def save_settings(c,data,now=None):
    now=now or dt.datetime.now()
    for key in DEFAULTS:
        if key not in data: continue
        if isinstance(DEFAULTS[key],bool):
            if not isinstance(data[key],bool): raise ValueError('设置值需要为开或关')
        elif key=='theme':
            if not isinstance(data[key],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',data[key]):raise ValueError('无效主题色')
        elif data[key] not in {'font_size':('standard','large','larger'),'density':('comfortable','compact'),'task_sort':('priority','time','created'),'default_priority':('low','normal','high','urgent')}[key]: raise ValueError('无效的设置选项')
        if key=='rollover_enabled' and data[key]!=value(c,key,False):
            # Begin at the next midnight; toggling never replays old history.
            put(c,'rollover_cursor',now.date().isoformat())
        put(c,key,data[key])

def validate(c,data,old=None):
    result=dict(old or {})
    for key in ('text','start_time','end_time','remind','priority','category_id','pomodoro'):
        if key in data: result[key]=data[key]
    text=str(result.get('text','')).strip()
    if not text or len(text)>2000: raise ValueError('待办内容需要 1 至 2000 个字符')
    start,end=result.get('start_time',''),result.get('end_time','')
    for t in (start,end):
        if t:
            try:
                if dt.time.fromisoformat(t).strftime('%H:%M')!=t: raise ValueError()
            except (ValueError,TypeError): raise ValueError('时段请使用 HH:MM 格式')
    if bool(start)!=bool(end) or (start and end<=start): raise ValueError('请填写同一天内完整时段，结束时间需晚于开始时间')
    remind=result.get('remind',False)
    if remind and not start: raise ValueError('请先设置时段，再开启提醒')
    pomo=result.get('pomodoro',False)
    if not isinstance(pomo,(bool,int)) or pomo not in (0,1):raise ValueError('番茄钟选项无效')
    if pomo and not start:raise ValueError('请先设置时段，再加入番茄钟')
    priority=result.get('priority','normal')
    if priority not in ('low','normal','high','urgent'): raise ValueError('无效优先级')
    category=result.get('category_id','')
    if category and not c.execute('SELECT 1 FROM todo_categories WHERE id=?',(category,)).fetchone(): raise ValueError('待办类别不存在')
    return {'text':text,'start_time':start,'end_time':end,'remind':int(bool(remind)),'priority':priority,'category_id':category,'pomodoro':int(bool(pomo))}

def create(c,data):
    date=data['date'];dt.date.fromisoformat(date)
    fields=validate(c,data);id=uuid.uuid4().hex
    c.execute('''INSERT INTO todos(id,date,text,done,created,start_time,end_time,remind,priority,category_id,root_id,origin_date)
    VALUES(?,?,?,0,?,?,?,?,?,?,?,?)''',(id,date,fields['text'],dt.datetime.now().isoformat(),fields['start_time'],fields['end_time'],fields['remind'],fields['priority'],fields['category_id'],id,date))
    c.execute('UPDATE todos SET pomodoro=? WHERE id=?',(fields['pomodoro'],id))
    return id

def update(c,data):
    old=c.execute('SELECT * FROM todos WHERE id=?',(data['id'],)).fetchone()
    if not old: raise ValueError('待办事项不存在')
    if any(k in data for k in ('text','start_time','end_time','remind','priority','category_id','pomodoro')):
        fields=validate(c,data,old)
        c.execute('UPDATE todos SET text=:text,start_time=:start_time,end_time=:end_time,remind=:remind,priority=:priority,category_id=:category_id,pomodoro=:pomodoro WHERE id=:id',{**fields,'id':data['id']})
        if any(fields[k]!=old[k] for k in ('start_time','end_time','remind')):
            c.execute('UPDATE reminder_events SET is_read=1 WHERE todo_id=?',(data['id'],))
    if 'done' in data: c.execute('UPDATE todos SET done=? WHERE id=?',(int(bool(data['done'])),data['id']))
    if data.get('done'): c.execute('UPDATE reminder_events SET is_read=1 WHERE todo_id=?',(data['id'],))

def tick(c,now=None):
    now=now or dt.datetime.now();today=now.date()
    c.execute('''UPDATE reminder_events SET is_read=1 WHERE todo_id IN
    (SELECT id FROM todos WHERE done=1 OR remind=0 OR date<? OR (date=? AND end_time<=?))''',
    (today.isoformat(),today.isoformat(),now.strftime('%H:%M')))
    if value(c,'rollover_enabled',False):
        cursor=dt.date.fromisoformat(value(c,'rollover_cursor',today.isoformat()))
        while cursor<today:
            target=cursor+dt.timedelta(days=1)
            rows=list(c.execute('SELECT * FROM todos WHERE date=? AND done=0',(cursor.isoformat(),)))
            for row in rows:
                c.execute('''INSERT OR IGNORE INTO todos(id,date,text,done,created,start_time,end_time,remind,priority,category_id,root_id,origin_date)
                VALUES(?,?,?,0,?,?,?,?,?,?,?,?)''',(uuid.uuid4().hex,target.isoformat(),row['text'],now.isoformat(),row['start_time'],row['end_time'],row['remind'],row['priority'],row['category_id'],row['root_id'],row['origin_date']))
                c.execute('UPDATE todos SET pomodoro=? WHERE date=? AND root_id=?',(row['pomodoro'],target.isoformat(),row['root_id']))
            cursor=target
        put(c,'rollover_cursor',today.isoformat())
    for row in c.execute('SELECT * FROM todos WHERE date=? AND done=0 AND remind=1 AND start_time!=\'\'',(today.isoformat(),)):
        start=dt.datetime.fromisoformat(row['date']+'T'+row['start_time'])
        end=dt.datetime.fromisoformat(row['date']+'T'+row['end_time'])
        if start<=now<end:
            schedule=row['date']+' '+row['start_time']+'–'+row['end_time']
            c.execute('INSERT OR IGNORE INTO reminder_events(todo_id,schedule_key,created_at) VALUES(?,?,?)',(row['id'],schedule,now.isoformat()))

def notifications(c):
    return [dict(x) for x in c.execute('''SELECT e.*,t.text,t.date,t.start_time,t.end_time FROM reminder_events e
    JOIN todos t ON t.id=e.todo_id WHERE e.is_read=0 AND t.done=0 ORDER BY e.created_at DESC LIMIT 30''')]

def category_change(c,path,data):
    if path=='/api/todo/category/save':
        name=data['name'].strip();color=data.get('color',COLORS[0]);id=data.get('id') or uuid.uuid4().hex
        if not name or len(name)>40 or not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color): raise ValueError('类别名称需要 1 至 40 个字符，请选择有效颜色')
        if data.get('id'): c.execute('UPDATE todo_categories SET name=?,color=? WHERE id=?',(name,color,id))
        else: c.execute('INSERT INTO todo_categories VALUES(?,?,?)',(id,name,color))
    elif path=='/api/todo/category/delete':
        c.execute("UPDATE todos SET category_id='' WHERE category_id=?",(data['id'],))
        c.execute('DELETE FROM todo_categories WHERE id=?',(data['id'],))
    else: return None
    return {'ok':True}
