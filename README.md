# mapinfo12pro

MapInfo Professional 12.0.2 Build 208 的原生修改项目。目标是在 MapInfo 原有窗口中完成连续撤回，并改进中文长路径和 WOR 工程的保存。

## 当前状态

构建器在 32 位 `micore.dll` 中写入原生撤回和路径处理代码，并校验输入文件的 SHA-256 和原指令。

- 对当前本地 Native TAB，新增点等原生对象编辑、单元格修改和批量 `UPDATE` 共用原生撤回历史。编辑菜单和 Ctrl+Z 可以连续恢复最近 33 步，其中包含原程序持有的一步。
- 批量更新沿用 MapInfo 的原生撤回内存限额。构建器把允许撤回的对象数提升至 800，尊重已关闭撤回的设置。保存或关闭图层时清空相关历史。切换到另一张表进行编辑时从该表重新累计。
- WOR 保存时，同一磁盘上不同目录中的本地 TAB 可以写成相对路径。已用原生保存和加载命令验证过 `..\Probe`。
- 为已定位的路径拼接增加了缓冲区边界检查。在 323 字符中文路径的测试中，打开操作返回错误，已有图层仍可访问。打开这类长路径和保存时的截断处理还有待完成。
- 跨表合并历史、布局和图层样式撤回仍待实现。

## Windows 部署

### 1. 安装并核对 MapInfo 原版

从 [Precisely 的 MapInfo Pro 下载入口](https://support.precisely.com/product-downloads/for/mapinfo-professional/) 或你的组织提供的授权介质获取 **32 位 MapInfo Professional 12.0.2 Build 208**。如果介质是 12.0 基础版，请安装对应的 12.0.2 维护更新。先按原版流程激活并启动一次，确认原版能够正常打开。

本项目按核心文件的 SHA-256 匹配构建。以下命令中的路径请改成你的实际安装目录。

```powershell
$mapinfo = 'C:\Program Files (x86)\MapInfo\Professional'
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $mapinfo 'micore.dll')
```

支持的 SHA-256 为 `5c0633da51941635bf897c7409ff976afdb685e9a5c92658795ee073a4dbde64`。仅显示相同版本号的核心文件也可能有不同的哈希。

### 2. 下载并生成增强版

安装 Python 3。下载并解压 [mapinfo12pro v0.1.0](https://github.com/RenXiaokai1999/mapinfo12pro/releases/download/v0.1.0/mapinfo12pro-v0.1.0.zip)，在含有 `build_app.py` 的解压目录中打开 PowerShell。输出路径应位于原安装目录之外，且尚未创建。

```powershell
$mapinfo = 'C:\Program Files (x86)\MapInfo\Professional'
$output = 'D:\mapinfo12pro'
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw '构建依赖安装失败' }
python build_app.py $mapinfo $output
```

构建器读取原版安装目录，在输出目录生成独立的增强版副本。

### 3. 启动并验证撤回

双击 `D:\mapinfo12pro\mapinfo12pro.exe`，保留同目录的运行文件。打开一份本地 Native TAB 样本，连续执行两次编辑，再按两次 **Ctrl+Z**，逐步检查结果。MapInfo 运行文件及授权来自本机原版安装。

遇到 `Unsupported micore.dll` 时，核对第 1 步的版本和哈希。遇到 `Destination already exists` 时，换一个尚不存在的输出目录。若启动时仍显示原版激活窗口，请核对本机 MapInfo 授权。

## 验证范围

本机安装版本的测试进程验证了实际 Ctrl+Z、混合编辑、容量上限、撤回后继续编辑、保存、关表重开与表切换。用本机正常运行的 MapInfo 文件构建的独立副本也通过了启动和 Native TAB 三步撤回测试。这些运行结果来自同一台 Windows 电脑，其他电脑需使用受支持的 MapInfo 构建和授权。

路径测试中，工程和图层分别位于不同层级的 D 盘目录，WOR 输出相对路径，关闭并重开后指向原图层。测试也覆盖了 323 字符的 E 盘中文路径。

相对路径转换使用 Windows 的 `PathRelativePathToA`。 [Microsoft API 文档](https://learn.microsoft.com/en-us/windows/win32/api/shlwapi/nf-shlwapi-pathrelativepathtoa)
