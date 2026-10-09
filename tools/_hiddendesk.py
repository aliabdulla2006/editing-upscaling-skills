"""Run CapCut on an invisible second desktop (same Windows user/session) and talk to its windows."""
import ctypes, ctypes.wintypes as wt, os, time
u = ctypes.windll.user32; k = ctypes.windll.kernel32
DESK = "EcomCapCutDesk"

class STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
                ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE)]
class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]

u.CreateDesktopW.restype = wt.HANDLE
u.OpenDesktopW.restype = wt.HANDLE

def desktop():
    h = u.OpenDesktopW(DESK, 0, False, 0x10000000)  # GENERIC_ALL
    return h or u.CreateDesktopW(DESK, None, None, 0, 0x10000000, None)

def launch(exe, args="", env=None):
    hd = desktop()
    si = STARTUPINFO(); si.cb = ctypes.sizeof(si); si.lpDesktop = "WinSta0\\" + DESK
    pi = PROCESS_INFORMATION()
    envblock = None
    if env:
        envblock = ctypes.create_unicode_buffer("\0".join(f"{k_}={v}" for k_, v in env.items()) + "\0\0")
    cmd = ctypes.create_unicode_buffer(f'"{exe}" {args}')
    ok = k.CreateProcessW(None, cmd, None, None, False, 0x400 if env else 0, envblock, os.path.dirname(exe),
                          ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        raise OSError(ctypes.GetLastError())
    return pi.dwProcessId, hd

def windows(hd):
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if u.IsWindowVisible(h):
            t = ctypes.create_unicode_buffer(256); u.GetWindowTextW(h, t, 256)
            r = wt.RECT(); u.GetWindowRect(h, ctypes.byref(r))
            out.append(dict(hwnd=h, title=t.value, rect=(r.left, r.top, r.right, r.bottom)))
        return True
    u.EnumDesktopWindows(hd, cb, 0)
    return out
