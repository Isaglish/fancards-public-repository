from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass

import discord

from source.enums import Item, Rarity, Condition, SpecialRarity, Fanmoji, PatreonRole
from source.utils import has_minimum_patreon_role
from source.utils.embed import create_success_embed

if TYPE_CHECKING:
    import asyncpg


@dataclass(frozen=True)
class UserTable:
    """Represents the Postgres ``users`` table.
    
    Attributes
    ----------
    id: :class:`int`
        The primary key ``id`` of ``users``.
    user_id: :class:`int`
        The ID of the user in Discord.
    silver: :class:`int`
        The amount of silver the user has.
    star: :class:`int`
        The amount of star the user has.
    gem: :class:`int`
        The amount of gem the user has.
    voucher: :class:`int`
        The amount of voucher the user has.
    registered_at: :class:`datetime.datetime`
        The date/time of when the user registered.
    backpack_level: :class:`int`
        The backpack level of the user.
    """
    id: int
    user_id: int
    silver: int
    star: int
    gem: int
    voucher: int
    registered_at: datetime.datetime
    backpack_level: int


@dataclass(frozen=True)
class InventoryTable:
    """Represents the Postgres ``inventory`` table.
    
    Attributes
    ----------
    id: :class:`int`
        The primary key ``id`` of ``inventory``.
    owner_id: :class:`int`
        The foreign key of ``inventory``. References the primary key ``id`` of ``users``.
    item: :class:`Item`
        The enum of the item.
    amount: :class:`int`
        The amount of the item.
    """
    id: int
    owner_id: int
    item: Item
    amount: int


@dataclass(frozen=True)
class CardTable:
    """Represents the Postgres ``cards`` table.
    
    Attributes
    ----------
    card_id: :class:`int`
        The primary key ``card_id`` of ``cards``. Represents the six-character ID of the card.
    owner_id: :class:`int`
        The foreign key of ``cards``. References the primary key ``id`` of ``users``.
    rarity: :class:`Rarity`
        The enum of the card rarity.
    condition: :class:`Condition`
        The enum of the card condition.
    special_rarity: :class:`SpecialRarity`
        The enum of the card special rarity.
    character_name: :class:`str`
        The name of the card character.
    created_at: :class:`datetime.datetime`
        The date/time of when the card was created/generated.
    has_sleeve: :class:`bool`
        Whether the card has a sleeve.
    locked: :class:`bool`
        Whether the card is locked from being burnt.
    """
    card_id: str
    owner_id: int
    rarity: Rarity
    condition: Condition
    special_rarity: SpecialRarity
    character_name: str
    created_at: datetime.datetime
    has_sleeve: bool = False
    locked: bool = False


@dataclass(frozen=True)
class LevelTable:
    """Represents the Postgres ``levels`` table.
    
    Attributes
    ----------
    user_id: :class:`int`
        The foreign key of ``levels``. References the primary key ``id`` of ``users``.
    current_exp: :class:`int`
        The current experience points of the user.
    current_level: :class:`int`
        The current level of the user.
    max_exp: :class:`int`
        The maximum amount of experience points required for the user to level up.
    """
    user_id: int
    current_exp: int = 0
    current_level: int = 1
    max_exp: int = 43


@dataclass(frozen=True)
class ConfigTable:
    """Represents the Postgres ``config`` table.
    
    Attributes
    ----------
    guild_id: :class:`int`
        The primary key ``guild_id`` of ``config``. Represents the ID of the guild in Discord.
    level_toggle: :class:`bool`
        Whether to allow level-up notifications in the guild.
    """
    guild_id: int
    level_toggle: bool = True


@dataclass(frozen=True)
class DailyTable:
    """Represents the Postgres ``daily`` table.
    
    Attributes
    ----------
    user_id: :class:`int`
        The foreign key of ``daily``. References the primary key ``id`` of ``users``.
    claimed_at: :class:`datetime.datetime`
        The date/time of when the user last claimed their daily rewards.
    reset_at: :class:`datetime.datetime`
        The date/time of when all daily rewards reset (00:00 UTC).
    streak: :class:`int`
        The daily rewards claim streak of the user.
    """
    user_id: int
    claimed_at: datetime.datetime
    reset_at: datetime.datetime
    streak: int = 0


