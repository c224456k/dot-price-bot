import discord
import google.generativeai as genai
import os

# 雲端版：從環境變數讀取 Key
GENAI_API_KEY = os.getenv("GENAI_API_KEY") 
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

intents = discord.Intents.default()
intents.message_content = True 
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'{client.user} 已上線 (雲端版 - Async 優化版)')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        user_input = message.content.replace(f'<@{client.user.id}>', '').strip()
        
        # 顯示輸入中...
        async with message.channel.typing():
            try:
                # 【修改重點】
                # 1. 加了 await (非同步等待)
                # 2. 改用 generate_content_async (非同步函式)
                # 這樣機器人等待時，還能同時處理 Discord 的心跳，不會卡住
                response = await model.generate_content_async(user_input)
                
                await message.channel.send(response.text, reference=message)
            except Exception as e:
                print(f"錯誤: {e}")
                # 避免錯誤訊息太長灌爆頻道，只印簡單的
                await message.channel.send("AI 思考時發生了一點錯誤，請稍後再試。")

if DISCORD_TOKEN:
    client.run(DISCORD_TOKEN)