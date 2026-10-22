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

NOTES['2026-10-21'].append(('知序版本归档 · 1.35','<p>修复多篇日志的历史检索：每篇独立显示，支持标题、正文和日期搜索，并可直接定位。修复历史记录与备份区域重叠，历史列表独立滚动。主题色覆盖背景、侧栏、卡片、表单和图标等整体界面。设置有未保存更改时，离开前可选择保存、放弃或继续编辑。保留旧数据与备份兼容，并更新 GitHub 源码和 Windows 下载包。</p>'))

NOTES['2026-10-21'].append(('知序版本归档 · 1.4','<p>新增右下角闹钟番茄钟，支持专注与休息时长、轮数、暂停和开始/结束系统通知，随主题换色。设置待办时段后可选自动执行番茄钟，支持截止结束、防重复和冲突处理。相册图注可拖到任意位置，设置文字色、底色、字号、透明度并自动保存，眼睛图标控制显隐；新增普通滚轮缩放、拖动平移与右下角鸟瞰图定位。标题改为“让生活更有序”，修复按钮悬停/选中残留绿色，并明确 GitHub 当前版本、下载入口与历史提交的区别。升级前备份，保留原有日志和媒体。</p>'))

NOTES['2026-10-21'].append(('知序版本归档 · 1.45','<p>番茄钟支持拖动、记忆位置、方向键移动和按钮避让。相册支持多图注、点击图片定位添加、悬浮编辑样式与等比例缩放，预览显示日期和大小；顶部重命名、两侧翻页、查看对应日志、设置相册封面。日志插图可隐藏图注，双击查看完整信息。数据与导出按保存位置、备份恢复和单独导出整理。统计改为当日日志篇数，并支持可选的手动心情、天气记录。增量迁移保留旧图注和个人数据。</p>'))

NOTES['2026-10-22']=[('知序版本归档 · 1.5','<p>番茄钟恢复默认右下角，整个图标可手动拖动并记住位置，移除自动避让与六点手柄。心情和天气默认展示，新增太阳、云、笑脸和哭脸等线条图标，移除相关设置。相册预览顶部压缩为一行图标工具栏，卡片默认仅显示名称，悬停或键盘聚焦查看详情。日志插图默认隐藏图注，双击查看完整图注。新增可关闭的新手指南、日志删除确认和撤销，保留相册媒体。新增可勾选桌面快捷方式的 Windows 安装向导，便携版首次启动也可创建。升级前备份，保留原有个人数据。</p>')]

def append_updates(c):
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entries'").fetchone():
        import journals
        journals.migrate(c)
    for date,sections in NOTES.items():
        has_entries=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entries'").fetchone()
        if has_entries:
            import journals
            target=c.execute('SELECT id,title,body FROM entries WHERE date=? AND title=? ORDER BY created,id LIMIT 1',(date,'知序 · 版本更新归档')).fetchone()
            if not target:
                id=journals.save(c,{'date':date,'title':'知序 · 版本更新归档','body':''})
                target=c.execute('SELECT id,title,body FROM entries WHERE id=?',(id,)).fetchone()
            body=target['body']
        else:
            target=c.execute('SELECT title,body FROM days WHERE date=?',(date,)).fetchone()
            body=target['body'] if target else ''
        for heading,text in sections:
            if '<h3>'+heading+'</h3>' not in body:
                body+=('<p><br></p>' if body else '')+'<h3>'+heading+'</h3>'+text
        if has_entries:
            c.execute('UPDATE entries SET body=?,updated=? WHERE id=?',(body,dt.datetime.now().isoformat(),target['id']))
            journals.sync_day(c,date)
        else:
            c.execute('INSERT INTO days(date,title,body,updated) VALUES(?,?,?,?) ON CONFLICT(date) DO UPDATE SET title=excluded.title,body=excluded.body,updated=excluded.updated',(date,(target['title'] if target and target['title'] else '知序 · 版本更新归档'),body,dt.datetime.now().isoformat()))