@dataclass(frozen=True)
class VoteTable:
    """Represents the Postgres ``vote`` table.
    
    Attributes
    ----------
    user_id: :class:`int`
        The foreign key of ``vote``. References the primary key ``id`` of ``users``.
    voted_at: :class:`datetime.datetime`
        The date/time of when the user last voted for the bot.
    vote_streak: :class:`int`
        The current voting streak of the user.
    """
    user_id: int
    voted_at: Optional[datetime.datetime]
    vote_streak: int = 0


@dataclass(frozen=True)
class BlacklistTable:
    """Represents the Postgres ``blacklist`` table.
    
    Attributes
    ----------
    id: :class:`int`
        The primary key ``id`` of ``blacklist``.
    user_id: :class:`int`
        The ID of the user in Discord.
    reason: :class:`str`
        The reason of being put in the blacklist.
    """
    id: int
    user_id: int
    reason: Optional[str]


class Blacklist:
    """Helper class for ``blacklist`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], user_id: int):
        self.pool = pool
        self.user_id = user_id

    async def get_table(self) -> Optional[BlacklistTable]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM blacklist
            WHERE user_id = $1;
            """
            result = await connection.fetchrow(query, self.user_id)

        if result is None:
            return None

        return BlacklistTable(**dict(result))
    
    async def add_user(self, user_id: int, reason: Optional[str] = None) -> None:
        async with self.pool.acquire() as connection:
            query = """
            INSERT INTO blacklist (user_id, reason) VALUES ($1, $2);
            """
            await connection.execute(query, user_id, reason)

    async def remove_user(self, user_id: int) -> None:
        async with self.pool.acquire() as connection:
            query = """
            DELETE FROM blacklist
            WHERE user_id = $1;
            """
            await connection.execute(query, user_id)


class Vote:
    """Helper class for ``vote`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], user_id: int):
        self.pool = pool
        self.user_id = user_id

    async def get_table(self) -> Optional[VoteTable]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM vote
            WHERE user_id = (
                SELECT id FROM users
                WHERE user_id = $1
            );
            """
            result = await connection.fetchrow(query, self.user_id)

        if result is None:
            return None

        return VoteTable(**dict(result))
    
    async def set_voted_at(self, voted_at: datetime.datetime) -> None:
        query = """
        UPDATE vote
        SET voted_at = $1
        WHERE user_id = (
            SELECT id FROM users
            WHERE user_id = $2
        );
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, voted_at, self.user_id)

    async def set_vote_streak(self, streak: int) -> None:
        query = """
        UPDATE vote
        SET vote_streak = $1
        WHERE user_id = (
            SELECT id FROM users
            WHERE user_id = $2
        )
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, streak, self.user_id)


class Daily:
    """Helper class for ``daily`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], user_id: int):
        self.pool = pool
        self.user_id = user_id

    async def get_table(self) -> Optional[DailyTable]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM daily
            WHERE user_id = (
                SELECT id FROM users
                WHERE user_id = $1
            );
            """
            result = await connection.fetchrow(query, self.user_id)

        if result is None:
            return None

        return DailyTable(**dict(result))
    
    async def set_claimed_at(self, claimed_at: datetime.datetime) -> None:
        query = """
        UPDATE daily
        SET claimed_at = $1
        WHERE user_id = (
            SELECT id FROM users
            WHERE user_id = $2
        );
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, claimed_at, self.user_id)

    @staticmethod
    async def set_reset_at(pool: asyncpg.Pool[asyncpg.Record], reset_at: datetime.datetime) -> None:
        query = """
        UPDATE daily
        SET reset_at = $1;
        """
        async with pool.acquire() as connection:
            await connection.execute(query, reset_at)

    async def set_streak(self, streak: int) -> None:
        query = """
        UPDATE daily
        SET streak = $1
        WHERE user_id = (
            SELECT id FROM users
            WHERE user_id = $2
        )
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, streak, self.user_id)


class Config:
    """Helper class for ``config`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], guild_id: int):
        self.pool = pool
        self.guild_id = guild_id

    async def get_table(self) -> Optional[ConfigTable]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM config
            WHERE guild_id = $1;
            """
            result = await connection.fetchrow(query, self.guild_id)

        if result is None:
            return None

        return ConfigTable(**dict(result))


