import threading
import http.server
import socketserver
import sys
import os
import json
import time
import random
import urllib.request
import urllib.error
from collections import deque
from PySide6.QtCore import Qt, QPoint, QPointF, QObject, Slot, QUrl, QTimer, QThread, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QInputDialog
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineCore import QWebEngineSettings

from monitor_thread import DesktopMonitorThread
from danmaku_thread import DanmakuMonitorThread
from ai_logic import AIPromptGenerator

GRAVITY = 1400.0          # px/s^2
RESTITUTION = 0.78        # 落地反弹保留的速度比例
GROUND_FRICTION = 2.5     # 贴地滑行时的减速系数（越大停得越快）
THROW_POWER = 1.0         # 甩出去初速度的整体倍率
FLING_MIN_SPEED = 60.0    # 松手时低于这个速度就当作普通放下，不触发抛物线
STOP_SPEED = 15.0         # 速度衰减到这个值以下就停止动画
FLING_TICK_MS = 16        # 抛掷动画的帧间隔（约 60fps）

def start_local_server(directory, port=8000):
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=directory, **kwargs
    )
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return port

class ChatWorker(QThread):
    """
    手机『聊天』訊息串用的背景執行緒：AI 呼叫（Ollama/OpenAI）可能要等個一兩秒，
    放主執行緒會把整個透明視窗卡死（拖拽/動畫都會頓住），所以丟到子執行緒跑，
    跑完用 signal 把結果丟回主執行緒去更新網頁。
    """
    result_ready = Signal(str, str)  # emotion, text
 
    def __init__(self, ai_client, prompt_gen, user_text, parent=None):
        super().__init__(parent)
        self.ai_client = ai_client
        self.prompt_gen = prompt_gen
        self.user_text = user_text
 
    def run(self):
        try:
            prompt = self.prompt_gen.get_chat_reaction(self.user_text)
            emotion, reply = self.ai_client.get_reaction(prompt)
        except Exception as e:  # noqa: BLE001 - 聊天失敗要讓使用者看到原因，不要吞掉
            emotion, reply = "sad", f"糟糕，我腦袋短路了：{e}"
        self.result_ready.emit(emotion, reply)

