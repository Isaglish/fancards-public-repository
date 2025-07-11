from __future__ import annotations

import random
import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from PIL import Image

from source.enums import Fanmoji, Condition, Item, Currency, Rarity, Character
from source.entity import CraftableCharacterEntity
from source.cogs.card import CardFactory, CardImage
from source.utils import psql, DISCORD_SERVER_URL, is_patreon
from source.utils.time import seconds_to_human
from source.utils.view import Confirm, EmbedPaginator, Promotion
from source.utils.embed import create_info_embed, create_error_embed, create_success_embed, get_card_property_text
from source.utils.action_logger import ActionLogger
from source.utils.autocomplete import rarity_autocomplete

if TYPE_CHECKING:
    from bot import Fancards


async def _card_downgrade(interaction: discord.Interaction, user: discord.Member | discord.User, card: CardImage):
    bot: Fancards = interaction.client  # type: ignore
    psql_user = psql.User(bot.pool, user.id)
    
    if card.has_sleeve:
        await psql_user.cards.invert_has_sleeve(card.card_id)

        embed = create_error_embed(interaction, f"The card you received **`{card.card_id}`** was protected by its {Item.card_sleeve.display()} from downgrading and was destroyed.")
        embed.set_author(name=user, icon_url = user.display_avatar.url)
        await interaction.followup.send(content=f"{user.mention}, card sleeve destroyed whilst trading!", embed=embed)
        return None
    
    new_condition = CardFactory.downgrade(card.condition)
    await psql_user.cards.change_card_condition(card.card_id, new_condition)
    display_card = CardFactory.display_card_side_by_side_condition(card, card.condition, new_condition)

    buffer = BytesIO()
    display_card.save(buffer, format="PNG")
    buffer.seek(0)
    
    embed = create_error_embed(interaction, f"The card you received **`{card.card_id}`** has its condition downgraded.\n`{card.condition.title()} {card.condition.to_unicode()}` -> `{new_condition.title()} {new_condition.to_unicode()}`")
    file = discord.File(buffer, filename="card_downgrade.png")
    embed.set_image(url="attachment://card_downgrade.png")
    await interaction.followup.send(content=f"{user.mention}, card condition downgraded whilst trading!", embed=embed, file=file)


def _streak_to_str(current_streak: int, reward_map: dict[int, tuple[int, Currency | Item]]) -> str:
    items: list[str] = []
    for day, (reward_amount, reward_type) in reward_map.items():
        emoji = Fanmoji.check_pixel_icon if current_streak > day else Fanmoji.cross_pixel_icon

        reward_text = f"Day {day+1} • {reward_type.to_emoji()} {reward_amount:,}"
        if isinstance(reward_type, Item):
            reward_text = f"Day {day+1} • {reward_type.display()} `x{reward_amount:,}`"

        items.append(f"{emoji}  {reward_text}")

    return "\n".join(items)


