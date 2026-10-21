# 后续版本发布

1. 使用测试数据开发；将 `ZHIXU_DATA` 指向独立目录，不拿个人资料库做破坏性测试。
2. 更新版本资源、界面版本、`package_release.py` 输出名、package.json、README 和 CHANGELOG。
3. 数据结构变化先提高结构版本，升级前用 SQLite backup API 保存快照，再做向后兼容的增量迁移。不能删除旧库、覆盖媒体目录或用示例数据重建用户数据库。
4. 保留旧目录/旧 ZIP 导入，并增加旧数据迁移与备份恢复测试。迁移失败不能修改当前路径配置；设置目录不可访问时不能静默创建空库。
5. 运行 Python 测试、离线界面测试和 Windows 构建；在隔离目录运行最终 EXE 验证。实际窗口外观也应另行检查。
6. 只提交明确列出的源码、文档与许可证。检查 `git diff --cached --name-only`，严禁提交 `data`、`attachments`、数据库、备份、运行配置、登录令牌、工作目录或个人媒体。
7. `package_release.py` 使用白名单打包，不压缩整个 release 目录。发布前检查 ZIP 清单和 SHA256；只上传已核对的程序 ZIP 与校验文件。
8. 推送版本标签，GitHub Release 附 Windows ZIP，README 指向最新 Release。提醒用户先完整备份、退出旧版后更新，保留旧数据目录。

公开版本不会自动往其他用户的日志里写入维护者的更新记录。`releases.py` 仅提供本地明确调用的归档工具，不在启动时自动执行。