class WebBridge(QObject):
    """Python 與前端 JavaScript 通訊的橋樑"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = None
        # 天气配置：先写死一组经纬度当默认值，之后可以改成读设定档
        self.weather_lat = 30.75
        self.weather_lon = 120.75
        self._weather_cache = None
        self._weather_cache_at = 0
        # 手机聊天：由 DesktopPetWindow 注入实际处理函式（需要 monitor_thread 的 ai_client/prompt_gen）
        self.chat_handler = None
 
    # ---------- 手机『聊天』：JS 呼叫送出文字，回覆用 receiveChatReply() 從 Python 主動推回去 ----------
    @Slot(str)
    def send_chat_message(self, text):
        if self.chat_handler:
            self.chat_handler(text)
 
    def trigger_action(self, emotion, text):
        if self.page:
            safe_text = text.replace("'", "\\'")
            js_code = f"playAction('{emotion}', '{safe_text}');"
            self.page.runJavaScript(js_code)

    # ---------- 天气：手机面板点天气角标时前端会呼叫这个 slot ----------
    @Slot(result=str)
    def get_weather(self):
        """
        回傳 JSON 字串（前端自己 JSON.parse）。
        用 Open-Meteo（免 API key、免註冊），10 分鐘內重複呼叫直接吃快取，
        避免手機面板開開關關就一直打外部 API。
        """
        now = time.time()
        if self._weather_cache and (now - self._weather_cache_at) < 600:
            return json.dumps(self._weather_cache, ensure_ascii=False)
 
        try:
            url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.weather_lat}&longitude={self.weather_lon}"
                "&current=temperature_2m,weather_code,relative_humidity_2m"
                "&timezone=auto"
            )
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            current = data.get("current", {})
            result = {
                "ok": True,
                "temp": current.get("temperature_2m"),
                "humidity": current.get("relative_humidity_2m"),
                "code": current.get("weather_code"),
            }
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            result = {"ok": False, "error": str(e)}
 
        self._weather_cache = result
        self._weather_cache_at = now
        return json.dumps(result, ensure_ascii=False)

class DesktopPetWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 1. 視窗基礎設定：無邊框、置頂、背景透明、不在工作列顯示
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(400, 500)
        self.drag_position = QPoint()

         # ---------- 甩出去用的状态 ----------
        self._dragging = False
        self._drag_samples = deque(maxlen=5)  # 每个元素 (globalPos: QPointF, timestamp: float)
        self._fling_vx = 0.0
        self._fling_vy = 0.0
        self._fling_timer = QTimer(self)
        self._fling_timer.setInterval(FLING_TICK_MS)
        self._fling_timer.timeout.connect(self._fling_tick)
        self._fling_last_tick = 0.0

        # 2. 初始化 QWebEngineView
        self.browser = QWebEngineView(self)
        self.browser.resize(400, 500)
        self.browser.page().setBackgroundColor(Qt.GlobalColor.transparent)
        # 关掉网页内建的原生右键菜单——右键改由网页端的「手机面板」接管（见 index.html）
        self.browser.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        
        # 3. 建立 QWebChannel 橋樑
        self.bridge = WebBridge()
        self.bridge.page = self.browser.page()
        self.channel = QWebChannel()
        self.channel.registerObject("backend_bridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)

        # 4.解除本地檔案讀取限制，讓網頁可以載入本地的 Live2D 模型
        settings = self.browser.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        # 5. 載入本地端的 HTML 檔案
        port = start_local_server(os.path.abspath("."))
        self.browser.load(QUrl(f"http://127.0.0.1:{port}/index.html"))

        # 6. 啟動桌面監控背景線程（大腦與環境感知）
        self.monitor_thread = DesktopMonitorThread()
        self.monitor_thread.trigger_speech.connect(self.on_pet_speak)
        self.monitor_thread.start()

        # 預留彈幕監控線程變數
        self.danmaku_thread = None
        
        # 7. 接上手机『聊天』：跟碎碎念共用同一个 ai_client/prompt_gen，但走独立的訊息串通道
        self.bridge.chat_handler = self._on_chat_message
        self._chat_workers = []  # 保留參照，避免執行緒跑到一半被 GC 回收
    
    def _on_chat_message(self, user_text):
        worker = ChatWorker(
            self.monitor_thread.ai_client,
            self.monitor_thread.prompt_gen,
            user_text,
        )
        worker.result_ready.connect(self._on_chat_reply)
        worker.finished.connect(lambda: self._chat_workers.remove(worker) if worker in self._chat_workers else None)
        self._chat_workers.append(worker)
        worker.start()
        
    def _on_chat_reply(self, emotion, text):
        # 注意：這裡刻意呼叫 receiveChatReply（推進手機訊息串），
        # 不呼叫 playAction（那個是浮動氣泡，屬於『看你做事』的碎碎念專用通道）
        safe_text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        safe_emotion = emotion.replace("'", "")
        js = f"window.receiveChatReply && window.receiveChatReply('{safe_emotion}', '{safe_text}');"
        self.browser.page().runJavaScript(js)
    
    def on_pet_speak(self, emotion, text, event_type):
        """接收 AI 產生的對話並執行動作（唯一版本，之前重複定義的另一個版本已刪除）"""
        print(f"[桌寵發話] 表情: {emotion} | 內容: {text}")
        self.bridge.trigger_action(emotion, text)

        if event_type == "bilibili_start" and not self.danmaku_thread:
            print("啟動彈幕監聽...")
            room_id = 213  # TODO: 換成從視窗標題解析出來的真實房間號
            self.danmaku_thread = DanmakuMonitorThread(room_id)
            self.danmaku_thread.new_danmaku.connect(self.on_danmaku_received)
            self.danmaku_thread.start()

        elif event_type == "app_focus" and self.danmaku_thread:
            print("離開直播間，關閉彈幕監聽...")
            self.danmaku_thread.stop()
            self.danmaku_thread = None

    def on_danmaku_received(self, uname, msg):
        """處理接收到的即時彈幕"""
        if random.random() < 0.01:
            prompt = AIPromptGenerator().get_danmaku_reaction("主播", msg)
            print(f"[彈幕吐槽觸發] {prompt}")

            # TODO: 這裡應串接真實的非同步 AI 呼叫，目前先用模擬回應
            emotion = "curious"
            text = f"居然有人說「{msg[:10]}」，真是有趣！"
            self.bridge.trigger_action(emotion, text)

    # ---------- 拖拽 + 甩出去 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._stop_fling()  # 正在飞的时候被抓住 → 立刻停下来给她抓
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragging = True
            self._drag_samples.clear()
            self._drag_samples.append((event.globalPosition(), time.monotonic()))
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            self._drag_samples.append((event.globalPosition(), time.monotonic()))
            event.accept()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            vx, vy = self._estimate_velocity()
            speed = (vx ** 2 + vy ** 2) ** 0.5
            if speed >= FLING_MIN_SPEED:
                self._start_fling(vx * THROW_POWER, vy * THROW_POWER)
            event.accept()
            
    def _estimate_velocity(self):
        """用最近幾筆拖拽採樣算放手瞬間的速度（px/s）。樣本太少就當作沒有甩。"""
        samples = list(self._drag_samples)
        if len(samples) < 2:
            return 0.0, 0.0
        (p0, t0), (p1, t1) = samples[-2], samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0, 0.0
        vx = (p1.x() - p0.x()) / dt
        vy = (p1.y() - p0.y()) / dt
        return vx, vy
 
    def _start_fling(self, vx, vy):
        self._fling_vx = vx
        self._fling_vy = vy
        self._fling_last_tick = time.monotonic()
        self._fling_timer.start()
 
    def _stop_fling(self):
        if self._fling_timer.isActive():
            self._fling_timer.stop()
 
    def _fling_tick(self):
        now = time.monotonic()
        dt = now - self._fling_last_tick
        self._fling_last_tick = now
        if dt <= 0:
            return
 
        screen = self.screen() or QApplication.primaryScreen()
        area = screen.availableGeometry()
 
        # 重力
        self._fling_vy += GRAVITY * dt
 
        pos = self.pos()
        new_x = pos.x() + self._fling_vx * dt
        new_y = pos.y() + self._fling_vy * dt
 
        w = self.width()
        h = self.height()
        min_x, max_x = area.x(), area.x() + area.width() - w
        min_y, max_y = area.y(), area.y() + area.height() - h
 
        # 落地/触边反弹
        if new_y >= max_y:
            new_y = max_y
            if self._fling_vy > 0:
                self._fling_vy = -self._fling_vy * RESTITUTION
            # 贴地时对水平速度施加摩擦力
            friction = GROUND_FRICTION * dt * 100
            if self._fling_vx > 0:
                self._fling_vx = max(0.0, self._fling_vx - friction)
            elif self._fling_vx < 0:
                self._fling_vx = min(0.0, self._fling_vx + friction)
        elif new_y <= min_y:
            new_y = min_y
            self._fling_vy = -self._fling_vy * RESTITUTION
 
        if new_x >= max_x:
            new_x = max_x
            self._fling_vx = -self._fling_vx * RESTITUTION
        elif new_x <= min_x:
            new_x = min_x
            self._fling_vx = -self._fling_vx * RESTITUTION
 
        self.move(int(new_x), int(new_y))
 
        speed = (self._fling_vx ** 2 + self._fling_vy ** 2) ** 0.5
        resting_on_ground = abs(new_y - max_y) < 0.5
        if speed < STOP_SPEED and resting_on_ground:
            self._fling_vx = 0.0
            self._fling_vy = 0.0
            self._stop_fling()

    def contextMenuEvent(self, event):
        # 右键已经交给网页端的手机面板处理（见 index.html 的 contextmenu 监听），
        # 这里保留一个极简的 Qt 原生菜单只当保险丝：万一网页那层挂了还能关掉程式。
        menu = QMenu(self)
        quit_action = menu.addAction("關閉桌寵（保險選單）")
        action = menu.exec(self.mapToGlobal(event.pos()))
        if action == quit_action:
            self.close()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    pet = DesktopPetWindow()
    pet.show()
    sys.exit(app.exec())