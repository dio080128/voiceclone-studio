# 发行说明 · 便携版打包

本项目的发行形态是**小体积启动器 + `resources` 资源目录**，整包可拷贝、可放 U 盘，
不需要目标机器安装 Python 或任何运行库。

---

## 一、产物结构

```
声纹工坊-v1.0.0/
├─ 声纹工坊.exe            ← 启动器，36 KB（纯 Win32，无 Python）
├─ 使用说明.txt
├─ VERSION.txt
├─ docs/                   ← 开发文档与自检脚本（可删）
└─ resources/
   ├─ app/                 程序代码（main.py + app/）
   ├─ runtime/             独立 Python 3.13 + 全部第三方包
   │  ├─ python.exe        ← 启动器实际拉起的进程（隐藏控制台运行）
   │  ├─ python313.dll
   │  ├─ Lib/              标准库 + site-packages（PySide6 / torch / F5-TTS…）
   │  └─ DLLs/
   ├─ bin/ffmpeg.exe       音视频转码（mp3 / m4a 解码）
   ├─ models/              F5-TTS 权重（可选，见下）
   └─ data/                用户数据，随时可备份
      ├─ voices/           音色档案
      ├─ output/           合成结果
      ├─ cache/            临时与识别模型缓存
      ├─ logs/             error.log
      └─ config.json
```

启动器只做四件事：定位同目录 `resources\runtime\python.exe` → 设置
`VCS_HOME / VCS_MODELS / HF_ENDPOINT / PYTHONNOUSERSITE` 等环境变量 →
`CreateProcessW` 拉起 `resources\app\main.py` → 退出。
所以 exe 本体极小，也不会因为缺 Qt 插件而启动失败；缺文件时会弹中文提示而不是闪退。

---

## 二、构建

```bat
:: 轻量版（不含模型，首次合成时自动下载 1.4GB）
.venv\Scripts\python.exe tools\build_release.py --out E:\VCS-Release --no-models --force

:: 完整版（把本机已下载的模型一起打进去，开箱即用）
.venv\Scripts\python.exe tools\build_release.py --out E:\VCS-Release --with-models --force
```

脚本会自动完成：复制代码 → 复制独立 Python 运行时与全部依赖 → 复制 ffmpeg →
（可选）复制模型 → 初始化 `data/` → 用 MinGW 编译启动器并嵌入图标 → 写说明文件 → 统计体积。

编译依赖：MinGW gcc / windres（脚本会优先找 `E:\qtcreator\Tools\mingw1310_64\bin`），
图标由 Qt 现画再转 ico，不需要额外素材。

---

## 三、两种发行包怎么选

| | 轻量版 | 完整版 |
|---|---|---|
| 体积 | 2.3 GB | 3.6 GB |
| 用户首次使用 | 需联网下载 1.4GB 模型 | 解压即用 |
| 适合 | 网盘分发、内网无模型仓库 | U 盘/离线交付、给不懂技术的用户 |

> 模型目录 `resources/models` 是自包含的：完整版的用户之间可以直接互相同步这个目录，
> 也可以用 `--with-models` 二次构建时复用。

### 打成分发压缩包

用项目自带脚本，**不要用资源管理器右键压缩，也不要用 bsdtar / 7z 直接压**：

```bat
:: 完整版（含模型）
.venv\Scripts\python.exe tools\make_zip.py 完整版

:: 精简版（排除模型，用户首次合成时自动下载）
.venv\Scripts\python.exe tools\make_zip.py 精简版 --exclude models
```

原因：Windows 自带压缩和 bsdtar 写出的 zip **不带 UTF-8 文件名标志**，
包内中文目录名换台机器解压就是乱码（实测 `声纹工坊` → `╔∙╬╞╣ñ╖╗`）。
Python 的 `zipfile` 会自动置位 flag 0x800，跨机器解压安全。

实测：3.56GB 打完整版约 12 分钟、出 3.06GB；2.26GB 打精简版约 3.4 分钟、出 1.76GB。
脚本会把 `.dll/.pyd/.safetensors/.whl` 等本身就是压缩格式的文件改为 store，
省掉无谓的 deflate 时间。

### 想做安装包

用 Inno Setup / NSIS 把整个 `声纹工坊-v1.0.0` 目录装到 `{app}` 即可；
注意**不要装进 `Program Files` 后又不给写权限**——`resources\data` 需要可写。
建议安装到 `%LOCALAPPDATA%\VoiceCloneStudio` 或让用户自选可写目录。

---

## 四、目标机器要求

- Windows 10/11 64 位（Win7 未测试）
- 内存 8GB 以上（加载模型后常驻约 2GB）
- 磁盘：轻量版 3GB、完整版 4.5GB（含解压与首次运行临时空间）
- 无独显可用，但很慢：4 核 CPU 跑 15 字约 2~3 分钟（推理步数 8）
- 不需要安装 Python、VC++ 运行库（`vcruntime140*.dll` 已随运行时一起带）

---

## 五、常见故障对应

