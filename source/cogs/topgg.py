from __future__ import annotations

import json
import datetime
from typing import TYPE_CHECKING

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

from source.enums import Fanmoji, PatreonRole, Currency
from source.utils import psql, FANCARDS_GUILD_ID, PATREON_PAGE_URL, has_minimum_patreon_role
from source.utils.embed import create_info_embed
from source.utils.view import Promotion

if TYPE_CHECKING:
    from bot import Fancards

VOTES_CHANNEL_ID = 1076822826318823444

TOPGG_VOTE_URL = "https://top.gg/bot/1064145673513087018/vote"
TOPGG_BASE_API_URL = "https://top.gg/api"
BOTS_URL_WITH_BOT_ID = f"{TOPGG_BASE_API_URL}/bots/1064145673513087018"


def _get_authorization() -> str:
    with open("source/json/config.json", "r") as f:
        config = json.load(f)

    return config["topgg_api_bot_token"]


async def user_voted_check(user_id: int) -> bool:
    """Check if the user has already voted for the bot."""

    headers = {"Authorization": _get_authorization()}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{BOTS_URL_WITH_BOT_ID}/check?userId={user_id}") as response:
            result_json = await response.json()
            voted: int = result_json["voted"]

    return bool(voted)


def _double_vote_rewards(guild: discord.Guild, member_id: int, reward_amount: int) -> int:
    """Doubles the ``reward_amount`` if the member has a specific Patreon role."""
    member = discord.utils.get(guild.members, id=member_id)

    if member is not None:
        if has_minimum_patreon_role(member, PatreonRole.uncommon):
            reward_amount *= 2

    return reward_amount


def _calculate_total_vote_rewards(guild: discord.Guild, member_id: int, vote_streak: int) -> int:
    reward_amount = 1
    if discord.utils.utcnow().weekday() in [5, 6]:
        reward_amount = 2

    if vote_streak >= 50:
        reward_amount += 2

    elif vote_streak >= 10:
        reward_amount += 1

    reward_amount = _double_vote_rewards(guild, member_id, reward_amount)

    return reward_amount


async def _handle_votes(bot: Fancards, message: discord.Message) -> None:
    vote_data = VoteData(message.embeds[0])

    psql_user = psql.User(bot.pool, vote_data.user_id)
    psql_vote_table = await psql_user.vote.get_table()

    if psql_vote_table is None:
        return None

    now = discord.utils.utcnow()
    voted_at = psql_vote_table.voted_at
    vote_streak = psql_vote_table.vote_streak

    current_streak = vote_streak + 1

    if voted_at is not None:
        revote_at: datetime.datetime = voted_at + datetime.timedelta(hours=12)
        if (now < revote_at):
            return None
        
        if (now - voted_at).days > 1:
            current_streak = 1
    
    guild = bot.get_guild(FANCARDS_GUILD_ID)
    assert guild
    reward_amount = _calculate_total_vote_rewards(guild, vote_data.user_id, current_streak)

    await psql_user.set_voucher(reward_amount)
    await psql_user.vote.set_vote_streak(current_streak)
    await psql_user.vote.set_voted_at(now)


class VoteData:
    def __init__(self, embed: discord.Embed) -> None:
        self.fields = embed.fields

    @property
    def user_id(self) -> int:
        field = discord.utils.get(self.fields, name="user ID")

        if field is None:
            raise AttributeError("Couldn't get vote data from embed.")

        assert field.value
        return int(field.value)


class TopGG(commands.Cog):
    def __init__(self, bot: Fancards) -> None:
        self.bot = bot
        self.log = bot.log

    @commands.Cog.listener("on_message")
    async def on_vote(self, message: discord.Message) -> None:
        assert self.bot.user
        if message.author.id == self.bot.user.id:
            return None
        
        if message.channel.id == VOTES_CHANNEL_ID:
            await _handle_votes(self.bot, message)

    @app_commands.command(name="vote", description="Vote for Fancards and get rewards, you can vote again every 12 hours")
    async def vote_command(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        psql_vote_table = await psql_user.vote.get_table()

        if psql_vote_table is not None:
            vote_streak = psql_vote_table.vote_streak
        else:
            vote_streak = 0

        voted = await user_voted_check(interaction.user.id)
        is_weekend = discord.utils.utcnow().weekday() in [5, 6]

        if voted:
            assert psql_vote_table
            voted_at = psql_vote_table.voted_at
            assert voted_at
            can_vote_again = discord.utils.format_dt(voted_at + datetime.timedelta(hours=12), style="R")
            can_vote_text = f"{Fanmoji.cross_pixel_icon}  **Vote Unavailable!**\nYou have already voted on [top.gg!]({TOPGG_VOTE_URL})\nYou can vote again: {can_vote_again}"
        else:
            can_vote_text = f"{Fanmoji.check_pixel_icon}  **Vote Available!**\n[Click here to vote on top.gg!]({TOPGG_VOTE_URL})"

        guild = self.bot.get_guild(FANCARDS_GUILD_ID)
        assert guild
        reward_amount = _calculate_total_vote_rewards(guild, interaction.user.id, vote_streak)

        vote_streak_10 = Fanmoji.check_pixel_icon if vote_streak >= 10 else Fanmoji.cross_pixel_icon
        vote_streak_50 = Fanmoji.check_pixel_icon if vote_streak >= 50 else Fanmoji.cross_pixel_icon

        description = f"Vote for Fancards every 12 hours to receive rewards!\nYou gain an extra {Currency.voucher.display()} on weekends (Saturday and Sunday)!"
        vote_streak_bonus_text = f"{Fanmoji.level_up} **Voting Streak Bonuses:**\n{vote_streak_10} **10+ Vote Streak:** You gain {Fanmoji.voucher} 1 more per vote.\n{vote_streak_50} **50+ Vote Streak:** You gain {Fanmoji.voucher} 2 more per vote.\n\n**Current Voting Streak:** `x{vote_streak}`\nYou will receive {Fanmoji.voucher} {reward_amount} if you vote now!"

        assert isinstance(interaction.user, discord.Member)

        embed = create_info_embed(
            interaction,
            f"{description}\n\n{can_vote_text}\n\n{vote_streak_bonus_text}\n\n{Fanmoji.patreon_badge} [Support us on Patreon]({PATREON_PAGE_URL}) to double your vote rewards and gain more benefits!"
        )
        embed.title = "Vote for Fancards to get Rewards!"
        
        if is_weekend:
            embed.set_footer(text=f"Weekend Bonus: +1 Voucher!", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed, view=Promotion())
        

async def setup(bot: Fancards):
    await bot.add_cog(TopGG(bot))