class Level:
    """Helper class for ``levels`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], user_id: int):
        self.pool = pool
        self.user_id = user_id

    @staticmethod
    def create_progress_bar(progress: int, max_progress: int, count: int) -> str:
        filled = int(progress / max_progress * count)
        bar = f"{'▰'*filled}{'▱'*(count - filled)} {progress}%"
        return bar
    
    @staticmethod
    def calculate_exp(current_level: int) -> int:
        if current_level < 16:
            max_exp = (current_level**2) + (6*7)
        elif current_level < 31:
            max_exp = int(2.5*(current_level**2) - (40.5*current_level) + 360)
        else:
            max_exp = int(4.5*(current_level**2) - (162.5*current_level) + 2220)

        return max_exp

    async def get_table(self) -> Optional[LevelTable]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM levels
            WHERE user_id = (
                SELECT id FROM users
                WHERE user_id = $1
            );
            """
            result = await connection.fetchrow(query, self.user_id)

        if result is None:
            return None

        return LevelTable(**dict(result))
    
    async def set_current_level(self, level: int) -> None:
        async with self.pool.acquire() as connection:
            max_exp = self.calculate_exp(level)

            query = """
            UPDATE levels
            SET current_exp = 0,
                current_level = $1,
                max_exp = $2
            WHERE user_id = (SELECT id FROM users WHERE user_id = $3);
            """
            await connection.execute(query, level, max_exp, self.user_id)
    
    async def add_exp(
        self,
        member: discord.Member,
        exp: int,
        current_exp: int,
        current_level: int,
        max_exp: int
    ) -> int:
        """Add EXP to the user and handles other calculation such as
        ``current_exp``, ``current_level``, and ``max_exp``.
        
        Returns the amount of EXP that was given.
        """
        max_level = 100

        if has_minimum_patreon_role(member, PatreonRole.uncommon):
            exp *= 2

        current_exp += exp
        while current_exp >= max_exp:
            if current_level < max_level:
                current_level += 1

            current_exp -= max_exp
            max_exp = self.calculate_exp(current_level)

            if current_level == max_level:
                current_exp = max_exp
                break

        async with self.pool.acquire() as connection:
            query = """
            UPDATE levels
            SET current_exp = $1,
                current_level = $2,
                max_exp = $3
            WHERE user_id = (SELECT id FROM users WHERE user_id = $4);
            """
            await connection.execute(query, current_exp, current_level, max_exp, self.user_id)

        return exp
    
    async def handle_exp_addition(
        self,
        interaction: discord.Interaction,
        exp: int
    ) -> int:
        psql_user = User(self.pool, interaction.user.id)

        psql_user_table = await psql_user.get_table()
        assert psql_user_table

        psql_levels_table = await psql_user.levels.get_table()

        if psql_levels_table is None:
            raise ValueError("User is not registered")

        assert interaction.guild
        psql_config_table = await Config(self.pool, interaction.guild.id).get_table()

        level_toggle = None
        if psql_config_table is not None:
            level_toggle = psql_config_table.level_toggle

        current_exp = psql_levels_table.current_exp
        current_level = psql_levels_table.current_level
        old_level = current_level
        max_exp = psql_levels_table.max_exp

        levelup_notification = (level_toggle or level_toggle is None)
        if old_level != current_level and levelup_notification:
            exp_bar = self.create_progress_bar(int((current_exp / max_exp)*100), 100, 16)
            embed = create_success_embed(interaction, f"{Fanmoji.level_up} {interaction.user.mention} You Leveled Up!\n\n{exp_bar}")
            embed.title = f"Level {old_level} -> Level {current_level}"
            embed.set_footer(text=f"EXP: {current_exp} / {max_exp}")
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed)

        assert isinstance(interaction.user, discord.Member)
        return await self.add_exp(interaction.user, exp, current_exp, current_level, max_exp)


