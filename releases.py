"""Idempotent version archive requested by the owner of this installation."""
import datetime as dt

NOTES = {
 '2026-10-20': [('知序版本归档 · Demo',
   '<p>初建知序 Demo：按日期编辑科研与学习日志，支持自动保存、图片及 MP4 等附件预览；提供每日待办、历史记录和本地备份，打包为 Windows 便携程序。</p>')],
 '2026-10-21': [('知序版本归档 · 1.0',
   '<p>完善编辑器选中状态：加粗、斜体等启用后深底浅字，新增下划线和编号列表。新增相册集及分类、增删改查和媒体预览；日志图片/视频可加入相册，查看来源日志并跳转。编辑器本地运行，无 WPS 小助手。</p>'),
   ('知序版本归档 · 1.1',
   '<p>相册媒体新增重命名、内容批注、导入日期，以及按导入时间、大小、名称正反序排序。每日待办新增可选时段与提醒、优先级和颜色类别。设置中可开启零点自动顺延未完成事项；新增本机后台与系统托盘，用于提醒和顺延。升级保留原数据，并将 Demo、1.0、1.1 更新记录分别归档至 10 月 20 日和 21 日。</p>')]
}

NOTES['2026-10-21'].append(('知序版本归档 · 1.2','<p>改善小窗口与缩放适配，侧栏和弹窗可完整滚动。统一知序窗口及任务栏图标，精简文案并改为通用记录。待办使用背景色区分优先级，悬停查看说明、点击编辑；类别支持调色盘与经典配色。新增字号、界面密度、待办排序、默认优先级、隐藏已完成、统计栏及灵感卡片等设置。保留原日志、待办与相册数据。</p>'))

NOTES['2026-10-21'].append(('知序版本归档 · 1.3','<p>相册排序精简为按时间、大小、名称并独立切换方向。新增主题色，移除界面密度。支持迁移或打开数据目录、导入旧版备份、导出日志文本与相册。媒体预览优先展示，支持缩放、图注开关与折叠编辑；重命名自动补齐后缀，界面隐藏后缀。日志支持一天多篇、纵向展示与折叠，图片和视频可直接插入正文、添加图注并关联相册。升级前自动备份，保留旧数据，准备 GitHub 项目和下载使用文档。</p>'))

def append_updates(c):
    for date,sections in NOTES.items():
        row=c.execute('SELECT title,body FROM days WHERE date=?',(date,)).fetchone()
        title=row['title'] if row and row['title'] else '知序 · 版本更新归档'
        body=row['body'] if row else ''
        for heading,text in sections:
            if heading not in body:
                body+=('<p><br></p>' if body else '')+'<h3>'+heading+'</h3>'+text
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entries'").fetchone():
            first=c.execute('SELECT id FROM entries WHERE date=? ORDER BY created,id LIMIT 1',(date,)).fetchone()
            if first:c.execute('UPDATE entries SET title=?,body=?,updated=? WHERE id=?',(title,body,dt.datetime.now().isoformat(),first['id']))
        c.execute('INSERT INTO days(date,title,body,updated) VALUES(?,?,?,?) ON CONFLICT(date) DO UPDATE SET title=excluded.title,body=excluded.body,updated=excluded.updated',
                  (date,title,body,dt.datetime.now().isoformat()))
