import asyncio

import discord
from discord.ext import commands, tasks
import random

import math
import os
import json

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

        if ctx.voice_state.player_message and msg.id == ctx.voice_state.player_message.id:
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

        # await reaction.message.add_reaction(reaction.emoji)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.reaction, user):
        if user == bot.user:
            return

        msg = reaction.message
        ctx = await self.bot.get_context(msg)
        ctx.voice_state = self.get_voice_state(ctx)

        ctx.message.author = user

        if ctx.voice_state.player_message and msg.id == ctx.voice_state.player_message.id:
            if reaction.emoji == '\U000023EF':  # Play/Pause
                await ctx.invoke(self._resume)
            elif reaction.emoji == '\U0001F502':  # Repeat Single
                await ctx.invoke(self._loop)


# def is_owner():
#     def predicate(ctx):
#         return ctx.author.id == 238801458030575627 or ctx.author.id == 787208554431119360
#     return commands.check(predicate)


class ChatCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.current = None
        self.reacts = {}
        self.void = {}

    @commands.command()
    @commands.is_owner()
    @commands.dm_only()
    async def set(self, ctx: commands.Context, id_send: int):
        self.current = await self.bot.fetch_channel(id_send)
        if self.current is None:
            self.current = await self.bot.fetch_user(id_send)
            if self.current is None:
                await ctx.send("That is not a valid destination.")
            else:
                await ctx.send("Destination to " + self.current.name + ".")
        else:
            await ctx.send("Destination to " + self.current.name + " in " + self.current.guild.name + ".")

    @commands.command(aliases=['send'])
    @commands.is_owner()
    @commands.dm_only()
    async def say(self, ctx: commands.Context, *, message: str):
        if self.current is not None:
            await self.current.send(message)
            await ctx.send("Message sent.")
        else:
            await ctx.send("Destination has not been set!")

    @commands.command()
    @commands.is_owner()
    @commands.dm_only()
    async def refresh(self, ctx: commands.Context):
        os.environ["loop"] = "loop"
        await ctx.send("Refreshing code...")
        await self.bot.logout()

    @commands.command()
    @commands.is_owner()
    @commands.dm_only()
    async def shutdown(self, ctx: commands.Context):
        os.environ["loop"] = "stop"
        await ctx.send("Shutting down...")
        await self.bot.logout()

    @commands.group()
    async def react(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send('Invalid subcommand for react')

    @react.command()
    async def add(self, ctx: commands.Context, emoji: str):
        guild_id = str(ctx.guild.id)
        member_id = str(ctx.author.id)
        if guild_id in self.reacts:
            if member_id not in self.reacts[guild_id]:
                self.reacts[guild_id][member_id] = {}
        else:
            self.reacts[guild_id] = {}
            self.reacts[guild_id][member_id] = {}

        self.reacts[guild_id][member_id]['emoji'] = emoji

        with open('reacts.json', 'w') as file:
            json.dump(self.reacts, file)

        await ctx.send("Set to react to " + ctx.author.mention + " with " + str(emoji))

    @react.command()
    async def remove(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        member_id = str(ctx.author.id)
        if guild_id in self.reacts:
            if member_id in self.reacts[guild_id]:
                del self.reacts[guild_id][member_id]

        with open('reacts.json', 'w') as file:
            json.dump(self.reacts, file)

        await ctx.send("Will no longer react to " + ctx.author.mention)

    @commands.group()
    async def void(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Invalid subcommand for void")

    # @void.command()
    # async def set(self, ctx: commands.Context, channel_id: discord.TextChannel):
    #     guild_id = str(ctx.guild.id)
    #     self.void[guild_id] = str(channel_id.id)
    #
    #     with open('void.json', 'w') as file:
    #         json.dump(self.void, file)
    #
    #     await ctx.send("Installed a bottomless void in " + channel_id.name)

    @void.command()
    async def remove(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        del self.void[guild_id]

        with open('void.json', 'w') as file:
            json.dump(self.void, file)

        await ctx.send("The void collapsed.")

    @tasks.loop(minutes=5)
    async def void_swallow(self):
        for channel_id in self.void.values():
            id_ = int(channel_id)
            void = self.bot.get_channel(id_)

    @commands.command()
    async def roll(self, ctx: commands.Context, *, dice: str):
        try:
            sum_rolls = 0
            adder = 0
            rollers = ""
            roll_nums = []

            if dice.find("d") == 0:
                dice = "1" + dice

            if "+" in dice:
                rollers, adder = dice.replace(" ", "").split("+")

                adder = int(adder)
                sum_rolls += adder
            else:
                rollers = dice.replace(" ", "")

            rolls, limit = map(int, rollers.split("d"))

        except Exception:
            await ctx.send('Format must be in (N)dN or (N)dN + c!')
            return

        for r in range(rolls):
            num = random.randint(1, limit)
            sum_rolls += num
            roll_nums.append(str(num))

        if adder == 0:
            if rolls == 1:
                await ctx.send("Roll `" + dice.replace(" ", "") + "`: " + str(sum_rolls))
            else:
                await ctx.send("Roll `" + dice.replace(" ", "")
                               + "`: " + str(sum_rolls) + " (`" + " + ".join(roll_nums) + "`)")
        else:
            await ctx.send("Roll `" + dice.replace(" ", "")
                           + "`: " + str(sum_rolls) + " (`" + " + ".join(roll_nums) + " + " + str(adder) + "`)")

    @commands.command()
    async def bitch(self, ctx: commands.Context):
        do_copypasta = random.random()
        if do_copypasta <= 0.1:
            async with ctx.channel.typing():
                await asyncio.sleep(2)
                await ctx.send("What the fuck did you just fucking say about me, you little bitch? I'll have you know "
                               + "I graduated top of my class in the Navy Seals, and I've been involved in numerous "
                               + "secret raids on  Al-Quaeda, and I have over 300 confirmed kills. I am trained in "
                               + "gorilla warfare and I'm the top sniper in the entire US armed forces. You are nothing"
                               + " to me but just another target. I will wipe you the fuck out with precision the likes"
                               + " of which has never been seen before on this Earth, mark my fucking words. You think "
                               + "you can get away with saying that shit to me over the Internet? Think again, fucker. "
                               + "As we speak I am contacting my secret network of spies across the USA and your IP is "
                               + "being traced right now so you better prepare for the storm, maggot. The storm that "
                               + "wipes out the pathetic little thing you call your life. You're fucking dead, kid. I "
                               + "can be anywhere, anytime, and I can kill you in over seven hundred ways, and that's "
                               + "just with my bare hands. Not only am I extensively trained in unarmed combat, but I "
                               + "have access to the entire arsenal of the United States Marine Corps and I will use it"
                               + " to its full extent to wipe your miserable ass off the face of the continent, you "
                               + "little shit. If only you could have known what unholy retribution your little "
                               + "\"clever\" comment was about to bring down upon you, maybe you would have held your "
                               + "fucking tongue. But you couldn't, you didn't, and now you're paying the price, you "
                               + "goddamn idiot. I will shit fury all over you and you will drown in it. "
                               + "You're fucking dead, kiddo.")
        else:
            await ctx.send(ctx.message.author.mention + " bitch")

    @commands.command()
    async def hello(self, ctx: commands.Context):
        await ctx.send(ctx.message.author.mention + " hello")

    @commands.Cog.listener()
    async def on_ready(self):
        with open('reacts.json', 'r') as in_file:
            self.reacts = json.load(in_file)

        with open('void.json', 'r') as void_in:
            self.void = json.load(void_in)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        is_bot_admin = message.author.id == self.bot.owner_id

        if isinstance(message.channel, discord.DMChannel) and not is_bot_admin:
            owner = self.bot.get_user(self.bot.owner_id)
            await owner.send("Message from " + message.author.name + ": " + message.content)

        if "good bot" in message.content.lower():
            await message.channel.send("thenk \U0001F642")  # Smiling face

        if ":thonk:" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(621072530253414432))

        if ":megathonk:" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(739226375239630918))

        if ":gaythonk:" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(750168162171093103))

        if ":doublethonk:" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(764553793039499286))

        if ":codethonk:" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(786700064051298364))

        if ":eggthonk:" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(786774524653862962))

        if "mood" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(783010747491942431))

        if "darryl" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(620036969933701120))

        if "bruh" in message.content.lower() or ":high:" in message.content.lower():
            await message.add_reaction(self.bot.get_emoji(786149121123680266))

        if isinstance(message.channel, discord.TextChannel):
            guild_id = str(message.guild.id)
            member_id = str(message.author.id)
            if guild_id in self.reacts:
                if member_id in self.reacts[guild_id]:
                    await message.add_reaction(self.reacts[guild_id][member_id]['emoji'])

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user):
        if user == bot.user:
            return

        if reaction.emoji == '\U00002755' or reaction.emoji == '\U00002757':
            await reaction.message.add_reaction('🇼')
            await reaction.message.add_reaction('🇭')
            await reaction.message.add_reaction('🇦')
            await reaction.message.add_reaction('🇹')


