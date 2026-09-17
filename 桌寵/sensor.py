import psutil
import win32gui
import win32process

class DesktopSensor:
    @staticmethod
    def get_active_window_info():
        """獲取當前聚焦視窗的執行檔名稱與標題"""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None
        title = win32gui.GetWindowText(hwnd)
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            app_name = process.name()
            return app_name, title
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None, title

    @staticmethod
    def analyze_bilibili_live(app_name, window_title):
        """特化解析：判斷是否為 B 站直播並提取資訊"""
        browsers = ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]
        if not app_name or app_name.lower() not in browsers:
            return None

        if "哔哩哔哩直播" in window_title or "bilibili直播" in window_title.lower():
            parts = window_title.split(" - ")
            if len(parts) >= 3:
                streamer_name = parts[-2]
                room_title = parts[0]
                return streamer_name, room_title
            return "某個主播", "未知直播"
        return None