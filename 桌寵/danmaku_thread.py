import asyncio
import blivedm
import blivedm.models.web as web_models
from PySide6.QtCore import QThread, Signal

class BilibiliDanmakuClient(blivedm.BLiveClient):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
 
    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        # 型別提示要用 web_models.DanmakuMessage，不是 blivedm.DanmakuMessage
        self.callback(message.uname, message.msg)

class DanmakuMonitorThread(QThread):
    new_danmaku = Signal(str, str)

    def __init__(self, room_id):
        super().__init__()
        self.room_id = room_id
        self.loop = None
        self.client = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
 
        self.client = blivedm.BLiveClient(self.room_id)
        handler = MyDanmakuHandler(self._emit_danmaku)
        self.client.set_handler(handler)
        self.client.start()
 
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.client.stop_and_close())
            self.loop.close()

    def _emit_danmaku(self, uname, msg):
        self.new_danmaku.emit(uname, msg)

    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.wait()