# Token for Boomer258
with open("token.txt") as f:
    token = f.read()
prefix = "m!"
bot = commands.Bot(command_prefix=commands.when_mentioned_or(prefix))

bot.add_cog(MusicCog(bot))
bot.add_cog(ChatCog(bot))


@bot.event
async def on_ready():
    print("Logged in as")
    print(bot.user.name)
    print(bot.user.id)
    print("------")
    activity = discord.Activity(name='the light', type=discord.ActivityType.watching)
    await bot.change_presence(activity=activity)


@bot.event
async def on_command_error(ctx: commands.context, error: commands.CommandError):
    if isinstance(error, commands.PrivateMessageOnly):
        user = bot.get_user(787208554431119360)
        await user.send("Someone tried to get me to say something not in a DM.")

    if isinstance(error, commands.NotOwner):
        user = bot.get_user(787208554431119360)
        await user.send("Someone tried to get me to say something that wasn't the owner.")


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    if (("moth" in message.content.lower()) and ("mother" not in message.content.lower())
            and "mothbot" not in message.content.lower())\
            or (hasattr(message.author, "nick")
                and "moth" in message.author.nick.lower() and "mother" not in message.author.nick.lower()):
        await message.channel.send("praise be")

    if "mothbot" in message.content.lower():
        await message.channel.send("praise me")

    if "praise be" in message.content.lower():
        await message.channel.send("praise be")

    await bot.process_commands(message)

bot.run(token)
