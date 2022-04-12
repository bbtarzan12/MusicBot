import os
import json
import re
import time
import itertools
from time import strftime
from tokenize import Number
from xmlrpc.client import DateTime
import discord
import lavalink
from discord.ext import commands
from configparser import ConfigParser

config = ConfigParser()
config.read('setting.ini')
guild_ids = json.loads(config.get('discord', 'guild_ids'))
url_rx = re.compile(r'https?://(?:www\.)?.+')
bot_id = int(os.getenv('BOT_ID'))
NUMBER_EMOJI = ['0️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

class LavalinkVoiceClient(discord.VoiceClient):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel

        if hasattr(self.client, 'lavalink'):
            self.lavalink = self.client.lavalink
        else:
            self.client.lavalink = lavalink.Client(bot_id)
            self.client.lavalink.add_node(
                'localhost',
                '2333',
                'pw',
                'us',
                'default-node')
            self.lavalink = self.client.lavalink
    
    async def on_voice_server_update(self, data):
        await self.lavalink.voice_update_handler({
            't': 'VOICE_SERVER_UPDATE',
            'd': data
        })
    
    async def on_voice_state_update(self, data):
        await self.lavalink.voice_update_handler({
            't': 'VOICE_STATE_UPDATE',
            'd': data
        })
    
    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel)
    
    async def disconnect(self, *, force: bool = False) -> None:
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        if not force and not player.is_connected:
            return
        
        await self.channel.guild.change_voice_state(channel=None)

        player.channel_id = None
        self.cleanup()

class MusicPlayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []

        if not hasattr(bot, 'lavalink'):
            bot.lavalink = lavalink.Client(bot_id)
            bot.lavalink.add_node('localhost', '2333', 'pw', 'us', 'default-node')
        
        lavalink.add_event_hook(self.track_hook)
    
    def cog_unload(self):
        self.bot.lavalink._event_hooks.clear()
    
    async def cog_before_invoke(self, ctx):
        guild_check = ctx.guild is not None

        if guild_check:
            await self.ensure_voice(ctx)
        
        return guild_check
    
    async def cog_command_error(self, ctx, error: Exception):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.respond(error.original)
        else:
            await ctx.respond(f"⛔ 뭔가 문제가 발생했어요,,, {error} <@273229464186519552> 고쳐줘!!!!!!!")
    
    async def ensure_voice(self, ctx):
        player = self.bot.lavalink.player_manager.create(ctx.guild.id, endpoint=str(ctx.guild.region))
        should_connect = ctx.command.name in ('play', 'search', 'join')
        should_move = ctx.command.name in ('join')

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandInvokeError('⛔ 음성 채널에 먼저 들어와주세요')
        
        if not player.is_connected:
            if not should_connect:
                raise commands.CommandInvokeError('⛔ 음성 채널에 연결되지 않았어요')

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect or not permissions.speak:
                raise commands.CommandInvokeError('⛔ 봇을 사용할 권한이 부족해요')
            
            player.store('channel', ctx.channel.id)
            await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
        else:
            if should_move:
                if int(player.channel_id) == ctx.author.voice.channel.id:
                    raise commands.CommandInvokeError('⛔ 이미 같은 채널에 있어요!')
                else:
                    await ctx.voice_client.move_to(ctx.author.voice.channel)
            elif int(player.channel_id) != ctx.author.voice.channel.id:
                raise commands.CommandInvokeError('⛔ 같은 채널에 있어야해요')
        
    async def track_hook(self, event):
        if isinstance(event, lavalink.events.QueueEndEvent):
            guild_id = int(event.player.guild_id)
            guild = self.bot.get_guild(guild_id)
            await guild.voice_client.disconnect(force=True)
        elif isinstance(event, lavalink.events.TrackStartEvent):
            channel = event.player.fetch('channel')
            if channel:
                channel = self.bot.get_channel(channel)
                user = await self.bot.get_or_fetch_user(event.track.requester)
                if channel and user:
                    description = f"**[{event.track.title}]({event.track.uri})** - (*{time.strftime('%H:%M:%S', time.gmtime(event.track.duration / 1000))}*)"
                    embed = discord.Embed(title=f"재생중...", description=description, color=discord.Color.blurple())
                    embed.set_footer(text=user.name, icon_url=user.display_avatar.url)
                    embed.set_image(url=f"https://img.youtube.com/vi/{event.track.identifier}/0.jpg")
                    await channel.send(embed=embed)
            

    @commands.slash_command(guild_ids=guild_ids, description=f'안녕하세요!')
    async def hello(self, ctx):
        await ctx.respond(f"👋 안녕하세요 {ctx.author.mention}님!")

    @commands.slash_command(guild_ids=guild_ids, description=f'음악을 재생해요. 제목, URL 등, 모바일이라면 마지막에 스페이스바를 한번 눌러주세요!')
    async def play(self, ctx, *, query: str):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        query = query.strip('<>')

        if not url_rx.match(query):
            query = f'ytsearch:{query}'
                
        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.respond('⛔ 아무것도 찾지 못했어요')
        
        description = ''
        if results['loadType'] == 'PLAYLIST_LOADED':
            tracks = results['tracks']

            for track in tracks:
                player.add(requester=ctx.author.id, track=track)
            
            description = f'Playlist를 목록에 추가했어요! {results["playlistInfo"]["name"]} - {len(tracks)}곡'
        else:
            track = results['tracks'][0]
            description = f'`{track["info"]["title"]}`을 `{len(player.queue) + 1}` 순서로 추가했어요!'

            track = lavalink.models.AudioTrack(track, ctx.author.id, recommended=True)
            player.add(requester=ctx.author.id, track=track)
        
        await ctx.respond(f"🎵 {description}")

        if not player.is_playing:
            await player.play()
    
    @commands.slash_command(guild_ids=guild_ids, description=f'음악을 유투브에서 검색해요')
    async def search(self, ctx, *, query: str):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        query = query.strip('<>')

        if url_rx.match(query):
            return await self.play(ctx, query=query)
        
        query = f'ytsearch:{query}'

        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.respond('⛔ 아무것도 찾지 못했어요')
        
        if results['loadType'] == 'SEARCH_RESULT':
            tracks = results['tracks']

            description = ''
            for index, track in enumerate(itertools.islice(tracks, 5), start=1):
                description += f"{NUMBER_EMOJI[index]} `{time.strftime('%H:%M:%S', time.gmtime(track['info']['length'] / 1000))}` | **{track['info']['title']}**\n" 

            class NumberButton(discord.ui.View):
                def __init__(self):
                    super().__init__()
                    for index, emoji in enumerate(NUMBER_EMOJI[1:6]):
                        button = discord.ui.Button(emoji=emoji)
                        button.custom_id = str(index)
                        button.callback = self.callback
                        self.add_item(button)

                async def callback(self, interaction):
                    await interaction.message.delete()
                    await ctx.respond(f"🎵 `{tracks[int(interaction.custom_id)]['info']['title']}`을 `{len(player.queue) + 1}` 순서로 추가했어요!")
                    player.add(requester=ctx.author.id, track=tracks[int(interaction.custom_id)])
                    if not player.is_playing:
                        await player.play()

            return await ctx.respond(description, view=NumberButton(), delete_after=10)
    
    @commands.slash_command(guild_ids=guild_ids, description=f'현재 재생중인 음악을 스킵해요')
    async def skip(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.respond('⛔ 재생중인 노래가 없어요')
        
        await ctx.respond(f"🎵 **{player.current.title}**을 스킵할게요!")
        await player.skip()
    
    @commands.slash_command(guild_ids=guild_ids, description=f'재생 목록에 있는 음악을 제거해요 /remove 번호(/queue로 확인 가능)')
    async def remove(self, ctx, *, number: int):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        
        if number > len(player.queue):
            return await ctx.respond(f'⛔ `{number}`번 노래가 목록에 없어요!')
        
        await ctx.respond(f"🗑️ {player.queue[number - 1].title}을 목록에서 삭제했어요!")
        del player.queue[number - 1]

    @commands.slash_command(guild_ids=guild_ids, description=f'재생 목록에 있는 음악들을 모두 제거해요')
    async def clear(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        player.queue.clear()
        return await ctx.respond(f"🗑️ 음악 목록을 싹 비웠어요!")
    
    @commands.slash_command(guild_ids=guild_ids, description=f'재생 목록을 출력해요')
    async def queue(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player.queue:
            return await ctx.respond('⛔ 재생목록에 아무것도 없어요')
        description = ''
        for index, track in enumerate(player.queue, start=1):
            user = await self.bot.get_or_fetch_user(track.requester)
            description += f"**`{index}`. {track.title}**  - {user.name}\n"
        embed = discord.Embed(description=description, color=discord.Color.blurple())
        return await ctx.respond(embed=embed)

    @commands.slash_command(guild_ids=guild_ids, description=f'혜팡이를 원하는 음성 채널로 이동시켜요')
    async def join(self, ctx):
        await ctx.respond(f"↖️ `{ctx.author.voice.channel.name}`으로 채널을 이동했어요!")

    @commands.slash_command(guild_ids=guild_ids, description=f'혜팡이 나가!!!')
    async def leave(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.respond('연결 안됨')
        
        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.respond('⛔ 같은 채널에 있어야 해요')
        
        player.queue.clear()
        await player.stop()
        await ctx.voice_client.disconnect(force=True)
        await ctx.respond('👋 나갈게요!')

def setup(bot):
    bot.add_cog(MusicPlayer(bot))