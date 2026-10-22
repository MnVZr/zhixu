"""Data lives outside app updates. Switching/restoring always retains the source."""
from contextlib import contextmanager
import datetime as dt
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from html.parser import HTMLParser

def config_path(root):
    if os.environ.get('ZHIXU_DATA'):return Path(os.environ['ZHIXU_DATA']).parent/'test-storage.json'
    return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Zhixu'/'storage.json'

def resolve(root):
    if os.environ.get('ZHIXU_DATA'):return Path(os.environ['ZHIXU_DATA']).resolve()
    config=config_path(root)
    if config.exists():
        # An unavailable external drive must never silently create a different library.
        path=Path(json.loads(config.read_text(encoding='utf-8'))['data_path'])
        if not (path/'journal.db').is_file():raise ValueError('找不到已设置的数据目录：'+str(path)+'。请恢复该目录或连接相应磁盘。')
        return path.resolve()
    if (root/'data'/'journal.db').is_file():return (root/'data').resolve()
    return (Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Zhixu'/'data').resolve()

def remember(root,path):
    config=config_path(root);config.parent.mkdir(parents=True,exist_ok=True)
    tmp=config.with_suffix('.tmp');tmp.write_text(json.dumps({'data_path':str(path)},ensure_ascii=False),encoding='utf-8');os.replace(tmp,config)

def validate(path):
    file=path/'journal.db'
    if not file.is_file():raise ValueError('请选择含 journal.db 的数据文件夹')
    c=sqlite3.connect(file.as_uri()+'?mode=ro',uri=True)
    try:
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('数据库校验失败')
        if c.execute('PRAGMA user_version').fetchone()[0]>6:raise ValueError('此数据来自较新版本，请使用最新版知序')
        tables={x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'days','todos','attachments'}<=tables:raise ValueError('不是知序数据目录')
        for id, in c.execute('SELECT id FROM attachments'):
            if not re.fullmatch('[a-f0-9]{32}',id) or not (path/'attachments'/id).is_file():raise ValueError('附件缺失，目录不完整，请选择完整数据或备份')
    finally:c.close()

def snapshot(path,label='manual'):
    folder=path/'upgrade-backups';folder.mkdir(exist_ok=True)
    target=folder/(label+'-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.db')
    src=sqlite3.connect(path/'journal.db');dst=sqlite3.connect(target)
    try:src.backup(dst)
    finally:src.close();dst.close()
    return target

@contextmanager
def exclusive_target(path):
    path.mkdir(parents=True,exist_ok=True)
    handle=(path/'instance.lock').open('a+b');handle.seek(0,2)
    if not handle.tell():handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise ValueError('此数据目录正在被另一个知序程序使用，请先退出该程序')
        yield handle
    finally:handle.close()

def copy_to(source,target):
    if target==source or source in target.parents or target in source.parents:raise ValueError('新目录不能与当前目录相同或互相包含')
    if target.exists() and any(target.iterdir()):raise ValueError('迁移目标必须是空文件夹；读取旧数据请使用“打开数据目录”')
    target.mkdir(parents=True,exist_ok=True)
    # A failed copy never changes the active pointer; original data remains untouched.
    for file in source.iterdir():
        if file.name in {'instance.lock','runtime.json'}:continue
        if file.is_dir():shutil.copytree(file,target/file.name)
        elif file.name=='journal.db':
            src=sqlite3.connect(file);dst=sqlite3.connect(target/file.name)
            try:src.backup(dst)
            finally:src.close();dst.close()
        elif not file.name.startswith('journal.db-'):shutil.copy2(file,target/file.name)
    validate(target)

def restore_zip(content,parent):
    target=parent/('知序-导入-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);target.mkdir()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if len(z.infolist())>100000 or sum(x.file_size for x in z.infolist())>20*1024**3:raise ValueError('备份过大')
        for item in z.infolist():
            name=item.filename.replace('\\','/')
            if not name.startswith('data/') or name.endswith('/'):continue
            relative=Path(name[5:])
            if relative.is_absolute() or '..' in relative.parts or ':' in name:raise ValueError('备份包含不安全路径')
            # Only the database and attachment payload are required; no runtime/config/code is restored.
            if str(relative)=='journal.db' or (len(relative.parts)==2 and relative.parts[0]=='attachments' and re.fullmatch('[a-f0-9]{32}',relative.parts[1])):
                dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst)
    validate(target);return target

class Plain(HTMLParser):
    def __init__(self):super().__init__();self.text=[]
    def handle_data(self,data):self.text.append(data)
    def handle_starttag(self,tag,attrs):
        if tag in {'br','p','div','h2','h3','li','figure','figcaption'}:self.text.append('\n')
        if tag in {'img','video'}:self.text.append('[图片]' if tag=='img' else '[视频]')
    def handle_endtag(self,tag):
        if tag in {'p','div','h2','h3','li','figure','figcaption'}:self.text.append('\n')

def safe_name(name):return re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',name).strip('. ')[:100] or '未命名'

def export(c,path,kind):
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        if kind=='journals':
            import journals
            attachments=[dict(x) for x in c.execute('SELECT * FROM attachments')]
            for row in c.execute('SELECT * FROM entries ORDER BY date,created,id'):
                parser=Plain();parser.feed(journals.embed_legacy(dict(row),attachments)['body']);text=row['title']+'\n'+row['date']+'\n\n'+''.join(parser.text).strip()
                z.writestr(row['date']+'/'+safe_name(row['title'])+'-'+row['id'][:8]+'.txt',text.encode('utf-8-sig'))
        elif kind=='albums':
            manifest=[]
            for album in c.execute('SELECT a.*,c.name AS category FROM albums a LEFT JOIN categories c ON c.id=a.category_id'):
                items=[];folder=safe_name(album['name'])+'-'+album['id'][:8]
                for item in c.execute('SELECT a.* FROM attachments a JOIN album_items i ON i.attachment_id=a.id WHERE i.album_id=?',(album['id'],)):
                    filename=folder+'/'+item['id'][:8]+'-'+safe_name(item['name']);z.write(path/'attachments'/item['id'],filename);items.append({**dict(item),'exported_file':filename})
                manifest.append({**dict(album),'items':items})
            z.writestr('相册信息.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
        else:raise ValueError('未知导出类型')
    return buffer.getvalue()
