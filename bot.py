from __future__ import annotations

import logging
import json
from typing import Any, TypeVar
from pathlib import Path
from typing import Literal, Optional

import asyncpg
import discord
from discord.ext import commands
from discord import app_commands

from source.enums import Rarity, Condition, SpecialRarity, Item
from source.utils import psql
from source.utils.embed import create_error_embed, create_warning_embed


OWNER_ID = 353774678826811403
Context = commands.Context["Fancards"]
ClientT = TypeVar('ClientT', bound='discord.Client')


class FancardsCommandTree(app_commands.CommandTree[ClientT]):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        bot: Fancards = interaction.client  # type: ignore
        psql_blacklist_table = await psql.Blacklist(bot.pool, interaction.user.id).get_table()

        with open("source/json/config.json", "r") as file:
            data: dict[str, Any] = json.load(file)

        if psql_blacklist_table is not None:
            command = interaction.command
            assert command

            if command.name == "support":
                return True

            embed = create_error_embed(interaction, f"I'm sorry but you are currently blacklisted.\n**Reason:** {psql_blacklist_table.reason}")
            embed.title = "You're Blacklisted!"
            await interaction.response.send_message(embed=embed)
            return False
        
        if data["maintenance_mode"]:
            embed = create_warning_embed(interaction, ":construction: Hi there lovely player! I apologize for the inconvenience but the bot is currently under maintenance. :construction:")
            embed.title = "Maintenance Notice!"
            await interaction.response.send_message(embed=embed)
            return False
        
        return True


class Fancards(commands.Bot):
    def __init__(self, config: dict[str, Any], cmd_prefix: str, dev_mode: bool) -> None:
        # bot variables
        self.uptime = discord.utils.utcnow()
        self.cmd_prefix = cmd_prefix

        # logging
        self.log = logging.getLogger("discord")
        self.log.setLevel(logging.INFO)

        self.config = config
        self.dev_mode = dev_mode

        super().__init__(
            command_prefix=cmd_prefix,
            owner_id=OWNER_ID,
            activity=discord.Activity(type=discord.ActivityType.playing, name="nightmare cards."),
            intents=discord.Intents.all(),
            allowed_mentions=discord.AllowedMentions.all(),
            help_command=None,
            tree_cls=FancardsCommandTree
        )
        self.add_command(sync)

    # built-in events and methods
    async def setup_hook(self) -> None:
        cogs = [p.stem for p in Path(".").glob("./source/cogs/*.py")]
        for cog in cogs:
            await self.load_extension(f"source.cogs.{cog}")
            self.log.info(f"Extension '{cog}' has been loaded.")

        await self.load_extension("jishaku")
        await self.create_pool()

    async def on_connect(self) -> None:
        self.log.info(f"Connected to Client (version: {discord.__version__}).")

    async def on_ready(self) -> None:
        assert self.user
        self.log.info(f"Bot has connected (Guilds: {len(self.guilds)}) (Bot Username: {self.user}) (Bot ID: {self.user.id}).")
        runtime = discord.utils.utcnow() - self.uptime
        self.log.info(f"connected after {runtime.total_seconds():.2f} seconds.")

    async def on_disconnect(self) -> None:
        self.log.critical("Bot has disconnected!")

    async def on_guild_leave(self, guild: discord.Guild) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute("DELETE FROM config WHERE guild_id = $1;", guild.id)

    async def init_connection(self, connection: asyncpg.Connection[asyncpg.Record]):
        with open("schema.sql", "r") as file:
            query = file.read()

        await connection.execute(query)
        await connection.set_type_codec(
            "card_rarity",
            encoder=lambda r: r.value,
            decoder=Rarity
        )
        await connection.set_type_codec(
            "card_condition",
            encoder=lambda c: c.value,
            decoder=Condition
        )
        await connection.set_type_codec(
            "card_special_rarity",
            encoder=lambda sr: sr.value,
            decoder=SpecialRarity
        )
        await connection.set_type_codec(
            "item",
            encoder=lambda i: i.value,
            decoder=Item
        )

    async def create_pool(self):
        if self.dev_mode:
            pool = await asyncpg.create_pool(
                host="localhost",
                port=5432,
                user="postgres",
                password=self.config["pg_password"],
                database="ditto",
                init=self.init_connection
            )
        else:
            pool = await asyncpg.create_pool(
                dsn=self.config["pg"],
                init=self.init_connection
            )

        assert pool
        self.pool = pool
        del self.dev_mode
        del self.config
        

# ungrouped commands
@commands.is_owner()
@commands.command()
async def sync(ctx: Context, option: Optional[Literal["~", "*", "^"]] = None) -> None:
    """Syncs all app commands to the server"""

    assert ctx.guild

    if option == "~":
        synced = await ctx.bot.tree.sync(guild=ctx.guild)  # sync to guild

    elif option == "*":
        ctx.bot.tree.copy_global_to(guild=ctx.guild)  # copy from global commands and sync to guild
        synced = await ctx.bot.tree.sync(guild=ctx.guild)

    elif option == "^":
        ctx.bot.tree.clear_commands(guild=ctx.guild)  # clear tree then sync
        await ctx.bot.tree.sync(guild=ctx.guild)
        synced = []

    else:
        synced = await ctx.bot.tree.sync()  # sync globally

    await ctx.send(f"Synced {len(synced)} commands {'globally' if option is None else 'to the current guild'}.")
