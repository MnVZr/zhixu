"""Versioned image-space notes; legacy fields remain readable by exports and old clients."""
import json
import uuid
import math

def migrate(c):
    columns={r['name'] for r in c.execute('PRAGMA table_info(attachments)')}
    if 'captions' not in columns:
        c.execute("ALTER TABLE attachments ADD COLUMN captions TEXT NOT NULL DEFAULT '[]'")
        for row in list(c.execute("SELECT id,annotation,caption_style FROM attachments WHERE annotation<>''")):
            style=json.loads(row['caption_style'] or '{}')
            notes=[dict(style,id=uuid.uuid4().hex,text=row['annotation'])]
            c.execute('UPDATE attachments SET captions=? WHERE id=?',(json.dumps(notes,ensure_ascii=False),row['id']))
    if 'cover_id' not in {r['name'] for r in c.execute('PRAGMA table_info(albums)')}:
        c.execute("ALTER TABLE albums ADD COLUMN cover_id TEXT NOT NULL DEFAULT ''")
    c.execute("CREATE TABLE IF NOT EXISTS day_context(date TEXT PRIMARY KEY,mood TEXT NOT NULL DEFAULT '',weather TEXT NOT NULL DEFAULT '')")

def update(c,row,data,note,style_validator):
    existing=json.loads(row['captions'])
    if 'captions' in data:
        notes=data['captions']
        if not isinstance(notes,list) or len(notes)>50:raise ValueError('每张图片最多 50 条图注')
        cleaned=[];seen=set()
        for item in notes:
            if not isinstance(item,dict):raise ValueError('图注格式无效')
            ident=item.get('id') or uuid.uuid4().hex
            if not isinstance(ident,str) or len(ident)>64 or ident in seen:raise ValueError('图注标识无效')
            seen.add(ident)
            text=item.get('text','')
            if not isinstance(text,str) or len(text)>2000:raise ValueError('每条图注最多 2000 字')
            for key in ('x','y','size','opacity'):
                if key in item and (isinstance(item[key],bool) or not isinstance(item[key],(int,float)) or not math.isfinite(item[key])):raise ValueError('图注位置或样式无效')
            cleaned.append(dict(style_validator(item),id=ident,text=text))
        existing=cleaned
        note='\n'.join(x['text'] for x in existing)
    elif 'annotation' in data or 'caption_style' in data:
        if not existing and note:existing=[{'id':uuid.uuid4().hex,'text':note}]
        if existing:
            if 'annotation' in data:existing[0]['text']=note
            if 'caption_style' in data:existing[0].update(style_validator(data['caption_style']))
    c.execute('UPDATE attachments SET captions=? WHERE id=?',(json.dumps(existing,ensure_ascii=False),row['id']))
    return note
