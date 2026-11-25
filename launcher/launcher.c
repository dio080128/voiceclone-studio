/*
 * 声纹工坊 · VoiceClone Studio 便携启动器
 *
 * 职责：找到同目录 resources\ 下的 Python 运行时，把环境变量配好，
 *      以无窗口方式拉起 resources\app\main.py。
 * 体积：几十 KB，不含任何 Python / Qt 二进制。
 *
 * 编译：gcc -O2 -s -municode -mwindows launcher.c launcher_res.o -o 声纹工坊.exe
 */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

#define APP_NAME L"声纹工坊"
#define BUFSZ (MAX_PATH * 4)

static void fail(const wchar_t *msg)
{
    MessageBoxW(NULL, msg, APP_NAME L" · 启动失败", MB_OK | MB_ICONERROR);
}

/* 取可执行文件所在目录 */
static BOOL get_exe_dir(wchar_t *out, DWORD n)
{
    DWORD len = GetModuleFileNameW(NULL, out, n);
    if (len == 0 || len >= n - 1) return FALSE;
    wchar_t *p = wcsrchr(out, L'\\');
    if (!p) return FALSE;
    *p = L'\0';
    return TRUE;
}

static BOOL exists(const wchar_t *path)
{
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR lpCmdLine, int nShow)
{
    wchar_t dir[BUFSZ];
    if (!get_exe_dir(dir, BUFSZ)) {
        fail(L"无法定位程序所在目录，请把程序放在普通文件夹里运行。");
        return 1;
    }

    wchar_t python[BUFSZ], script[BUFSZ], dataDir[BUFSZ];
    wchar_t modelDir[BUFSZ], ffmpeg[BUFSZ], workdir[BUFSZ];

    _snwprintf(python,   BUFSZ, L"%s\\resources\\runtime\\python.exe", dir);
    _snwprintf(script,   BUFSZ, L"%s\\resources\\app\\main.py",          dir);
    _snwprintf(dataDir,  BUFSZ, L"%s\\resources\\data",                  dir);
    _snwprintf(modelDir, BUFSZ, L"%s\\resources\\models",                dir);
    _snwprintf(ffmpeg,   BUFSZ, L"%s\\resources\\bin\\ffmpeg.exe",       dir);
    wcscpy(workdir, dir);

    if (!exists(python)) {
        /* 运行环境没就位：如果带了引导脚本，就走在线下载流程 */
        wchar_t ps1[BUFSZ];
        _snwprintf(ps1, BUFSZ, L"%s\\launcher\\bootstrap.ps1", dir);

        if (exists(ps1)) {
            int r = MessageBoxW(NULL,
                L"这是首次运行，需要先下载运行环境与语音模型（共约 3.5 GB）。\n\n"
                L"下载一次即可，之后打开程序不再需要联网。\n\n"
                L"现在开始下载吗？",
                APP_NAME L" · 首次运行", MB_YESNO | MB_ICONQUESTION);
            if (r != IDYES) return 6;

            wchar_t args[BUFSZ * 3];
            _snwprintf(args, BUFSZ * 3,
                L"/c powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%s\" -Root \"%s\"",
                ps1, dir);

            HINSTANCE h = ShellExecuteW(NULL, L"open", L"cmd.exe", args, NULL, SW_SHOWNORMAL);
            if ((INT_PTR)h <= 32) {
                fail(L"无法启动下载程序。\n\n请手动运行 launcher\\bootstrap.ps1\n"
                     L"或检查系统是否禁用了 PowerShell。");
                return 7;
            }
            return 0;
        }

        fail(L"缺少运行环境：\n\nresources\\runtime\\python.exe\n\n"
             L"请把压缩包完整解压后再运行；\n"
             L"不要只把 exe 单独复制出来，也不要在压缩包预览窗口里直接双击。");
        return 2;
    }
    if (!exists(script)) {
        fail(L"缺少程序文件：\n\nresources\\app\\main.py\n\n"
             L"安装包可能不完整，请重新解压。");
        return 3;
    }

    CreateDirectoryW(dataDir, NULL);
    CreateDirectoryW(modelDir, NULL);

    wchar_t logDir[BUFSZ], logFile[BUFSZ];
    _snwprintf(logDir, BUFSZ, L"%s\\logs", dataDir);
    CreateDirectoryW(logDir, NULL);
    _snwprintf(logFile, BUFSZ, L"%s\\runtime.log", logDir);

    /* 关键：本程序是 GUI 子系统、没有控制台。若不给子进程有效句柄，
       继承到的是 NULL，Qt/ffmpeg 往 stderr 一写就崩。
       这里把子进程的 stdout/stderr 指到日志文件，stdin 指到 NUL。 */
    SECURITY_ATTRIBUTES sa;
    sa.nLength = sizeof(sa);
    sa.lpSecurityDescriptor = NULL;
    sa.bInheritHandle = TRUE;

    HANDLE hOut = CreateFileW(logFile, FILE_APPEND_DATA,
                              FILE_SHARE_READ | FILE_SHARE_WRITE, &sa,
                              OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    HANDLE hIn = CreateFileW(L"NUL", GENERIC_READ,
                             FILE_SHARE_READ | FILE_SHARE_WRITE, &sa,
                             OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hOut == INVALID_HANDLE_VALUE) hOut = NULL;
    if (hIn == INVALID_HANDLE_VALUE) hIn = NULL;

    /* 交给 Python 侧的环境变量 */
    SetEnvironmentVariableW(L"VCS_HOME", dataDir);
    SetEnvironmentVariableW(L"VCS_MODELS", modelDir);
    if (exists(ffmpeg))
        SetEnvironmentVariableW(L"VCS_FFMPEG", ffmpeg);

    SetEnvironmentVariableW(L"HF_ENDPOINT", L"https://hf-mirror.com");
    SetEnvironmentVariableW(L"HF_HUB_DISABLE_XET", L"1");
    SetEnvironmentVariableW(L"HF_HUB_DISABLE_TELEMETRY", L"1");
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    /* 关键：不加载用户目录里的第三方包，保证环境干净可复现 */
    SetEnvironmentVariableW(L"PYTHONNOUSERSITE", L"1");
    SetEnvironmentVariableW(L"PYTHONDONTWRITEBYTECODE", L"1");

    wchar_t cmd[BUFSZ];
    _snwprintf(cmd, BUFSZ, L"\"%s\" \"%s\"", python, script);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb         = sizeof(si);
    /* 只重定向标准句柄；不要设 STARTF_USESHOWWINDOW——否则 SW_HIDE 会被子进程
       继承，导致主窗口 show() 后仍然是隐藏状态（进程活着但看不见窗）。 */
    si.dwFlags    = STARTF_USESTDHANDLES;
    si.hStdInput   = hIn;
    si.hStdOutput  = hOut;
    si.hStdError   = hOut;
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessW(python, cmd, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, workdir, &si, &pi)) {
        wchar_t buf[BUFSZ];
        _snwprintf(buf, BUFSZ,
                   L"无法启动运行环境（错误码 %lu）。\n\n%s\n\n"
                   L"常见原因：杀毒软件拦截、文件被占用、或解压不完整。",
                   GetLastError(), python);
        fail(buf);
        if (hOut) CloseHandle(hOut);
        if (hIn) CloseHandle(hIn);
        return 4;
    }

    /* 启动后 3 秒内就退出，说明运行环境有问题，直接告诉用户去哪看日志 */
    if (WaitForSingleObject(pi.hProcess, 3000) == WAIT_OBJECT_0) {
        DWORD code = 0;
        GetExitCodeProcess(pi.hProcess, &code);
        wchar_t buf[BUFSZ];
        _snwprintf(buf, BUFSZ,
                   L"程序启动后立即退出（退出码 %lu）。\n\n"
                   L"请把下面这个日志文件发给开发者：\n%s",
                   code, logFile);
        fail(buf);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        if (hOut) CloseHandle(hOut);
        if (hIn) CloseHandle(hIn);
        return 5;
    }

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    if (hOut) CloseHandle(hOut);
    if (hIn) CloseHandle(hIn);
    return 0;
}
