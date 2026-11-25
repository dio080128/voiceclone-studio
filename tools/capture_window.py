# -*- coding: utf-8 -*-
"""抓取指定标题窗口的截图（纯 ctypes，不依赖被测进程）。

用法：python tools/capture_window.py "声纹工坊" out.png
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

PW_RENDERFULLCONTENT = 0x00000002


def find_window(keyword: str) -> int:
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if keyword in buf.value:
            found.append((hwnd, buf.value))
            return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0][0] if found else 0


def capture(hwnd: int, out_path: str) -> bool:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False

    hdc_win = user32.GetWindowDC(hwnd)
    hdc = gdi32.CreateCompatibleDC(hdc_win)
    bmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    gdi32.SelectObject(hdc, bmp)

    ok = user32.PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount = 1, 32
    bi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bi), 0)

    from PIL import Image
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)

    # PrintWindow 拿不到内容时（全黑）退回到屏幕拷贝
    extrema = img.convert("L").getextrema()
    if extrema[1] < 8:
        user32.SetForegroundWindow(hwnd)
        import time
        time.sleep(0.8)
        screen = user32.GetDC(0)
        mem = gdi32.CreateCompatibleDC(screen)
        bmp2 = gdi32.CreateCompatibleBitmap(screen, w, h)
        gdi32.SelectObject(mem, bmp2)
        gdi32.BitBlt(mem, 0, 0, w, h, screen, rect.left, rect.top, 0x00CC0020)
        gdi32.GetDIBits(mem, bmp2, 0, h, buf, ctypes.byref(bi), 0)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
        gdi32.DeleteObject(bmp2)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, screen)

    img.convert("RGB").save(out_path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(hwnd, hdc_win)
    return bool(ok)


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "声纹工坊"
    out = sys.argv[2] if len(sys.argv) > 2 else "window.png"
    hwnd = find_window(keyword)
    if not hwnd:
        print("未找到窗口")
        return 2
    capture(hwnd, out)
    print("已保存", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
