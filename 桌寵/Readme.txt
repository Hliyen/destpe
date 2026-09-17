DesktopPet/
│
├── main.py                # 系統進入點 (主視窗、UI 渲染、JS 通訊橋樑)
├── monitor_thread.py      # 背景監控線程 (輪詢桌面狀態、呼叫 AI)
├── sensor.py              # 環境感知模組 (獲取前台視窗、解析 B 站標題)
├── ai_logic.py            # AI 決策模組 (冷卻過濾器、Prompt 提示詞生成)
├── danmaku_thread.py      # 彈幕連動模組 (B 站 WebSocket 連線與抽樣)
│
├── index.html             # 前端渲染介面 (Live2D 畫布、接收 Python 指令)
├── qwebchannel.js         # Qt 官方的 JS 橋樑檔案 (需從 PySide6 套件庫中複製過來)
│
└── assets/                # (你需要自己準備的) Live2D 模型資料夾
    └── your_model_name/
        ├── model3.json    # Live2D 模型設定檔 (index.html 裡要讀取的檔案)
        ├── *.moc3         # 模型核心檔
        ├── *.png          # 貼圖檔
        └── motions/       # 動作資料夾 (包含 .motion3.json)

live2D模型
https://booth.pm/en/search/live2d
https://www.live2d.com/zh-CHS/learn/sample/