class Uncategorized(commands.Cog):
    def __init__(self, bot: Fancards):
        self.bot = bot
        self.log = bot.log

    async def cog_load(self) -> None:
        self.daily_reward_resetter.start()

    async def cog_unload(self) -> None:
        self.daily_reward_resetter.cancel()

    @app_commands.command(name="trade-card", description="Trade one of your cards for another user's cards")
    @app_commands.rename(your_card="your-card", their_card="their-card")
    @app_commands.describe(
        user="The user you want to trade with",
        your_card="The code of your card",
        their_card="The code of the specified user's card"
    )
    async def trade_card(self, interaction: discord.Interaction, user: discord.Member, your_card: str, their_card: str):
        await interaction.response.defer(thinking=True)

        if user == interaction.user:
            embed = create_error_embed(interaction, "You cannot trade with yourself.")
            await interaction.followup.send(embed=embed)
            return None
        
        psql_user = psql.User(self.bot.pool, interaction.user.id)
        psql_user_table = await psql_user.get_table()

        their_psql_user = psql.User(self.bot.pool, user.id)
        their_psql_user_table = await their_psql_user.get_table()

        if psql_user_table is None:
            embed = create_error_embed(interaction, "You are currently not registered.")
            await interaction.followup.send(embed=embed)
            return None
        
        if their_psql_user_table is None:
            embed = create_error_embed(interaction, "This user is currently not registered.")
            await interaction.followup.send(embed=embed)
            return None
        
        psql_levels_table = await psql_user.levels.get_table()
        assert psql_levels_table

        required_level = 5
        if psql_levels_table.current_level < required_level:
            embed = create_error_embed(interaction, f"You must be at least **level {required_level}** in-order to trade with other users.")
            embed.set_footer(text="This is to make using alt-accounts more difficult.")
            await interaction.followup.send(embed=embed)
            return None
        
        their_psql_levels_table = await psql_user.levels.get_table()
        assert their_psql_levels_table

        if their_psql_levels_table.current_level < required_level:
            embed = create_error_embed(interaction, f"This user must be at least **level {required_level}** in-order to trade with you.")
            embed.set_footer(text="This is to make using alt-accounts more difficult.")
            await interaction.followup.send(embed=embed)
            return None

        first_trader_card = await psql_user.cards.get_card(your_card)
        second_trader_card = await their_psql_user.cards.get_card(their_card)

        if first_trader_card is None:
            embed = create_error_embed(interaction, f"I couldn't find any card with the ID `{your_card}`.")
            await interaction.followup.send(embed=embed)
            return None

        if first_trader_card.owner_id != psql_user_table.id:
            embed = create_error_embed(interaction, "You can only trade cards you own.")
            await interaction.followup.send(embed=embed)
            return None

        if second_trader_card is None:
            embed = create_error_embed(interaction, f"I couldn't find any card with the ID `{their_card}`.")
            await interaction.followup.send(embed=embed)
            return None

        if second_trader_card.owner_id != their_psql_user_table.id:
            embed = create_error_embed(interaction, "This user doesn't own this card.")
            await interaction.followup.send(embed=embed)
            return None

        first_trader_card = CardImage(
            image=Image.open(f"source/assets/cards/{first_trader_card.rarity}.png"),
            rarity=first_trader_card.rarity,
            condition=first_trader_card.condition,
            special_rarity=first_trader_card.special_rarity,
            character_name=first_trader_card.character_name,
            card_id=first_trader_card.card_id,
            has_sleeve=first_trader_card.has_sleeve
        )

        second_trader_card = CardImage(
            image=Image.open(f"source/assets/cards/{second_trader_card.rarity}.png"),
            rarity=second_trader_card.rarity,
            condition=second_trader_card.condition,
            special_rarity=second_trader_card.special_rarity,
            character_name=second_trader_card.character_name,
            card_id=second_trader_card.card_id,
            has_sleeve=second_trader_card.has_sleeve
        )

        trader_card_property_text = get_card_property_text(first_trader_card.card_id, first_trader_card.rarity, first_trader_card.condition, first_trader_card.special_rarity, first_trader_card.character_name, first_trader_card.has_sleeve)
        second_trader_card_property_text = get_card_property_text(second_trader_card.card_id, second_trader_card.rarity, second_trader_card.condition, second_trader_card.special_rarity, second_trader_card.character_name, second_trader_card.has_sleeve)
        embed = create_info_embed(interaction, "")
        embed.set_footer(text="Note: cards have a 50% chance of having their condition downgraded after trading.")
        embed.title = "Trade Offer"
        embed.add_field(name=interaction.user, value=trader_card_property_text, inline=False)
        embed.add_field(name=user, value=second_trader_card_property_text, inline=False)

        view = Confirm(user, timeout=30)
        message = await interaction.followup.send(
            f"{user.mention} You received a trading offer from {interaction.user.mention}.",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.all(),
            wait=True
        )

        await view.wait()
        if view.value is None:
            embed = create_error_embed(interaction, "This trade offer has expired.")
            embed.title = "Trade Offer Expired."
            embed.add_field(name=interaction.user, value=trader_card_property_text)
            embed.add_field(name=user, value=second_trader_card_property_text)
            await message.edit(content="", embed=embed, view=None)
            return None

        elif view.value:
            trader_card_check = await psql_user.cards.get_card(your_card)
            second_trader_card_check = await their_psql_user.cards.get_card(their_card)

            if trader_card_check is None or second_trader_card_check is None:
                embed = create_error_embed(interaction, "One of the cards being traded no longer exists.")
                await message.edit(
                    content=f"{interaction.user.mention} {user.mention} trading failed!",
                    embed=embed,
                    view=None
                )
                return None

            if trader_card_check.owner_id != psql_user_table.id:
                embed = create_error_embed(interaction, "You can only trade cards you own.")
                await message.edit(embed=embed, view=None)
                return None

            if second_trader_card_check.owner_id != their_psql_user_table.id:
                embed = create_error_embed(interaction, "This user doesn't own this card.")
                await message.edit(embed=embed, view=None)
                return None

            trader_card_downgrade = random.random() <= 0.5
            second_trader_card_downgrade = random.random() <= 0.5
            if trader_card_downgrade and first_trader_card.condition is not Condition.damaged:
                await _card_downgrade(interaction, user, first_trader_card)

            if second_trader_card_downgrade and second_trader_card.condition is not Condition.damaged:
                await _card_downgrade(interaction, interaction.user, second_trader_card)

            # swap the owner of the trader's card to the user's card
            await psql_user.cards.change_card_owner(first_trader_card.card_id, their_psql_user_table.id)
            # swap the owner of the user's card to the trader's card
            await their_psql_user.cards.change_card_owner(second_trader_card.card_id, psql_user_table.id)

            embed = create_success_embed(interaction, "")
            embed.add_field(name=interaction.user, value=trader_card_property_text, inline=False)
            embed.add_field(name=user, value=second_trader_card_property_text, inline=False)
            embed.title = "Trade Offer Accepted!"
            await message.delete()
            await interaction.followup.send(
                content=f"{interaction.user.mention} {user.mention} the trade was a success!",
                embed=embed
            )
            await ActionLogger.card_trade(interaction, user, first_trader_card.card_id, second_trader_card.card_id)

        else:
            embed = create_error_embed(interaction, f"{interaction.user.mention}, Trade offer was declined by {user.mention}")
            embed.title = "Trade Offer Declined!"
            await message.edit(content="", embed=embed, view=None)
            return None

    @app_commands.command(name="support", description="Get an invitation to Fancards' support server")
    async def support(self, interaction: discord.Interaction):
        await interaction.response.send_message(DISCORD_SERVER_URL, view=Promotion())

    @app_commands.command(name="help", description="Provides you with a list of available commands")
    async def help_command(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        embeds: list[discord.Embed] = []
        end = 10
        tree_commands = [command for command in self.bot.tree.walk_commands() if not isinstance(command, app_commands.Group)]
        for start in range(0, len(tree_commands), 10):
            current_command = tree_commands[start:end]
            end += 10

            command_names: list[str] = []
            for command in current_command:
                if command.root_parent:
                    continue

                parameters = command.parameters if not isinstance(command, app_commands.Group) else None
                
                parameter_names: list[str] = []
                if parameters is not None:
                    for parameter in parameters:
                        parameter_names.append(f"({parameter.display_name})" if parameter.required else f"[{parameter.display_name}]")

                joined_parameter_names = ' '.join(parameter_names)
                command_names.append(f"• `/{command.qualified_name}{f' {joined_parameter_names}' if joined_parameter_names else ''}`\n>> {command.description}")

            if command_names:
                joined_command_names = "\n\n".join(command_names)
                embed = create_info_embed(interaction, joined_command_names)
                embed.title = "Uncategorized"
                embeds.append(embed)

        groups = [command for command in self.bot.tree.walk_commands() if isinstance(command, app_commands.Group)]
        for start in range(0, len(groups), 10):
            current_group = groups[start:end]
            end += 10

            for group in current_group:
                if group.parent:
                    continue

                commands: list[str] = []
                for command in group.walk_commands():
                    if isinstance(command, app_commands.Group):
                        continue

                    parameters = command.parameters if not isinstance(command, app_commands.Group) else None
                    
                    parameter_names: list[str] = []
                    if parameters is not None:
                        for parameter in parameters:
                            parameter_names.append(f"({parameter.display_name})" if parameter.required else f"[{parameter.display_name}]")
                        
                    joined_parameter_names = ' '.join(parameter_names)
                    commands.append(f"• `/{command.qualified_name}{f' {joined_parameter_names}' if joined_parameter_names else ''}`\n>> {command.description}")

                joined_commands = "\n\n".join(commands)
                embed = create_info_embed(interaction, f">> {group.description}\n\n{joined_commands}")
                embed.title = f"/{group.qualified_name}"
                embeds.append(embed)

        paginator = EmbedPaginator(interaction, embeds)
        embed = paginator.index_page
        await interaction.followup.send(embed=embed, view=paginator)

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        
        psql_daily_table = await psql_user.daily.get_table()

        if psql_daily_table is None:
            embed = create_error_embed(interaction, f"You are currently not registered.")
            await interaction.followup.send(embed=embed)
            return None

        now = discord.utils.utcnow()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
        reset_date = (midnight - now).total_seconds()

        claimed_at = psql_daily_table.claimed_at
        reset_at = psql_daily_table.reset_at
        streak = psql_daily_table.streak

        max_streak = 7
        current_streak = streak + 1
        streak_reward_map: dict[int, tuple[int, Currency | Item]] = {
            0: (200, Currency.silver),
            1: (300, Currency.silver),
            2: (500, Currency.silver),
            3: (1, Item.rare_card_pack),
            4: (1200, Currency.silver),
            5: (2000, Currency.silver),
            6: (5, Currency.gem)
        }

        streak_restarted_text = ""
        if claimed_at is not None:  # type: ignore
            if claimed_at > reset_at:
                streak_str = _streak_to_str(streak, streak_reward_map)
                embed = create_error_embed(interaction, f"You've already claimed your daily reward. Try again in `{seconds_to_human(reset_date)}` at {discord.utils.format_dt(midnight, style='t')}.\n\n**Current Streak:** `x{streak}`\n{streak_str}")
                embed.set_footer(text="Daily rewards reset at 00:00 UTC")
                await interaction.followup.send(embed=embed, view=Promotion())
                return None

            if (days := (now - claimed_at).days) > 1:
                streak_restarted_text = f"You haven't claimed your daily rewards for **`{days} day{'s' if days > 1 else ''}`**! Your streak was reset.\n\n"
                streak = 0
                current_streak = 1

        reward_amount, reward_type = streak_reward_map[streak]
        assert isinstance(interaction.user, discord.Member)
        if is_patreon(interaction.user):
            reward_amount *= 2 
        
        await psql_user.daily.set_claimed_at(now)
        await psql_user.daily.set_streak(current_streak % max_streak)

        reward_text = f"• {reward_type.to_emoji()} {reward_amount:,}"
        if isinstance(reward_type, Currency):
            if reward_type is Currency.gem:
                await psql_user.set_gem(reward_amount)

            elif reward_type is Currency.silver:
                await psql_user.set_silver(reward_amount)

            else:
                raise ValueError("Currency is not defined.")
            
        if isinstance(reward_type, Item):
            await psql_user.inventory.add_item(reward_type, reward_amount)

            reward_text = f"• {reward_type.display()} `x{reward_amount:,}`"

        streak_str = _streak_to_str(current_streak, streak_reward_map)

        embed = create_success_embed(interaction, f"{streak_restarted_text}**You received:**\n{reward_text}\n\n**Current Streak:** `x{current_streak}`\n{streak_str}")
        embed.title = "Here is your daily reward!"
        embed.set_footer(text="Daily rewards reset at 00:00 UTC")
        await interaction.followup.send(embed=embed, view=Promotion())

    @tasks.loop(seconds=10)
    async def daily_reward_resetter(self) -> None:
        now = discord.utils.utcnow()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        await psql.Daily.set_reset_at(self.bot.pool, midnight)

    @daily_reward_resetter.before_loop
    async def before_daily_reward_resetter(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="characters", description="View the list of available characters, omit rarity to view all")
    @app_commands.describe(
        rarity="The rarity that is assigned to the characters",
        craftable="Whether to show if the character is craftable or not"
    )
    @app_commands.autocomplete(rarity=rarity_autocomplete)
    async def show_characters(self, interaction: discord.Interaction, rarity: Optional[str] = None, craftable: bool = False):
        await interaction.response.defer(thinking=True)

        characters = Character.get_characters()
        if rarity is not None:
            try:
                rarity_map = {str(r): r for r in Rarity if r not in Rarity.get_exclusive_rarities()}
                rarity = rarity_map[rarity.casefold()]  # type: ignore
                characters = Character._member_map_[str(rarity)].value
            except KeyError:
                rarity = None
                characters = Character.get_characters()

        if craftable:
            rarity = None
            characters = [
                (character, rarity) for (character, rarity) in Character.get_characters() if character in CraftableCharacterEntity.get_character_names()
            ]

        embeds: list[discord.Embed] = []
        end = 10
        for start in range(0, len(characters), 10):
            current_page = characters[start:end]
            end += 10

            items: list[str] = []
            if rarity is None:
                for character, character_rarity in current_page:
                    items.append(f"• {character_rarity.to_emoji(True)} **{character}**")
            else:
                for character in current_page:
                    items.append(f"• **{character}**")

            joined_items = "\n".join(items)
            embed = create_info_embed(
                interaction,
                f"Viewing available characters.\n\n{joined_items}"
            )
            embed.title = f"{rarity.title()} Characters ({len(characters)})" if rarity is not None else f"All Characters ({len(characters)})"

            if craftable:
                embed.title = f"Craftable Characters ({len(characters)})"

            embeds.append(embed)

        paginator = EmbedPaginator(interaction, embeds)
        embed = paginator.index_page
        await interaction.followup.send(embed=embed, view=paginator)

    @app_commands.command(name="level", description="View your current level or view another user's level")
    @app_commands.describe(user="View this user's level")
    async def show_level(self, interaction: discord.Interaction, user: Optional[discord.Member | discord.User] = None):
        await interaction.response.defer(thinking=True)
        user =  interaction.user if user is None or interaction.user == user else user

        psql_user = psql.User(self.bot.pool, user.id)

        psql_levels_table = await psql_user.levels.get_table()

        if psql_levels_table is None:
            description = "You are currently not registered." if user == interaction.user else "This user is not registered."
            embed = create_error_embed(interaction, description)
            await interaction.followup.send(embed=embed)
            return None

        current_exp = psql_levels_table.current_exp
        max_exp = psql_levels_table.max_exp
        current_level = psql_levels_table.current_level

        exp_bar = psql.Level.create_progress_bar(int((current_exp / max_exp)*100), 100, 16)
        embed = create_info_embed(interaction, f"Viewing the level of {user.mention}\n\n{exp_bar}")
        embed.title = f"Level {current_level}"
        embed.set_footer(text=f"EXP: {current_exp} / {max_exp}")
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=embed)
        

async def setup(bot: Fancards) -> None:
    await bot.add_cog(Uncategorized(bot))