class Card:
    """Helper class for ``cards`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], user_id: int):
        self.pool = pool
        self.user_id = user_id

    async def invert_locked(self, card_id: str) -> None:
        query = """
        UPDATE cards
        SET locked = NOT locked
        WHERE card_id = $1;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, card_id)

    async def invert_has_sleeve(self, card_id: str) -> None:
        query = """
        UPDATE cards
        SET has_sleeve = NOT has_sleeve
        WHERE card_id = $1;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, card_id)

    async def change_card_condition(self, card_id: str, condition: Condition) -> None:
        query = """
        UPDATE cards
        SET condition = $1
        WHERE card_id = $2;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, condition, card_id)

    async def change_card_owner(self, card_id: str, new_owner_id: int) -> None:
        query = """
        UPDATE cards
        SET owner_id = $1
        WHERE card_id = $2 AND owner_id = (
            SELECT id FROM users
            WHERE user_id = $3
        );
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, new_owner_id, card_id, self.user_id)

    async def get_most_recently_obtained_card(self) -> Optional[CardTable]:
        query = """
        SELECT * FROM cards
        WHERE owner_id = (
            SELECT id FROM users
            WHERE user_id = $1
        )
        ORDER BY created_at DESC
        LIMIT 1;
        """
        async with self.pool.acquire() as connection:
            result = await connection.fetchrow(query, self.user_id)

        if result is None:
            return None
        
        return CardTable(**dict(result))
    
    async def get_card(self, card_id: str) -> Optional[CardTable]:
        query = """
        SELECT * FROM cards
        WHERE card_id = $1;
        """
        async with self.pool.acquire() as connection:
            result = await connection.fetchrow(query, card_id)

        if result is None:
            return None
        
        return CardTable(**dict(result))
    
    async def get_cards(self) -> Optional[list[CardTable]]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM cards
            WHERE owner_id = (
                SELECT id FROM users
                WHERE user_id = $1
            );
            """
            results = await connection.fetch(query, self.user_id)

        if not results:
            return None

        return [CardTable(**dict(result)) for result in results]
    
    async def get_card_owner_id(self, card_id: str) -> Optional[int]:
        """Returns the Discord User ID of the card owner."""
        query = """
        SELECT users.user_id FROM cards
        JOIN users ON cards.owner_id = users.id
        WHERE cards.card_id = $1;
        """
        async with self.pool.acquire() as connection:
            result = await connection.fetchval(query, card_id)

        if result is None:
            return None
        
        return result
    
    async def get_cards_by_character_name(self, character_name: str) -> Optional[list[CardTable]]:
        query = """
        SELECT * FROM cards
        WHERE owner_id = (SELECT id FROM users WHERE users.user_id = $1) AND
            (cards.character_name = $2 OR cards.character_name = $3);
        """
        async with self.pool.acquire() as connection:
            results = await connection.fetch(query, self.user_id, character_name.casefold(), character_name.title())

        if not results:
            return None
        
        return [CardTable(**dict(result)) for result in results]
    
    async def get_cards_by_card_id(self, card_ids: list[str]) -> Optional[list[CardTable]]:
        query = """
        SELECT * FROM cards
        WHERE card_id = ANY($1::TEXT[]);
        """
        async with self.pool.acquire() as connection:
            results = await connection.fetch(query, card_ids)

        if not results:
            return None
        
        return [CardTable(**dict(result)) for result in results]
    
    async def get_close_matches_by_card_id(self, card_id: str) -> Optional[list[CardTable]]:
        query = """
        SELECT * FROM cards
        WHERE card_id LIKE ($2 || '%') AND owner_id = (SELECT id FROM users WHERE users.user_id = $1);
        """
        async with self.pool.acquire() as connection:
            results = await connection.fetch(query, self.user_id, card_id)

        if not results:
            return None
        
        return [CardTable(**dict(result)) for result in results]
    
    async def delete_card(self, card_id: str) -> None:
        query = """
        DELETE FROM cards
        WHERE card_id = $1;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, card_id)

    async def delete_cards_by_card_id(self, card_ids: list[str]) -> None:
        query = """
        DELETE FROM cards
        WHERE card_id = ANY($1::TEXT[]);
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, card_ids)

    async def add_card(self, card_table: CardTable) -> None:
        query = """
        INSERT INTO cards (card_id, owner_id, rarity, condition, special_rarity, character_name, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7);
        """
        async with self.pool.acquire() as connection:
            await connection.execute(
                query,
                card_table.card_id,
                card_table.owner_id,
                card_table.rarity,
                card_table.condition,
                card_table.special_rarity,
                card_table.character_name,
                card_table.created_at
            )
    

