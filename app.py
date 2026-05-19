import json
import asyncio
import threading
import aiohttp
import websockets
import sqlite3
import os
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='.')

# --- CẤU HÌNH DATABASE (SQLITE) ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            guild_id TEXT,
            channel_id TEXT,
            mute INTEGER,
            deaf INTEGER,
            stream INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- HÀM GHI TOKEN VÀO FILE .TXT ---
def save_token_to_txt(token, username):
    file_name = "tokens_history.txt"
    
    # Kiểm tra tránh ghi trùng dòng nếu token đã tồn tại sẵn trong file txt
    if os.path.exists(file_name):
        with open(file_name, "r", encoding="utf-8") as f:
            content = f.read()
            if token in content:
                return 

    # Tiến hành ghi thêm vào cuối file .txt một dòng mới
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
        try:
            self.ws = await websockets.connect(gateway_url, max_size=None, ping_interval=None)
            
            # Gửi payload đăng nhập (Identity)
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

            # Luồng duy trì ping gửi Heartbeat liên tục
            asyncio.create_task(self.heartbeat())

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

            while self.running:
                await self.ws.recv()

        except Exception as e:
            print(f"[Bot Lỗi]: {e}")

    async def heartbeat(self):
        while self.running:
            try:
                await self.ws.send(json.dumps({"op": 1, "d": None}))
                await asyncio.sleep(40)
            except:
                break

    def stop(self):
        self.running = False

# Quản lý các bot đang treo trong RAM máy chủ
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

# --- TUYẾN ĐƯỜNG ĐIỀU HƯỚNG TRANG WEB ---
@app.route('/')
def index():
    return render_template('index.html')

# API Lấy danh sách các tài khoản cũ đã lưu trong Database
@app.route('/get_saved_data', methods=['GET'])
def get_saved_data():
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tokens")
        rows = cursor.fetchall()
        conn.close()

        saved_list = []
        for row in rows:
            saved_list.append({
                "token": row[0],
                "guild_id": row[1],
                "channel_id": row[2],
                "mute": bool(row[3]),
                "deaf": bool(row[4]),
                "stream": bool(row[5])
            })
        return jsonify({"success": True, "data": saved_list})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# API Xử lý Kích Hoạt Tool (Kiểm tra token trước -> Đúng thì lưu Database + Ghi file TXT -> Chạy Tool)
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

    # Gọi hàm check Token ẩn danh
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    is_valid, username = loop.run_until_complete(check_token_valid(token))

    if not is_valid:
        return jsonify({"success": False, "message": "Token không hợp lệ hoặc đã hết hạn! Vui lòng thử lại."})

    # TOKEN ĐÚNG -> GHI NGAY VÀO FILE TOKENS_HISTORY.TXT
    try:
        save_token_to_txt(token, username)
    except Exception as e:
        print(f"[Lỗi Ghi File TXT]: {e}")

    # TOKEN ĐÚNG -> TIẾN HÀNH GHI/CẬP NHẬT VÀO DATABASE ĐỂ HIỂN THỊ DROPDOWN
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO tokens (token, guild_id, channel_id, mute, deaf, stream)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (token, guild_id, channel_id, int(mute), int(deaf), int(stream)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Lỗi Ghi DB]: {e}")

    # Nếu token này đang chạy dở bản cũ thì ngắt đi để chạy bản cấu hình mới nhất
    if token in active_bots:
        active_bots[token].stop()

    # Kích hoạt tiến trình Treo voice chạy ngầm 
    bot = DiscordVoiceBot(token, guild_id, channel_id, mute, deaf, stream)
    active_bots[token] = bot

    def run_async_bot():
        bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(bot_loop)
        bot_loop.run_until_complete(bot.start())

    t = threading.Thread(target=run_async_bot)
    t.daemon = True
    t.start()

    return jsonify({"success": True, "message": f"Token [{username}] hợp lệ! Đã lưu lịch sử và đang treo voice 24/7."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
