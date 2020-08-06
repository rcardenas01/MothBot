import asyncio

import discord
from discord.ext import commands
import random

import math

import Music


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)

        if not state or not state.exists:
            state = Music.VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('An error occurred: {}'.format(str(error)))

    @commands.command(name="join", invoke_without_subcommand=True)
    async def _join(self, ctx: commands.Context):
        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_client.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()
        await ctx.send("Connected to voice channel.")

    @commands.command(name='summon')
    # @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        if not channel and not ctx.author.voice:
            raise Music.VoiceError('You are neither connected to a voice channel nor specified a channel to join.')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    # @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        if not ctx.voice_state.voice:
            return await ctx.send('Not connected to any voice channel.')

        await ctx.send("Left the voice channel.")
        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    async def _volume(self, ctx: commands.Context, *, volume: int):

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        if 0 > volume > 100:
            return await ctx.send('Volume must be between 0 and 100')

        ctx.voice_state.current.source.volume = volume / 100
        await ctx.send('Volume of the player set to {}%'.format(volume))

    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        await ctx.send(embed=ctx.voice_state.current.create_embed())

    @commands.command(name='pause')
    # @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context):
        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_playing():
            ctx.voice_state.voice.pause()
            await ctx.send("Music paused.")

    @commands.command(name='resume')
    # @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context):
        if ctx.voice_state.is_playing and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.send("Music resumed.")

    @commands.command(name='stop')
    # @commands.has_permissions(manage_guild=True)
    async def _stop(self, ctx: commands.Context):
        ctx.voice_state.songs.clear()

        if ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()

            await ctx.voice_state.player_message.delete()
            ctx.voice_state.player_message = None

            await ctx.send("Music stopped.")

    @commands.command(name='skip')
    async def _skip(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send('Not playing any music right now...')

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.send("Song skipped.")
            ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.send("Song skipped.")
                ctx.voice_state.skip()
            else:
                await ctx.send('Skip vote added, currently at **{}/3**'.format(total_votes))

        else:
            await ctx.send('You have already voted to skip this song.')

    @commands.command(name='queue')
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(i + 1, song)

        embed = (discord.Embed(description='**{} tracks:**\n\n{}'.format(len(ctx.voice_state.songs), queue))
                 .set_footer(text='Viewing page {}/{}'.format(page, pages)))
        await ctx.send(embed=embed)

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffles the queue."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.shuffle()
        await ctx.send("Shuffled the queue.")

    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):
        """Removes a song from the queue at a given index."""

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.remove(index - 1)
        await ctx.send("Song removed.")

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        if ctx.voice_state.loop:
            await ctx.send("Current song will **now** be looped.")
        else:
            await ctx.send("Current song will **not** be looped.")

    @commands.command(name='play', aliases=['p'])
    async def _play(self, ctx: commands.Context, *, search: str):
        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        async with ctx.typing():
            try:
                source = await Music.YTDLSource.create_source(ctx, search, loop=self.bot.loop)
            except Music.YTDLError as e:
                await ctx.send('An error occurred while processing this request: {}'.format(str(e)))
            else:
                song = Music.Song(source)

                await ctx.voice_state.songs.put(song)
                await ctx.send('Enqueued {}'.format(str(source)))

    @_join.before_invoke
    @_play.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('You are not connected to any voice channel.')

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError('Bot is already in a voice channel.')

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user):
        if user == bot.user:
            return

        msg = reaction.message
        ctx = await self.bot.get_context(msg)
        ctx.voice_state = self.get_voice_state(ctx)

        ctx.message.author = user

        if msg.id == ctx.voice_state.player_message.id:
            if reaction.emoji == '\U000023EF':  # Play/Pause
                await ctx.invoke(self._pause)
            elif reaction.emoji == '\U000023F9':  # Stop
                await ctx.invoke(self._stop)
            elif reaction.emoji == '\U000023ED':  # Next
                await ctx.invoke(self._skip)
            elif reaction.emoji == '\U0001F500':  # Shuffle
                await ctx.invoke(self._shuffle)
            elif reaction.emoji == '\U0001F502':  # Repeat Single
                await ctx.invoke(self._loop)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.reaction, user):
        if user == bot.user:
            return

        msg = reaction.message
        ctx = await self.bot.get_context(msg)
        ctx.voice_state = self.get_voice_state(ctx)

        ctx.message.author = user

        if msg.id == ctx.voice_state.player_message.id:
            if reaction.emoji == '\U000023EF':  # Play/Pause
                await ctx.invoke(self._resume)
            elif reaction.emoji == '\U0001F502':  # Repeat Single
                await ctx.invoke(self._loop)


token = "NzA1Nzk0OTI3Nzk1MTA5ODg4.XsRsWQ.uwCzo_r6LMm1kQ6gX2YSfZUlRVs"
prefix = "m!"
bot = commands.Bot(command_prefix=commands.when_mentioned_or(prefix))

bot.add_cog(MusicCog(bot))


@bot.event
async def on_ready():
    print("Logged in as")
    print(bot.user.name)
    print(bot.user.id)
    print("------")
    activity = discord.Activity(name='the light', type=discord.ActivityType.watching)
    await bot.change_presence(activity=activity)


@bot.command()
async def roll(ctx, *,  dice: str):
    try:
        sum_rolls = 0
        adder = 0
        rollers = ""
        roll_nums = []

        if "+" in dice:
            rollers, adder = dice.replace(" ", "").split("+")

            adder = int(adder)
        else:
            rollers = dice.replace(" ", "")

        if rollers.find("d") == 0:
            rollers = "1" + rollers

        rolls, limit = map(int, rollers.split("d"))

    except Exception:
        await ctx.send('Format must be in NdN or NdN + c')
        return

    for r in range(rolls):
        num = random.randint(1, limit)
        sum_rolls += num
        roll_nums.append(str(num))

    await ctx.send("```" + dice.replace(" ", "")
                   + " is " + " + ".join(roll_nums) + " + " + str(adder) + " = " + str(sum_rolls) + "\n```")


@bot.command()
async def bitch(ctx):
    await ctx.send(ctx.message.author.mention + " bitch")


@bot.command()
async def hello(ctx):
    await ctx.send(ctx.message.author.mention + " hello")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.author.name == "BerzerkerBear":
        emoji = discord.utils.get(message.guild.emojis, name='Aian')
        if emoji:
            await message.add_reaction(emoji)

    if "moth" in message.content.lower() and prefix not in message.content:
        await message.channel.send("praise be")

    await bot.process_commands(message)


bot.run(token)
