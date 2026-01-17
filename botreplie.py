import discord
import google.generativeai as genai
import os # 引入作業系統模組

# --- 改成從環境變數讀取 ---
# 本地端測試時，如果不設環境變數會讀不到，建議先保留字串測試，
# 但上傳前請務必改成 os.getenv
GENAI_API_KEY = os.getenv("GENAI_API_KEY") 
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

intents = discord.Intents.default()
intents.message_content = True 
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'{client.user} 已上線 (雲端版)')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if client.user in message.mentions:
        user_input = message.content.replace(f'<@{client.user.id}>', '').strip()
        try:
            response = model.generate_content(user_input)
            await message.channel.send(response.text, reference=message)
        except Exception as e:
            print(e)

# 啟動
if DISCORD_TOKEN:
    client.run(DISCORD_TOKEN)
else:
    print("錯誤：找不到 DISCORD_TOKEN")
