import re

class AIBaseClient:
    """基礎 AI 客戶端，包含共用的情緒與文字解析邏輯"""
    
    def _parse_response(self, raw_text):
        """
        容錯解析器：將 "[angry] 你又在玩遊戲！" 拆成 ("angry", "你又在玩遊戲！")
        """
        # 使用正則表達式尋找 [xxx] 格式
        match = re.search(r'\[([a-zA-Z]+)\](.*)', raw_text, re.DOTALL)
        
        if match:
            emotion = match.group(1).lower()
            text = match.group(2).strip()
            
            # 限制合法的情緒標籤，確保這些標籤能對應到 Live2D 裡的 motion 或 expression 名稱
            valid_emotions = ["happy", "angry", "curious", "idle", "shocked", "laugh", "sad"]
            
            if emotion not in valid_emotions:
                # 如果 AI 發明了奇怪的標籤，預設回到 idle 狀態
                emotion = "idle"
                
            return emotion, text
        else:
            # 如果 AI 忘記加標籤，預設給 idle 動作，並把全部文字當作台詞
            return "idle", raw_text.strip()


class OllamaClient(AIBaseClient):
    """本地端 Ollama 模型呼叫客戶端 (免費、隱私度高、吃本機顯卡)"""
    
    def __init__(self, model_name="qwen2.5"):
        try:
            import ollama
            self.ollama = ollama
        except ImportError:
            raise ImportError("請先安裝套件：pip install ollama")
            
        self.model_name = model_name

    def get_reaction(self, prompt):
        try:
            response = self.ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一個傲嬌桌寵，必須嚴格按照 [情緒] 台詞 的格式回覆，情緒標籤限用英文。字數控制在 20 字以內。"},
                    {"role": "user", "content": prompt}
                ]
            )
            raw_text = response['message']['content']
            return self._parse_response(raw_text)
            
        except Exception as e:
            print(f"[Ollama 錯誤] {e}")
            return "sad", "大腦連線失敗，請確認你已經在終端機啟動了 Ollama 模型..."


class OpenAIClient(AIBaseClient):
    """雲端 OpenAI 模型呼叫客戶端 (需 API Key、極快且聰明)"""
    
    def __init__(self, api_key, model_name="gpt-4o-mini"):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("請先安裝套件：pip install openai")
            
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def get_reaction(self, prompt):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是一個傲嬌桌寵，必須嚴格按照 [情緒] 台詞 的格式回覆，情緒標籤限用英文。字數控制在 20 字以內。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,       # 限制輸出的字數
                temperature=0.8      # 稍微調高數值，讓回答更有變化與創意
            )
            raw_text = response.choices[0].message.content
            return self._parse_response(raw_text)
            
        except Exception as e:
            print(f"[OpenAI 錯誤] {e}")
            return "sad", "網路好像斷了，我連不上雲端大腦..."