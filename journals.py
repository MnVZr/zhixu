"""Multi-entry journals, safe local media markup, and non-destructive legacy migration."""
import datetime as dt
from html import escape
from html.parser import HTMLParser
import re
import uuid
import json

class CleanHTML(HTMLParser):
    tags={'p','div','br','b','strong','i','em','u','ul','ol','li','h2','h3','blockquote','span','figure','figcaption','img','video','a'}
    def __init__(self):super().__init__(convert_charrefs=True);self.out=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','iframe','object','svg','math'}:self.skip+=1;return
        if self.skip or tag not in self.tags:return
        values=dict(attrs);allowed=[]
        for key,value in values.items():
            if value is None:continue
            if key=='data-media-id' and re.fullmatch(r'[a-f0-9]{32}',value):allowed.append((key,value))
            if key in {'src','href'} and re.fullmatch(r'/files/[a-f0-9]{32}(?:\?download=1)?',value):allowed.append((key,value))
            if key in {'alt','title'}:allowed.append((key,value[:1000]))
        if tag=='video':allowed.extend([('controls',''),('preload','metadata')])
        self.out.append('<'+tag+''.join(' '+k+'="'+escape(v,quote=True)+'"' for k,v in allowed)+'>')
    def handle_endtag(self,tag):
        if tag in {'script','style','iframe','object','svg','math'}:self.skip=max(0,self.skip-1);return
        if not self.skip and tag in self.tags and tag not in {'br','img'}:self.out.append('</'+tag+'>')
    def handle_data(self,data):
        if not self.skip:self.out.append(escape(data))

def clean(body):
    parser=CleanHTML();parser.feed(body);return ''.join(parser.out)

def migrate(c):
    c.execute('''CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,date TEXT NOT NULL,title TEXT NOT NULL DEFAULT '',body TEXT NOT NULL DEFAULT '',collapsed INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,updated TEXT NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS entries_date ON entries(date,created,id)')
    columns={x['name'] for x in c.execute('PRAGMA table_info(attachments)')}
    if 'entry_id' not in columns:c.execute("ALTER TABLE attachments ADD COLUMN entry_id TEXT NOT NULL DEFAULT ''")
    if 'legacy_pending' not in columns:
        c.execute('ALTER TABLE attachments ADD COLUMN legacy_pending INTEGER NOT NULL DEFAULT 0')
        c.execute('UPDATE attachments SET legacy_pending=1 WHERE journal_visible=1')
    for row in list(c.execute('SELECT * FROM days')):
        entry=c.execute('SELECT id FROM entries WHERE date=? ORDER BY created,id LIMIT 1',(row['date'],)).fetchone()
        if not entry:
            id=uuid.uuid4().hex;stamp=row['updated'] or row['date']+'T00:00:00'
            c.execute('INSERT INTO entries VALUES(?,?,?,?,0,?,?)',(id,row['date'],row['title'],row['body'],stamp,stamp));entry={'id':id}
        c.execute("UPDATE attachments SET entry_id=? WHERE date=? AND entry_id='' AND journal_visible=1",(entry['id'],row['date']))

def primary(c,date):
    row=c.execute('SELECT * FROM entries WHERE date=? ORDER BY created,id LIMIT 1',(date,)).fetchone()
    return dict(row) if row else None

def ensure(c,date):
    row=primary(c,date)
    if row:return row['id']
    return save(c,{'date':date,'title':'','body':''})

def save(c,data):
    date=data['date'];dt.date.fromisoformat(date)
    id=data.get('id') or uuid.uuid4().hex;stamp=dt.datetime.now().isoformat(timespec='microseconds')
    old=c.execute('SELECT date FROM entries WHERE id=?',(id,)).fetchone()
    if old and old['date']!=date:raise ValueError('日志日期不匹配')
    title=str(data.get('title',''))[:300];body=str(data.get('body',''))
    if len(body)>20*1024*1024:raise ValueError('正文过大，请减少内容')
    c.execute('''INSERT INTO entries VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,updated=excluded.updated''',(id,date,title,clean(body),int(bool(data.get('collapsed',False))),stamp,stamp))
    c.execute('UPDATE attachments SET legacy_pending=0 WHERE entry_id=?',(id,))
    sync_day(c,date)
    return id

def sync_day(c,date):
    row=primary(c,date)
    if not row:c.execute('DELETE FROM days WHERE date=?',(date,))
    if row:c.execute('INSERT INTO days VALUES(?,?,?,?) ON CONFLICT(date) DO UPDATE SET title=excluded.title,body=excluded.body,updated=excluded.updated',(date,row['title'],row['body'],row['updated']))

def embed_legacy(entry,attachments):
    """Append old attachment media in the returned view; never rewrite an old body silently."""
    body=entry['body']
    for item in attachments:
        if item['entry_id']!=entry['id'] or not item['journal_visible'] or not item['legacy_pending'] or item['id'] in body:continue
        id=item['id'];name=escape(item['name']);caption=escape(item['annotation'])
        if item['mime'].startswith('image/'):
            body+=f'<figure data-media-id="{id}"><img src="/files/{id}" alt="{name}"><figcaption>{caption}</figcaption></figure><p><br></p>'
        elif item['mime']=='video/mp4':
            body+=f'<figure data-media-id="{id}"><video src="/files/{id}" controls preload="metadata"></video><figcaption>{caption}</figcaption></figure><p><br></p>'
        else:body+=f'<p><a href="/files/{id}?download=1">{name}</a></p>'
    return {**entry,'body':body}


def delete(c,id):
    row=c.execute('SELECT * FROM entries WHERE id=?',(id,)).fetchone()
    if not row:raise ValueError('日志不存在或已删除')
    entry=dict(row)
    media=[dict(x) for x in c.execute('SELECT id,journal_visible,legacy_pending FROM attachments WHERE entry_id=?',(id,))]
    payload=json.dumps({'entry':entry,'media':media},ensure_ascii=False)
    c.execute('INSERT OR REPLACE INTO deleted_entries VALUES(?,?,?,?)',(id,entry['date'],payload,dt.datetime.now().isoformat()))
    c.execute("UPDATE attachments SET entry_id='',journal_visible=0,legacy_pending=0 WHERE entry_id=?",(id,))
    c.execute('DELETE FROM entries WHERE id=?',(id,))
    sync_day(c,entry['date'])
    return {'ok':True,'id':id,'date':entry['date']}

def restore(c,id):
    row=c.execute('SELECT payload FROM deleted_entries WHERE id=?',(id,)).fetchone()
    if not row:raise ValueError('找不到可恢复的日志')
    payload=json.loads(row['payload']);entry=payload['entry']
    if c.execute('SELECT 1 FROM entries WHERE id=?',(id,)).fetchone():raise ValueError('日志已恢复')
    c.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?)',tuple(entry[k] for k in ('id','date','title','body','collapsed','created','updated')))
    for item in payload['media']:
        c.execute("UPDATE attachments SET entry_id=?,journal_visible=?,legacy_pending=? WHERE id=? AND entry_id=''",(id,item['journal_visible'],item['legacy_pending'],item['id']))
    c.execute('DELETE FROM deleted_entries WHERE id=?',(id,));sync_day(c,entry['date'])
    return {'ok':True,'id':id,'date':entry['date']}
