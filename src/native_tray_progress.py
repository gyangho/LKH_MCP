"""Small native Windows shutdown progress window; no Tcl/Tk runtime dependency."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import queue
import threading


class ProgressFailure(RuntimeError):
    def __init__(self, operation_started):
        self.operation_started = operation_started
        super().__init__("Native shutdown progress unavailable")


def show_shutdown_progress(operation, *, title="LKH MCP 종료 중", initial_message="종료 준비 중…", stages=None):
    """Run operation(report) off the UI thread; return its safe error string or None."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    controls = ctypes.WinDLL("comctl32", use_last_error=True)
    result_type = ctypes.c_ssize_t
    callback_type = ctypes.WINFUNCTYPE(result_type, wintypes.HWND, wintypes.UINT,
                                       wintypes.WPARAM, wintypes.LPARAM)

    class WindowClass(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("procedure", callback_type),
                    ("class_extra", ctypes.c_int), ("window_extra", ctypes.c_int),
                    ("instance", wintypes.HINSTANCE), ("icon", wintypes.HANDLE),
                    ("cursor", wintypes.HANDLE), ("background", wintypes.HANDLE),
                    ("menu", wintypes.LPCWSTR), ("name", wintypes.LPCWSTR)]

    class ControlClasses(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("classes", wintypes.DWORD)]

    kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel.GetModuleHandleW.restype = wintypes.HMODULE
    user.RegisterClassW.argtypes = [ctypes.POINTER(WindowClass)]
    user.RegisterClassW.restype = wintypes.ATOM
    user.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user.UnregisterClassW.restype = wintypes.BOOL
    user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user.CreateWindowExW.restype = wintypes.HWND
    user.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.DefWindowProcW.restype = result_type
    user.DestroyWindow.argtypes = [wintypes.HWND]
    user.DestroyWindow.restype = wintypes.BOOL
    user.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user.SetWindowTextW.restype = wintypes.BOOL
    user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.SendMessageW.restype = result_type
    user.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
    user.SetTimer.restype = ctypes.c_size_t
    user.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    user.KillTimer.restype = wintypes.BOOL
    user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user.GetMessageW.restype = ctypes.c_int
    user.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user.DispatchMessageW.restype = result_type
    user.PostQuitMessage.argtypes = [ctypes.c_int]
    user.GetSystemMetrics.argtypes = [ctypes.c_int]
    user.GetSystemMetrics.restype = ctypes.c_int
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.UpdateWindow.argtypes = [wintypes.HWND]
    controls.InitCommonControlsEx.argtypes = [ctypes.POINTER(ControlClasses)]
    controls.InitCommonControlsEx.restype = wintypes.BOOL
    init = ControlClasses(ctypes.sizeof(ControlClasses), 0x20)  # ICC_PROGRESS_CLASS
    if not controls.InitCommonControlsEx(ctypes.byref(init)):
        raise RuntimeError("Progress control initialization failed")

    events = queue.Queue()
    state = {"text": None, "bar": None, "error": "종료 결과를 확인하지 못했습니다.",
             "completed": False, "destroyed": False, "started": False}
    stages = stages or (("서버 연결", 10), ("Agent 작업 스케줄러", 25), ("Agent 중지", 45),
                        ("Windows 관리자", 65), ("MCP 서버 서비스", 85))

    @callback_type
    def procedure(window, message, wparam, lparam):
        if message == 0x10:  # WM_CLOSE: closing a window cannot cancel an SCM request.
            return 0
        if message == 0x113:  # WM_TIMER, queue is consumed only by the UI owner thread.
            try:
                while True:
                    kind, value = events.get_nowait()
                    if kind == "progress":
                        user.SetWindowTextW(state["text"], value)
                        position = next((position for prefix, position in stages if value.startswith(prefix)), 10)
                        user.SendMessageW(state["bar"], 0x402, position, 0)  # PBM_SETPOS
                    else:
                        state["error"], state["completed"] = value, True
                        user.SendMessageW(state["bar"], 0x402, 100, 0)
                        user.DestroyWindow(window)
                        return 0
            except queue.Empty:
                pass
            return 0
        if message == 2:  # WM_DESTROY
            state["destroyed"] = True
            user.KillTimer(window, 1)
            user.PostQuitMessage(0)
            return 0
        return user.DefWindowProcW(window, message, wparam, lparam)

    instance = kernel.GetModuleHandleW(None)
    name = "LKHShutdownProgress" + str(threading.get_ident())
    definition = WindowClass(0, procedure, 0, 0, instance, None, None, 6, None, name)
    if not user.RegisterClassW(ctypes.byref(definition)):
        raise RuntimeError("Shutdown progress registration failed")
    window = None
    try:
        width, height = 560, 190
        x = max(0, (user.GetSystemMetrics(0) - width) // 2)
        y = max(0, (user.GetSystemMetrics(1) - height) // 2)
        window = user.CreateWindowExW(0x8, name, title, 0x00C00000,
                                     x, y, width, height, None, None, instance, None)
        if not window:
            raise RuntimeError("Shutdown progress creation failed")
        child_style = 0x40000000 | 0x10000000
        state["text"] = user.CreateWindowExW(0, "STATIC", initial_message, child_style,
            18, 20, 520, 46, window, None, instance, None)
        state["bar"] = user.CreateWindowExW(0, "msctls_progress32", "", child_style,
            18, 75, 520, 22, window, None, instance, None)
        note = user.CreateWindowExW(0, "STATIC", "진행 막대는 처리 단계를 표시합니다. 완료까지 기다려 주세요.",
            child_style, 18, 112, 520, 28, window, None, instance, None)
        if not state["text"] or not state["bar"] or not note:
            raise RuntimeError("Shutdown progress controls unavailable")
        user.SendMessageW(state["bar"], 0x406, 0, 100)  # PBM_SETRANGE32
        if not user.SetTimer(window, 1, 100, None):
            raise RuntimeError("Shutdown progress timer unavailable")
        user.ShowWindow(window, 5)
        user.UpdateWindow(window)

        def work():
            error = "종료 처리 중 오류가 발생했습니다. 트레이 로그를 확인하세요."
            try:
                error = operation(lambda text: events.put(("progress", text)))
            finally:
                events.put(("complete", error))

        threading.Thread(target=work, daemon=True, name="LKH-Tray-Shutdown").start()
        state["started"] = True
        message = wintypes.MSG()
        while True:
            code = user.GetMessageW(ctypes.byref(message), None, 0, 0)
            if code == 0:
                break
            if code == -1:
                raise RuntimeError("Shutdown progress message loop failed")
            user.TranslateMessage(ctypes.byref(message))
            user.DispatchMessageW(ctypes.byref(message))
        return state["error"] if state["completed"] else "종료 진행창이 예기치 않게 닫혔습니다."
    except Exception:
        raise ProgressFailure(state["started"]) from None
    finally:
        if window and not state["destroyed"]:
            user.DestroyWindow(window)
        user.UnregisterClassW(name, instance)
