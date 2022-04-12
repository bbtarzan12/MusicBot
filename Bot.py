import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from configparser import ConfigParser

load_dotenv(verbose=True)
config = ConfigParser()
config.read('setting.ini')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

def get_prefix(bot, msg):
    prefixes = ['$']
    return commands.when_mentioned_or(*prefixes)(bot, msg)

bot = commands.Bot(command_prefix=get_prefix, description='PangPang Music Bot', intents=intents)

@bot.event
async def on_ready():
    activity_type = discord.ActivityType.listening
    song_name='/play | PangPang'
    await bot.change_presence(activity=discord.Activity(type=activity_type,name=song_name))

@bot.event
async def on_command_error(ctx, error):
    return await ctx.reply(f"""
    ⚠️ 안녕하세요! HyePang 음악 봇 사용법이 바뀌었어요 ⚠️

    *디스코드에서 접두사를 이용한 명령어 사용이 곧 제한됨*

    기존에 사용하던 **$** 접두사를 **/(슬래시)**로 바꿔서 사용해주세요!
    ```
    /play 노래
    /search 노래
    /clear
    /queue
    /join
    /leave
    ... 등등```""")

exts=['Music']

for ext in exts:
    bot.load_extension(ext)


bot.run(os.getenv('BOT_TOKEN'))