| 现象 | 原因 | 处理 |
|---|---|---|
| 弹「缺少运行环境」 | 只复制了 exe 或解压不完整 | 整体解压 |
| 双击无反应 | 被杀软拦截 | 加信任，或查看 `resources\data\logs\error.log` |
| 启动后闪退 | 缺 DLL 或运行环境被删改 | 看 `error.log`，重装 |
| 首次合成卡在下载 | 网络问题 | 检查 `resources\models` 是否增长；换镜像 |
| 提示端口占用/白屏 | 极少见，Qt 平台插件缺失 | 确认 `resources\runtime\Lib\site-packages\PySide6\plugins` 完整 |

---

## 六、合规（发行前必读）

- **F5-TTS 模型权重是 CC-BY-NC 许可，禁止商业使用。** 直接打包分发并收费属于侵权。
  若要商用发行，必须替换引擎：在 `app/core/engines/` 下新增一个引擎类并注册即可
  （接口只有 `available()` 与 `synth_chunk()`），换成有商用授权的模型。
- 软件本身（本项目代码）可自由分发，但必须保留免责声明：**不得用于伪造他人身份、
  诈骗、虚假信息**；对外发布合成音频应标注「AI 合成」。
- 若发行到应用商店，需自行确认各平台对「声音克隆」类工具的资质要求。

---

## 七、版本与回滚

`VERSION.txt` 记录版本、构建时间、是否预置模型。
回滚只需把旧目录整体替换回去；用户数据在 `resources\data`，升级时**保留该目录**即可无缝迁移。

---

## 八、构建踩坑记录（改启动器前必看）

这三条都是实测踩出来的，症状都表现为「双击没反应 / 进程秒退 / 窗口不出来」：

1. **不要用 `pythonw.exe`**
   它是 GUI 子系统，没有控制台时 C 层 `stdout/stderr` 是空指针。Qt 的 ffmpeg 后端一打
   「Input #0, wav...」就踩空指针崩溃，进程静默退出、`error.log` 什么都不留。
   改为 `python.exe` + `CREATE_NO_WINDOW`（有隐藏控制台、无黑框），并把子进程
   stdout/stderr 重定向到 `resources\data\logs\runtime.log`。
   **验证方法**：正常启动时该日志里会出现 ffmpeg 的输入信息。

2. **不要设 `STARTF_USESHOWWINDOW` + `SW_HIDE`**
   这个标志会被子进程继承，Qt 拿到 `nCmdShow=SW_HIDE`，窗口 `show()` 之后仍是隐藏状态——
   现象是进程活着、占 120MB 内存，但桌面上什么都没有。

3. **裁剪标准库别删 `unittest`**
   `torch.utils._config_module` 会 `import unittest`，删掉后 `import torch` 直接
   `ModuleNotFoundError`。同理 `test` 包也建议保留。可以安全剔除的只有
   `tkinter / idlelib / lib2to3 / ensurepip / turtledemo`。

另外：**gcc 不接受命令行里的中文路径**（MinGW 按系统代码页解释，UTF-8 参数会变成乱码）。
构建脚本用 `subprocess` 传参没问题（走 CreateProcessW），但在 Git Bash 里直接
`gcc ... "E://声纹工坊//x.o"` 会报 `No such file or directory`。

增量构建时如果 exe 正在运行会覆盖失败，先关闭程序再打包。

---

## 九、多语言扩展包（可选，单独分发）

主程序的 3.6 GB 包里只有 F5-TTS（中英）。需要日语/韩语/粤语时，另外发一个
**多语言扩展包**（GPT-SoVITS）：

```bat
.venv\Scripts\python.exe tools\build_ext.py            :: 目录 + zip（首次约 40 分钟）
.venv\Scripts\python.exe tools\build_ext.py --zip-only  :: 目录已存在时只重压缩
```

产物：`dist\声纹工坊-v1.0.0-多语言扩展包.zip`（约 2.7 GB）。
解压后得到 `gpt_sovits\`，放进 `resources\` 即启用。

**为什么单独放**：GPT-SoVITS 的依赖（pyopenjtalk / funasr / pytorch-lightning）
只支持 Python 3.9~3.10，主程序是 3.13，装不到一起。所以扩展包自带一套
Python 3.10 运行时，主程序用子进程 + 本地 HTTP 调用它。

**构建时做的精简**（否则体积 3.3 GB+）：
- 删 `torch/lib/*.lib`（静态库，编译器才用）——省 768 MB
- 删 `torch/include`（C++ 头文件）——省 49 MB
- 删 `pip/setuptools/wheel` ——省约 40 MB
- **保留 `pkg_resources`**：pyopenjtalk 用它定位词典，删了日语直接崩

**中文路径的坑（重要）**：open_jtalk 的 C 库不认非 ASCII 路径，路径里有中文就报
`Failed to initialize Mecab`，而本程序目录叫「声纹工坊」。解决办法是启动时检测词典
路径，含非 ASCII 就自动复制到 `C://ProgramData//VoiceCloneStudio//ojdic` 再指过去
（见 `gptsovits_engine.py` 里的 `_LAUNCHER_SRC`）。这台机器 8.3 短路径是禁用的，
所以不能靠短名绕过。
