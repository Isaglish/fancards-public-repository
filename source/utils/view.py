from __future__ import annotations
from typing import Any, Self, Union, Callable, Optional, ParamSpec

import discord
from discord import app_commands

from source.enums import Fanmoji
from source.utils import DISCORD_SERVER_URL, PATREON_PAGE_URL
from source.utils.embed import create_error_embed
from source.utils.cooldown import reset_command_cooldown


P = ParamSpec("P")
ConfirmT = Union["Confirm", "EmbedPaginatorWithConfirm"]
TOPGG_VOTE_URL = "https://top.gg/bot/1064145673513087018/vote"


async def wait_for_confirmation(
    _interaction: discord.Interaction,
    _view: ConfirmT,
    _message: discord.WebhookMessage,
    _callback: Callable[P, Any],
    _timeout_message: Optional[str] = None,
    *args: P.args,
    **kwargs: P.kwargs
) -> None:
    await _view.wait()
    if _view.value is None:
        if isinstance(_interaction.command, app_commands.Command) and _interaction.command.extras.get("cooldown", None) is not None:
            reset_command_cooldown(_interaction)
        
        embed = create_error_embed(_interaction, _timeout_message if _timeout_message is not None else "You took too long to respond.")
        await _message.edit(embed=embed, view=None, attachments=[])
        return None

    elif _view.value:
        await _callback(*args, **kwargs)

    else:
        embed = create_error_embed(_interaction, "Command canceled.")
        await _message.edit(embed=embed, view=None, attachments=[])
        return None


class Confirm(discord.ui.View):
    def __init__(self, author: discord.Member, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.value = None
        self.author = author

    @discord.ui.button(emoji=str(Fanmoji.check_icon), style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.value = True
        self.stop()

    @discord.ui.button(emoji=str(Fanmoji.cross_icon), style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.value = False
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author != interaction.user:
            await interaction.response.send_message("You don't have the permission to do that.", ephemeral=True)
            return False
           
        return True
    

class Promotion(discord.ui.View):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.Button(label="Support us!", url=PATREON_PAGE_URL, emoji=str(Fanmoji.patreon_badge)))
        self.add_item(discord.ui.Button(label="Fancards Discord", url=DISCORD_SERVER_URL, emoji=str(Fanmoji.discord_badge)))
        self.add_item(discord.ui.Button(label="Vote for rewards!", url=TOPGG_VOTE_URL, emoji=str(Fanmoji.topgg_badge)))


class EmbedPaginator(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, embeds: list[discord.Embed]):
        super().__init__(timeout=None)
        self.current_page = 0
        self.max_pages = len(embeds)
        self.interaction = interaction
        self.author = interaction.user
        self.embeds = embeds

    @property
    def index_page(self) -> discord.Embed:
        if self.max_pages > 1:
            self.next.disabled = False

        if self.max_pages > 2:
            self.last_page.disabled = False

        if self.max_pages < 3:
            self.remove_item(self.last_page)
            self.remove_item(self.first_page)

        if self.max_pages < 2:
            self.remove_item(self.prev)
            self.remove_item(self.next)
            self.remove_item(self.quit_button)

        embed = self.embeds[0]
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        return embed

    @discord.ui.button(emoji=str(Fanmoji.first_page), style=discord.ButtonStyle.blurple, custom_id="first_page:button", disabled=True)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.current_page = 0
        button.disabled = True
        self.prev.disabled = True

        if self.max_pages > 1:
            self.next.disabled = False

        if self.max_pages > 2:
            self.last_page.disabled = False

        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji=str(Fanmoji.previous_icon), style=discord.ButtonStyle.blurple, custom_id="prev_page:button", disabled=True)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.current_page  = self.current_page - 1 if self.current_page - 1 != -1 else self.current_page
        button.disabled = self.current_page - 1 == -1
        self.first_page.disabled = self.current_page - 1 == -1

        if self.max_pages > 1 and (self.current_page - 1 == -1 or self.current_page - 1 != -1):
            self.next.disabled = False
            
        if self.max_pages > 2 and self.current_page - 1 != -1:
            self.last_page.disabled = False
        
        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji=str(Fanmoji.next_icon), style=discord.ButtonStyle.blurple, custom_id="next_page:button", disabled=True)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.current_page = self.current_page + 1 if self.current_page + 1 != self.max_pages else self.current_page
        button.disabled = self.current_page + 1 >= self.max_pages
        self.last_page.disabled = self.current_page + 1 >= self.max_pages

        if self.max_pages > 1:
            self.prev.disabled = False

        if self.max_pages > 2:
            self.first_page.disabled = False

        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji=str(Fanmoji.last_page), style=discord.ButtonStyle.blurple, custom_id="last_page:button", disabled=True)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.current_page = self.max_pages - 1
        button.disabled = True
        
        if self.max_pages > 1:
            self.next.disabled = True
            self.prev.disabled = False

        if self.max_pages > 2:
            self.first_page.disabled = False

        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji=str(Fanmoji.power_icon), style=discord.ButtonStyle.red, custom_id="quit:button")
    async def quit_button(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        await interaction.response.edit_message(embed=embed, view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author != interaction.user:
            await interaction.response.send_message("You don't have the permission to do that.", ephemeral=True)
            return False

        return True


class EmbedPaginatorWithConfirm(EmbedPaginator):
    def __init__(self, interaction: discord.Interaction, embeds: list[discord.Embed]):
        super().__init__(interaction, embeds)
        self.value = None
        self.remove_item(self.quit_button)

    @discord.ui.button(emoji=str(Fanmoji.check_icon), style=discord.ButtonStyle.green, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.value = True
        self.stop()

    @discord.ui.button(emoji=str(Fanmoji.cross_icon), style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
        self.value = False
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author != interaction.user:
            await interaction.response.send_message("You don't have the permission to do that.", ephemeral=True)
            return False

        return True
