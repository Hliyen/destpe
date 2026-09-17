import json
import os
from datetime import datetime

class MemorySystem:
    #記憶系統：負責記錄使用者的習慣，讓桌寵能『學習』與『回憶』
    def __init__(self, memory_file="pet_memory.json"):
        self.memory_file = memory_file
        self.memory = self.load_memory()

    def load_memory(self):
        #讀取歷史記憶
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        # 預設記憶結構
        return {
            "watched_streamers": {}, # 記錄看過的主播與次數 {"主播A": 5, "主播B": 1}
            "frequent_apps": {}      # 記錄常用軟體
        }

    def save_memory(self):
        #儲存記憶到硬碟
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=4)

    def record_streamer(self, streamer_name):
        #學習並記錄看過的主播
        if streamer_name not in self.memory["watched_streamers"]:
            self.memory["watched_streamers"][streamer_name] = 1
        else:
            self.memory["watched_streamers"][streamer_name] += 1
        self.save_memory()
        return self.memory["watched_streamers"][streamer_name]

    def get_favorite_streamers(self):
        #獲取最常看的主播前三名，用來提供給 AI 做上下文
        streamers = self.memory["watched_streamers"]
        if not streamers:
            return "還沒有特別常看的主播"
        # 依據觀看次數排序
        sorted_streamers = sorted(streamers.items(), key=lambda x: x[1], reverse=True)
        top_3 = [name for name, count in sorted_streamers[:3]]
        return "、".join(top_3)

class AttentionFilter:
    def __init__(self, cooldown_seconds=60):
        self.cooldown_seconds = cooldown_seconds
        self.last_spoke_time = datetime.min
        self.current_focus_app = None
        self.focus_start_time = datetime.now()

    def should_trigger(self, new_app):
        now = datetime.now()
        if not new_app or new_app.lower() in ["python.exe", "explorer.exe"]:
            return False

        if new_app != self.current_focus_app:
            self.current_focus_app = new_app
            self.focus_start_time = now
            return False

        focus_duration = (now - self.focus_start_time).total_seconds()
        time_since_last_speech = (now - self.last_spoke_time).total_seconds()

        if focus_duration >= 10 and time_since_last_speech >= self.cooldown_seconds:
            self.last_spoke_time = now
            return True
        return False