class Inventory:
    """Helper class for ``inventory`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], user_id: int):
        self.pool = pool
        self.user_id = user_id

    async def get_item(self, item: Item) -> Optional[InventoryTable]:
        query = """
        SELECT * FROM inventory
        WHERE item = $1 AND owner_id = (
            SELECT id FROM users
            WHERE user_id = $2
        );
        """
        async with self.pool.acquire() as connection:
            result = await connection.fetchrow(query, item, self.user_id)

        if result is None:
            return None
        
        return InventoryTable(**dict(result))

    async def get_items(self) -> Optional[list[InventoryTable]]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM inventory
            WHERE owner_id = (
                SELECT id FROM users
                WHERE user_id = $1
            );
            """
            results = await connection.fetch(query, self.user_id)

        if not results:
            return None

        return [InventoryTable(**dict(result)) for result in results]
    
    async def add_item(self, item: Item, amount: int = 1) -> None:
        query = """
        INSERT INTO inventory (owner_id, item, amount)
        VALUES ((
            SELECT id FROM users
            WHERE user_id = $1
        ), $2, $3)
        ON CONFLICT (item, owner_id)
        DO UPDATE SET amount = inventory.amount + $3;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, self.user_id, item, amount)

    async def remove_item(self, item: Item, amount: int = 1) -> None:
        query = """
        UPDATE inventory
        SET amount = amount - $1
        WHERE item = $2 AND owner_id = (
            SELECT id FROM users
            WHERE user_id = $3
        );
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, amount, item, self.user_id)

            query = """
            DELETE FROM inventory
            WHERE amount < 1;
            """
            await connection.execute(query)


class User:
    """Helper class for ``users`` table operations.
    
    Attributes
    ----------
    pool: :class:`asyncpg.Pool`
        The pool to use when connecting to the database.
    user_id: :class:`int`
        The ID of the user in Discord.
    """

    def __init__(self, pool: asyncpg.Pool[asyncpg.Record], user_id: int):
        self.pool = pool
        self.user_id = user_id

    async def register(self) -> int:
        """Register a user into the database with all the default table values.

        Returns
        ----------
        :class:`int`
            The primary key ``id`` of table ``users``
        """
        async with self.pool.acquire() as connection:
            user_table = await self.get_table()
            
            if user_table is None:
                user_id = await connection.fetchval(
                    "INSERT INTO users (user_id, registered_at) VALUES ($1, $2) RETURNING id;",
                    self.user_id,
                    discord.utils.utcnow()
                )
                await connection.execute("INSERT INTO levels (user_id) VALUES ($1);", user_id)

                now = discord.utils.utcnow()
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

                await connection.execute("INSERT INTO daily (user_id, reset_at) VALUES ($1, $2);", user_id, midnight)
                await connection.execute("INSERT INTO vote (user_id) VALUES ($1);", user_id)

                return user_id

        return user_table.id

    async def get_table(self) -> Optional[UserTable]:
        async with self.pool.acquire() as connection:
            query = """
            SELECT * FROM users
            WHERE user_id = $1;
            """
            result = await connection.fetchrow(query, self.user_id)

        if result is None:
            return None

        return UserTable(**dict(result))
    
    @property
    def inventory(self) -> Inventory:
        return Inventory(self.pool, self.user_id)
    
    @property
    def cards(self) -> Card:
        return Card(self.pool, self.user_id)
    
    @property
    def levels(self) -> Level:
        return Level(self.pool, self.user_id)
    
    @property
    def daily(self) -> Daily:
        return Daily(self.pool, self.user_id)
    
    @property
    def vote(self) -> Vote:
        return Vote(self.pool, self.user_id)
    
    async def set_silver(self, amount: int, subtract: bool = False) -> None:
        """Add or subtract silver from the user."""
        amount = amount*-1 if subtract else amount
        query = """
        UPDATE users
        SET silver = silver + $1
        WHERE user_id = $2;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, amount, self.user_id)

    async def set_star(self, amount: int, subtract: bool = False) -> None:
        """Add or subtract stars from the user."""
        amount = amount*-1 if subtract else amount
        query = """
        UPDATE users
        SET star = star + $1
        WHERE user_id = $2;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, amount, self.user_id)

    async def set_gem(self, amount: int, subtract: bool = False) -> None:
        """Add or subtract gems from the user."""
        amount = amount*-1 if subtract else amount
        query = """
        UPDATE users
        SET gem = gem + $1
        WHERE user_id = $2;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, amount, self.user_id)

    async def set_voucher(self, amount: int, subtract: bool = False) -> None:
        """Add or subtract vouchers from the user."""
        amount = amount*-1 if subtract else amount
        query = """
        UPDATE users
        SET voucher = voucher + $1
        WHERE user_id = $2;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, amount, self.user_id)

    async def increase_backpack_level(self) -> None:
        query = """
        UPDATE users
        SET backpack_level = backpack_level + 1
        WHERE user_id = $1;
        """
        async with self.pool.acquire() as connection:
            await connection.execute(query, self.user_id)
