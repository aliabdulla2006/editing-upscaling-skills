"""Background window helpers: find CapCut windows, capture them without focus, post input."""
import ctypes, ctypes.wintypes as wt
from PIL import Image
u = ctypes.windll.user32; g = ctypes.windll.gdi32; k = ctypes.windll.kernel32
u.SetProcessDPIAware()

def proc_name(pid):
    h = k.OpenProcess(0x1000, False, pid); buf = ctypes.create_unicode_buffer(260); n = wt.DWORD(260)
    k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)); k.CloseHandle(h); return buf.value

def capcut_windows(visible_only=True):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if 'CapCut' in proc_name(pid.value) and (u.IsWindowVisible(h) or not visible_only):
            t = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, t, 256)
            c = ctypes.create_unicode_buffer(256); u.GetClassNameW(h, c, 256)
            r = wt.RECT(); u.GetWindowRect(h, ctypes.byref(r))
            out.append(dict(hwnd=h, title=t.value, cls=c.value, rect=(r.left, r.top, r.right, r.bottom)))
        return True
    u.EnumWindows(cb, 0)
    return out

def capture(hwnd):
    r = wt.RECT(); u.GetClientRect(hwnd, ctypes.byref(r)); w, h = r.right, r.bottom
    hdc = u.GetDC(hwnd); mdc = g.CreateCompatibleDC(hdc); bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mdc, bmp)
    ok = u.PrintWindow(hwnd, mdc, 3)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]
    bmi = BMI(); bmi.biSize = ctypes.sizeof(BMI); bmi.biWidth = w; bmi.biHeight = -h; bmi.biPlanes = 1; bmi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    g.DeleteObject(bmp); g.DeleteDC(mdc); u.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB"), ok

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
def post_click(hwnd, x, y):
    lp = (y << 16) | (x & 0xFFFF)
    u.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    u.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lp)
    u.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)

def foreground():
    h = u.GetForegroundWindow(); t = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, t, 256); return h, t.value

class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", wt.UINT), ("flags", wt.UINT), ("showCmd", wt.UINT),
                ("ptMinPosition", wt.POINT), ("ptMaxPosition", wt.POINT), ("rcNormalPosition", wt.RECT)]

def park_offscreen(hwnd, w=1920, h=1080, x=-6000, y=0):
    """Show the window un-minimized but far outside every monitor, without activating it."""
    wp = WINDOWPLACEMENT(); wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    u.GetWindowPlacement(hwnd, ctypes.byref(wp))
    wp.rcNormalPosition = wt.RECT(x, y, x + w, y + h); wp.showCmd = 4  # SW_SHOWNOACTIVATE
    u.SetWindowPlacement(hwnd, ctypes.byref(wp))
    u.SetWindowPos(hwnd, 1, x, y, w, h, 0x10 | 0x4)  # HWND_BOTTOM, NOACTIVATE|NOZORDER-less

def post_dblclick(hwnd, x, y):
    lp = (y << 16) | (x & 0xFFFF)
    for m, wp in ((0x200, 0), (0x201, 1), (0x202, 0), (0x203, 1), (0x202, 0)):
        u.PostMessageW(hwnd, m, wp, lp)

def restore_foreground(hwnd):
    """Give focus back to Ali's window (ALT tap lets a background process change the foreground)."""
    u.keybd_event(0x12, 0, 0, 0); u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(hwnd)

def find_window(title_part):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        t = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, t, 256)
        if title_part in t.value and u.IsWindowVisible(h): out.append(h)
        return True
    u.EnumWindows(cb, 0); return out
