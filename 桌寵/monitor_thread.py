from PySide6.QtCore import QThread, Signal
from ai_logic import AIPromptGenerator, AttentionFilter
from sensor import DesktopSensor
from llm_client import OllamaClient
import time


class DesktopMonitorThread(QThread):
    # 信號：情緒標籤, 說話文字, 事件類型(App/Bilibili)
    trigger_speech = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.sensor = DesktopSensor()
        self.filter = AttentionFilter(cooldown_seconds=60)
        self.prompt_gen = AIPromptGenerator()

        self.ai_client = OllamaClient(model_name="qwen2.5")
        self.running = True

        # 紀錄當前是否在看 B 站，避免重複觸發
        self.watching_bilibili = False

    def run(self):
        last_interact_time = time.time()

        while self.running:
            # 每次迴圈開始時重置旗標（這是原本遺漏的變數，補上）
            event_triggered = False

            app, title = self.sensor.get_active_window_info()

            if not app:
                self.msleep(2000)
                continue

            # 1. 優先檢查是否為 B 站直播
            bilibili_info = self.sensor.analyze_bilibili_live(app, title)

            if bilibili_info:
                streamer, room_title = bilibili_info
                if not self.watching_bilibili:  # 剛切換到直播間
                    self.watching_bilibili = True
                    prompt = self.prompt_gen.get_bilibili_reaction(streamer, room_title)
                    emotion, text = self.ai_client.get_reaction(prompt)
                    self.trigger_speech.emit(emotion, text, "bilibili_start")
                    event_triggered = True
            else:
                self.watching_bilibili = False
                # 2. 一般程式狀態檢查
                if self.filter.should_trigger(app):
                    prompt = self.prompt_gen.get_app_reaction(app, title)
                    emotion, text = self.ai_client.get_reaction(prompt)
                    self.trigger_speech.emit(emotion, text, "app_focus")
                    event_triggered = True

            if event_triggered:
                last_interact_time = time.time()

            # 【閒置碎碎念】如果超過 300 秒 (5分鐘) 沒有任何新事件
            if time.time() - last_interact_time > 300:
                print("[系統] 觸發閒置碎碎念")
                prompt = "使用者已經 5 分鐘沒有切換視窗了，請用傲嬌語氣發個牢騷，刷一下存在感。"
                emotion, text = self.ai_client.get_reaction(prompt)
                self.trigger_speech.emit(emotion, text, "whisper")
                last_interact_time = time.time()

            self.msleep(2000)

    def stop(self):
        self.running = False
        self.wait()