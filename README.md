# mapinfo12pro

MapInfo Professional 12.0.2 Build 208 的原生修改项目。目标是在 MapInfo 原有窗口中完成连续撤回，并改进中文长路径和 WOR 工程的保存。

## 当前状态

构建器在 32 位 `micore.dll` 中写入原生撤回和路径处理代码，并校验输入文件的 SHA-256 和原指令。

- 对当前本地 Native TAB，新增点等原生对象编辑、单元格修改和批量 `UPDATE` 共用原生撤回历史。编辑菜单和 Ctrl+Z 可以连续恢复最近 33 步，其中包含原程序持有的一步。
- 批量更新沿用 MapInfo 的原生撤回内存限额。构建器把允许撤回的对象数提升至 800，尊重已关闭撤回的设置。保存或关闭图层时清空相关历史。切换到另一张表进行编辑时从该表重新累计。
- WOR 保存时，同一磁盘上不同目录中的本地 TAB 可以写成相对路径。已用原生保存和加载命令验证过 `..\Probe`。
- 为已定位的路径拼接增加了缓冲区边界检查。在 323 字符中文路径的测试中，打开操作返回错误，已有图层仍可访问。打开这类长路径和保存时的截断处理还有待完成。
- 跨表合并历史、布局和图层样式撤回仍待实现。

## 在本机生成程序

在 Windows 上准备 Python 3 和已授权的 32 位 MapInfo Professional 12.0.2 Build 208。解压发布 ZIP，在解压目录中运行以下命令。第二个路径应指向一个尚未创建的目录。

```powershell
python -m pip install -r requirements.txt
python build_app.py 'C:\Program Files (x86)\MapInfo\Professional' 'D:\mapinfo12pro'
```

生成成功后，双击 `D:\mapinfo12pro\mapinfo12pro.exe`，保留同目录的运行文件。构建器保留原安装目录，遇到不支持的核心 DLL 或已存在的输出目录时会报错。下载包提供构建源码和说明，MapInfo 运行文件和授权来自你自己的本机安装。

## 验证范围

本机安装版本的测试进程验证了实际 Ctrl+Z、混合编辑、容量上限、撤回后继续编辑、保存、关表重开与表切换。用本机正常运行的 MapInfo 文件构建的独立副本也通过了启动和 Native TAB 三步撤回测试。这些运行结果来自同一台 Windows 电脑，其他电脑需使用受支持的 MapInfo 构建和授权。

路径测试中，工程和图层分别位于不同层级的 D 盘目录，WOR 输出相对路径，关闭并重开后指向原图层。测试也覆盖了 323 字符的 E 盘中文路径。

相对路径转换使用 Windows 的 `PathRelativePathToA`。 [Microsoft API 文档](https://learn.microsoft.com/en-us/windows/win32/api/shlwapi/nf-shlwapi-pathrelativepathtoa)
