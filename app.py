import os
import time
import json
import asyncio
import threading
import aiohttp
import websockets
from flask import Flask, request, jsonify, render_template

# Khởi tạo Flask. Nó sẽ tự động tìm file HTML trong thư mục 'templates'
app = Flask(__name__, template_folder='.')

# --- CLASS XỬ LÝ KẾT NỐI DISCORD (Giữ nguyên của bạn) ---
class DiscordVoiceBot:
    def __init__(self, token, guild_id, channel_id, mute=True, deaf=True, stream=False):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.mute = mute
        self.deaf = deaf
        self.stream = stream
        self.running = True
        self.ws = None
        self.heartbeat_interval = 0
        self.session_id = None

    async def get_gateway_url(self):
        headers = {"Authorization": self.token}
        async with aiohttp.ClientSession() as session:
            async with session.get("https://discord.com/api/v10/gateway", headers=headers) as res:
                if res.status == 200:
                    data = await res.json()
                    return data["url"] + "/?v=10&encoding=json"
                raise Exception("Token không hợp lệ hoặc bị từ chối")

    async def start_heartbeat(self):
        while self.running and self.ws:
            if self.ws.close_code is not None:
                break
            try:
                await self.ws.send(json.dumps({"op": 1, "d": None}))
            except:
                break
            await asyncio.sleep(self.heartbeat_interval)

    async def join_voice(self):
        payload = {
            "op": 4,
            "d": {
                "guild_id": self.guild_id,
                "channel_id": self.channel_id,
                "self_mute": self.mute,
                "self_deaf": self.deaf,
                "self_video": self.stream,
                "self_stream": self.stream
            }
        }
        await self.ws.send(json.dumps(payload))

    async def connect(self):
        gateway_url = await self.get_gateway_url()
        self.ws = await websockets.connect(gateway_url, max_size=None, ping_interval=None)
        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": 0,
                "properties": {"os": "Windows", "browser": "Discord Client", "device": "Discord Client"}
            }
        }
        await self.ws.send(json.dumps(payload))

    async def handle_message(self, message):
        op = message.get("op")
        t = message.get("t")
        d = message.get("d")

        if op == 10:
            self.heartbeat_interval = d["heartbeat_interval"] / 1000
            asyncio.create_task(self.start_heartbeat())
        elif op == 0 and t == "READY":
            await self.join_voice()

    async def start(self):
        try:
            await self.connect()
            while self.running:
                msg = await self.ws.recv()
                data = json.loads(msg)
                await self.handle_message(data)
        except Exception as e:
            print(f"[Core Lỗi]: {e}")

def run_bot_thread(bot_obj):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot_obj.start())
    finally:
        loop.close()

# --- ĐỊNH TUYẾN WEB BẰNG FLASK ---

@app.route('/')
def home():
    # Lệnh này sẽ gọi file index.html nằm trong thư mục templates ra
    return render_template('index.html')

@app.route('/start_bot', methods=['POST'])
def start_bot():
    data = request.json
    token = data.get('token')
    guild_id = data.get('guild_id')
    channel_id = data.get('channel_id')
    mute = data.get('mute', True)
    deaf = data.get('deaf', True)
    stream = data.get('stream', False)

    try:
        bot = DiscordVoiceBot(token, guild_id, channel_id, mute, deaf, stream)
        t = threading.Thread(target=run_bot_thread, args=(bot,), daemon=True)
        t.start()
        return jsonify({"success": True, "message": "Thành công! Máy chủ đang chạy ngầm."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("="*60)
    print(f" ==> WEB APP ĐANG CHẠY TẠI: http://127.0.0.1:{port}")
    print("="*60)
    app.run(host='0.0.0.0', port=port, debug=False)