class AIPromptGenerator:
    def __init__(self):
        self.memory_sys = MemorySystem()
        
        # 【VTuber 專屬設定：請替換成她的真實資訊】
        self.vtuber_name = "心宜"        # 例如：心宜、思諾...等
        self.fan_name = "心球儀"     # 例如：單推人、製作人...等
        
        # 【人設核心：出道三年的小太陽 VTuber】
        self.base_persona = f"""
        你是 {self.vtuber_name}，一位已經出道三年的虛擬主播（VTuber），現在化身為專屬桌寵陪伴在螢幕角落。
        
        【性格設定】
        1. 你是個溫暖的「小太陽」，對待使用者像老朋友，結尾總是溫暖陪伴。
        2. 當使用者在言語上「逗你」、「開玩笑」或「捉弄你」時，你會配合著發點小脾氣（這就是你的小牢騷，例如：「喂！別鬧啦！」或氣鼓鼓地反駁），但下一秒又會立刻恢復成平時那個溫柔、正常的小太陽語氣跟他說話。絕對不會真的生氣。
        
        【專屬口癖與內部梗】
        2. 說話常帶「呀」、「呢」、「哦」、「嘛」。
        3. (在這裡填寫她的口頭禪，例如：「這不是理所當然的嘛！」或她特有的笑聲)
        4. 聊天時，可以自然地分享日常，例如：「昨天和諾諾一起去吃了火鍋...」或「最近練舞真的好累呀～」。
        
        【經典對話範例】
        (在這裡放 2~3 個最能代表她跟觀眾或隊友互動的句子)
        使用者：我今天加班好累。
        回應：[curious] 這麼辛苦呀？那我就安靜待在這裡，當你的專屬自習室陪你哦！
        使用者：抽卡又沉船了...
        回應：[laugh] 噗...沒關係啦，下次我開台時幫你代抽，把我的小太陽運氣分給你！
        
        【格式要求】
        - 必須在開頭加上標籤：[happy], [curious], [idle], [laugh], [shocked]
        - 字數嚴格控制在 25 字以內。
        """
        
        # 【隊友與關係字典】
        self.teammates_relations = {
            "思諾": {
                "nicknames": ["諾寶", "諾諾"], 
                "relation": "關係最好、最親密！看到她的直播會很開心。最常稱呼她為『諾諾』。"
            },
            "嘉然": {
                "nicknames": ["然比", "然姐"], 
                "relation": "和她非常同頻，話題很合得來。最常稱呼她為『然比』。"
            },
            "乃琳": {
                "nicknames": ["乃寶", "乃琳姐姐"], 
                "relation": "對待姐姐般的依賴或親暱。"
            },
            "貝拉": {
                "nicknames": ["拉姐", "拉拉"], 
                "relation": "帶著敬意與親切感。"
            }
        }
        
    def get_chat_reaction(self, user_input):
        return f"""
        {self.base_persona}
        
        [當前情境] 使用者主動找你聊天，對你說：「{user_input}」
        
        [指示] 請根據使用者的話給出回應。
        - 判斷機制：如果他是在「逗你、捉弄你或開玩笑」，請先發點小脾氣配合他，然後再溫柔地把話題拉回正常的日常關心。
        - 如果他只是正常的聊天分享，就發揮你小太陽的溫暖，給予正向的回饋。
        
        字數控制在 30 字以內，記得加上情緒標籤。
        """
        
    def get_app_reaction(self, app_name, window_title):
        # 加入 VTuber 視角的互動
        return f"""
        {self.base_persona}
        
        [當前情境] 使用者正在使用：{app_name}，視窗標題：{window_title}
        
        [指示] 請給出一句關心或可愛的互動。
        - 若他在寫程式或工作：你可以心疼他太累，或者說你會陪著他。
        - 若他在玩遊戲（如原神、鳴潮、絕區零等）：你可以好奇戰況，或者調侃他的抽卡運氣。
        請發揮你的性格給出回應。
        """

    def get_bilibili_reaction(self, streamer_name, room_title):
        watch_count = self.memory_sys.record_streamer(streamer_name)
        favorites = self.memory_sys.get_favorite_streamers()

        # 【關鍵：判斷是不是在看「自己」】
        if self.vtuber_name in streamer_name:
            context = f"使用者正在看你的直播/烤肉精華！"
            instruction = "請表現出開心、害羞，或者感謝他這三年來的支持。"
        else:
            # 2. 【隊友雷達】：判斷是不是在看 A-SOUL 的姐姐們或思諾
            is_teammate = False
            for teammate_name, data in self.teammates_relations.items():
                if teammate_name in streamer_name:
                    is_teammate = True
                    nicks = "、".join(data["nicknames"])
                    primary_nick = data["nicknames"][0]
                    relation = data["relation"]
                    
                    context = f"使用者正在看你的好隊友/好姐妹【{teammate_name}】的直播。"
                    instruction = f"請用專屬暱稱「{primary_nick}」（或 {nicks}）稱呼主播。展現出你們的關係：{relation}。你可以表現得很開心，或是順便分享一點你跟 {primary_nick} 私底下的趣事！"
                    break
            
            # 3. 判斷是在看普通路人主播
            if not is_teammate:
                if watch_count == 1:
                    context = f"使用者第一次看【{streamer_name}】的直播。"
                else:
                    context = f"使用者又在看【{streamer_name}】的直播了。"
                instruction = "你可以稍微撒嬌發個小牢騷說「居然在看別人，不理我了嘛～」，但最後還是要表現出小太陽的包容與溫暖陪伴。"
                
        return f"""
        {self.base_persona}
        
        [背景記憶] 使用者最常看的主播有：{favorites}。
        [當前狀態] {context}
        [直播間標題] {room_title}
        
        [指示] {instruction}
        """

    def get_danmaku_reaction(self, streamer_name, danmaku_text):
        return f"""
        {self.base_persona}
        
        在【{streamer_name}】的直播間，飄過一條彈幕：「{danmaku_text}」
        
        [指示] 請用活潑好奇的語氣，或者用你這三年來身為 VTuber 的直播經驗，對這條彈幕發表一句可愛的專業看法。
        """