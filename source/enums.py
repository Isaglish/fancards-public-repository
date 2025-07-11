from __future__ import annotations

import random
from typing import Self, Any, Optional
from pathlib import Path
from enum import Enum

import discord


CHARACTER_PATH = "./source/assets/characters"


class Rarity(Enum):
    common = "common"
    uncommon = "uncommon"
    rare = "rare"
    epic = "epic"
    mythic = "mythic"
    legendary = "legendary"
    exotic = "exotic"
    nightmare = "nightmare"

    # patreon-exclusive rarities
    exclusive_icicle = "exclusive - icicle"

    def __str__(self) -> str:
        return self.value

    def __lt__(self, other: Self) -> bool:
        return self.level < other.level

    def __gt__(self, other: Self) -> bool:
        return self.level > other.level

    @property
    def level(self) -> int:
        mapping = {
            self.common: 1,
            self.uncommon: 2,
            self.rare: 3,
            self.epic: 4,
            self.mythic: 5,
            self.legendary: 6,
            self.exotic: 7,
            self.nightmare: 8
        }
        return mapping[self]

    def title(self) -> str:
        return self.value.title()

    def to_emoji(self, letter: bool = False) -> Fanmoji:
        if letter:
            mapping = {
                self.exclusive_icicle: Fanmoji.exclusive,
                self.nightmare: Fanmoji.nightmare,
                self.exotic: Fanmoji.exotic,
                self.legendary: Fanmoji.legendary,
                self.mythic: Fanmoji.mythic,
                self.epic: Fanmoji.epic,
                self.rare: Fanmoji.rare,
                self.uncommon: Fanmoji.uncommon,
                self.common: Fanmoji.common
            }
        else:
            mapping = {
                self.exclusive_icicle: Fanmoji.exclusive_icicle,
                self.nightmare: Fanmoji.nightmare_card,
                self.exotic: Fanmoji.exotic_card,
                self.legendary: Fanmoji.legendary_card,
                self.mythic: Fanmoji.mythic_card,
                self.epic: Fanmoji.epic_card,
                self.rare: Fanmoji.rare_card,
                self.uncommon: Fanmoji.uncommon_card,
                self.common: Fanmoji.common_card
            }
        return mapping[self]

    def to_embed_color(self) -> discord.Color:
        mapping = {
            self.common: FancadeColor.gray(),
            self.uncommon: FancadeColor.light_green(),
            self.rare: FancadeColor.light_blue(),
            self.epic: FancadeColor.light_purple(),
            self.mythic: FancadeColor.light_red(),
            self.legendary: FancadeColor.light_yellow(),
            self.exotic: FancadeColor.light_orange(),
            self.nightmare: FancadeColor.black(),
            self.exclusive_icicle: FancadeColor.light_blue()
        }
        return mapping[self]

    def to_silver(self) -> tuple[int, int]:
        mapping = {
            self.common: (10, 40),
            self.uncommon: (50, 75),
            self.rare: (100, 350),
            self.epic: (500, 750),
            self.mythic: (1000, 4750),
            self.legendary: (5000, 9750)
        }
        return mapping[self]
    
    def to_star(self) -> int:
        mapping = {
            self.common: 3,
            self.uncommon: 12,
            self.rare: 33,
            self.epic: 72,
            self.mythic: 138,
            self.legendary: 228,
            self.exotic: 486,
            self.nightmare: 972
        }
        return mapping[self]
    
    @classmethod
    def get_valuable_rarities(cls) -> list[Self]:
        return [cls.exotic, cls.nightmare] + cls.get_exclusive_rarities()
    
    @classmethod
    def get_exclusive_rarities(cls) -> list[Self]:
        return [cls.exclusive_icicle]


class SpecialRarity(Enum):
    unknown = "unknown"
    shiny = "shiny"

    def __str__(self) -> str:
        return self.value
    
    def title(self) -> str:
        return self.value.title()


class Condition(Enum):
    damaged = "damaged"
    poor = "poor"
    good = "good"
    near_mint = "near mint"
    mint = "mint"
    pristine = "pristine"

    def __str__(self) -> str:
        return self.value

    def title(self) -> str:
        return self.value.title()

    @property
    def level(self) -> int:
        mapping = {
            self.damaged: 1,
            self.poor: 2,
            self.good: 3,
            self.near_mint: 4,
            self.mint: 5,
            self.pristine: 6
        }
        return mapping[self]

    def to_unicode(self) -> str:
        mapping = {
            self.damaged: "▱▱▱▱▱",
            self.poor: "▰▱▱▱▱",
            self.good: "▰▰▱▱▱",
            self.near_mint: "▰▰▰▱▱",
            self.mint: "▰▰▰▰▱",
            self.pristine: "▰▰▰▰▰"
        }
        return mapping[self]

    def to_star(self) -> int:
        mapping = {
            self.damaged: 3,
            self.poor: 12,
            self.good: 33,
            self.near_mint: 72,
            self.mint: 138,
            self.pristine: 228
        }
        return mapping[self]


class NewUserWeight(Enum):
    rarity = {
        Rarity.common: 65,
        Rarity.uncommon: 20,
        Rarity.rare: 10,
        Rarity.epic: 5
    }
    condition = {
        Condition.damaged: 16,
        Condition.poor: 45,
        Condition.good: 25,
        Condition.near_mint: 10,
        Condition.mint: 3,
        Condition.pristine: 1
    }
    special_rarity = {
        SpecialRarity.unknown: 100,
    }

    def __len__(self) -> int:
        return len(self.value)

    def __getitem__(self, item: Any) -> float:
        return self.value[item]

    def keys(self):
        return self.value.keys()

    def values(self):
        return self.value.values()
    
    def items(self):
        return self.value.items()


class BasicWeight(Enum):
    rarity = {
        Rarity.common: 46.5,
        Rarity.uncommon: 30,
        Rarity.rare: 16.1,
        Rarity.epic: 6,
        Rarity.mythic: 1.25,
        Rarity.legendary: 0.15
    }
    condition = {
        Condition.damaged: 10,
        Condition.poor: 20,
        Condition.good: 45,
        Condition.near_mint: 19,
        Condition.mint: 5,
        Condition.pristine: 1
    }
    special_rarity = {
        SpecialRarity.unknown: 99.95,
        SpecialRarity.shiny: 0.05
    }

    def __len__(self) -> int:
        return len(self.value)

    def __getitem__(self, item: Any) -> float:
        return self.value[item]

    def keys(self):
        return self.value.keys()

    def values(self):
        return self.value.values()
    
    def items(self):
        return self.value.items()


class PremiumWeight(Enum):
    rarity = {
        Rarity.uncommon: 50,
        Rarity.rare: 30,
        Rarity.epic: 16.5,
        Rarity.mythic: 2.75,
        Rarity.legendary: 0.75
    }
    condition = {
        Condition.damaged: 10,
        Condition.poor: 20,
        Condition.good: 45,
        Condition.near_mint: 18.5,
        Condition.mint: 5,
        Condition.pristine: 1.5
    }
    special_rarity = {
        SpecialRarity.unknown: 99.8,
        SpecialRarity.shiny: 0.2
    }

    def __len__(self) -> int:
        return len(self.value)

    def __getitem__(self, item: Any) -> float:
        return self.value[item]

    def keys(self):
        return self.value.keys()

    def values(self):
        return self.value.values()
    
    def items(self):
        return self.value.items()


class FancadeColor(Enum):
    light_brown = "df9191"
    brown = "bc6578"
    dark_brown = "914d5a"
    light_pastel_brown = "fee4e3"
    pastel_brown = "ffcab8"
    dark_pastel_brown = "faaa9f"
    light_purple = "ab83fe"
    purple = "8567d7"
    dark_purple = "654da1"
    light_pink = "ffb2e6"
    pink = "ff8dc9"
    dark_pink = "e868a5"
    light_red = "ff9393"
    red = "fe4a67"
    dark_red = "be304a"
    light_orange = "ffa279"
    orange = "ff6748"
    dark_orange = "cc4a3a"
    light_yellow = "ffff6f"
    yellow = "fece00"
    dark_yellow = "eaa000"
    light_green = "aaff63"
    green = "3cbd46"
    dark_green = "01874a"
    light_blue = "00c0ff"
    blue = "0088fe"
    dark_blue = "0065d9"
    white = "ffffff"
    light_gray = "e3e6ef"
    gray = "acafc2"
    dark_gray = "606279"
    darker_gray = "3b3c50"
    black = "1c1c28"

    def __str__(self) -> str:
        return f"#{self.value}"

    def __call__(self) -> discord.Color:
        return discord.Color.from_str(str(self))


class Character(Enum):
    common = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/common/*.png")]
    uncommon = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/uncommon/*.png")]
    rare = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/rare/*.png")]
    epic = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/epic/*.png")]
    mythic = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/mythic/*.png")]
    legendary = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/legendary/*.png")]
    exotic = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/exotic/*.png")]
    nightmare = [p.stem for p in Path(".").glob(f"{CHARACTER_PATH}/nightmare/*.png")]

    def __len__(self) -> int:
        return len(self.value)

    def __getitem__(self, item: int) -> str:
        return self.value[item]

    def __str__(self) -> str:
        return self.name
    
    @classmethod
    def get_characters(cls) -> list[tuple[str, Rarity]]:
        characters: list[tuple[str, Rarity]] = []
        for member in cls:
            for value in member.value:
                characters.append((value, Rarity[member.name]))

        return characters
    
    @staticmethod
    def get_character_rarity(character_name: str) -> Rarity:
        root_dir = Path(CHARACTER_PATH)
        file_path = next((p.parent for p in root_dir.rglob(f"{character_name}.png")), None)
        assert file_path

        mapping = {str(rarity): rarity for rarity in Rarity}
        return mapping[file_path.name]
    
    @staticmethod
    def get_random_character(rarity: Optional[Rarity] = None) -> str:
        rarity_map = {
            Rarity.common: Character.common,
            Rarity.uncommon: Character.uncommon,
            Rarity.rare: Character.rare,
            Rarity.epic: Character.epic,
            Rarity.legendary: Character.legendary,
            Rarity.mythic: Character.mythic,
            Rarity.exotic: Character.exotic,
            Rarity.nightmare: Character.nightmare
        }

        if rarity in Rarity.get_exclusive_rarities() or rarity is None:
            rarities = [r for r in Rarity]
            character_list = rarity_map[random.choice(rarities)]
            character_name = random.choice(character_list)
        else:
            character_list = rarity_map[rarity]
            character_name = random.choice(character_list)

        return character_name


class Fanmoji(Enum):
    # rarities (letter)
    common = "<:common:1079981432660828300>"
    uncommon = "<:uncommon:1080025872163143720>"
    rare = "<:rare:1079981447567376384>"
    epic = "<:epic:1079981435571687485>"
    mythic = "<:mythic:1079981442915897355>"
    legendary = "<:legendary:1079981440969744464>"
    exotic = "<:exotic:1080025869084532817>"
    nightmare = "<:nightmare:1079981445537349662>"
    shiny = "<:shiny:1079984379775963206>"
    exclusive = "<:exclusive:1099900515321643018>"

    # rarities (cards)
    common_card = "<:common_card:1080279941091950654>"
    uncommon_card = "<:uncommon_card:1080279946926231643>"
    rare_card = "<:rare_card:1079992438661328906>"
    epic_card = "<:epic_card:1079992441794465834>"
    mythic_card = "<:mythic_card:1079992436903911454>"
    legendary_card = "<:legendary_card:1079992434139856969>"
    exotic_card = "<:exotic_card:1079992443509932144>"
    nightmare_card = "<:nightmare_card:1080279943595962369>"
    exclusive_icicle = "<:exclusive_icicle:1099901895138619442>"

    # 2D icons
    next_icon = "<:next:1066775743461343393>"
    previous_icon = "<:previous:1066775842287530014>"
    cross_icon = "<:cross:1066776823041630420>"
    check_icon = "<:checkmark:1066776850765991997>"
    last_page = "<:lastpage:1067087060588048515>"
    first_page = "<:firstpage:1067086989247139874>"
    power_icon = "<:power:1067086964123250779>"
    basket = "<:basket:1069998447769428080>"

    # pixel art
    check_pixel_icon = "<:checkmark_pixel:1078378631518240920>"
    cross_pixel_icon = "<:cross_pixel:1078378634622030003>"

    # custom
    locked = "<:locked:1073963681131544696>"
    unlocked = "<:unlocked:1073961068050780280>"

    level_up = "<:level_up:1071444103251890216>"
    patreon_badge = "<:patreon_badge:1099587190578745424>"
    discord_badge = "<:discord_badge:1099612629540020305>"
    topgg_badge = "<:topgg_badge:1099617871614709770>"

    # currencies
    silver = "<:silver:1008458068226474024>"
    star = "<:star:1065585170113122304>"
    gem = "<:gem:1064152201964040243>"
    voucher = "<:voucher:1099281161534066688>"

    # items
    premium_drop = "<:premium_drop:1069285953132310660>"

    glistening_gem = "<:glistening_gem:1069283444359696505>"
    fusion_crystal = "<:fusion_crystal:1069283094688976897>"
    crown = "<:crown:1071444097488924712>"
    card_sleeve = "<:card_sleeve:1069285949827207239>"

    # card packs
    rare_card_pack = "<:rare_card_pack:1104834476665749616>"
    epic_card_pack = "<:epic_card_pack:1104834480138616923>"
    mythic_card_pack = "<:mythic_card_pack:1104834473331277985>"
    legendary_card_pack = "<:legendary_card_pack:1104834471175397518>"
    exotic_card_pack = "<:exotic_card_pack:1105509848059215872>"

    def __str__(self) -> str:
        return self.value


class Currency(Enum):
    silver = "silver"
    star = "star"
    gem = "gem"
    voucher = "voucher"

    def __str__(self) -> str:
        return self.value

    def to_emoji(self) -> Fanmoji:
        mapping = {
            self.silver: Fanmoji.silver,
            self.star: Fanmoji.star,
            self.gem: Fanmoji.gem,
            self.voucher: Fanmoji.voucher
        }
        return mapping[self]
    
    def display(self) -> str:
        return f"{self.to_emoji()} **{self.value.title()}**"


class Item(Enum):
    glistening_gem = "glistening gem"

    fusion_crystal = "fusion crystal"
    card_sleeve = "card sleeve"
    premium_drop = "premium drop"
    crown = "crown"
    backpack_upgrade = "backpack upgrade"
    
    rare_card_pack = "rare card pack"
    epic_card_pack = "epic card pack"
    mythic_card_pack = "mythic card pack"
    legendary_card_pack = "legendary card pack"
    exotic_card_pack = "exotic card pack"

    def __str__(self) -> str:
        return self.value

    def title(self) -> str:
        return self.value.title()

    def to_emoji(self) -> Fanmoji:
        mapping = {
            self.glistening_gem: Fanmoji.glistening_gem,
            self.fusion_crystal: Fanmoji.fusion_crystal,
            self.card_sleeve: Fanmoji.card_sleeve,
            self.premium_drop: Fanmoji.premium_drop,
            self.crown: Fanmoji.crown,
            self.backpack_upgrade: Fanmoji.level_up,
            self.rare_card_pack: Fanmoji.rare_card_pack,
            self.epic_card_pack: Fanmoji.epic_card_pack,
            self.mythic_card_pack: Fanmoji.mythic_card_pack,
            self.legendary_card_pack: Fanmoji.legendary_card_pack,
            self.exotic_card_pack: Fanmoji.exotic_card_pack
        }
        return mapping[self]
    
    def display(self) -> str:
        return f"{self.to_emoji()} **{self.title()}**"


class PatreonRole(Enum):
    common = 1099000179723604068
    uncommon = 1099008980304547962
    rare = 1099009546481049600
    
    def __str__(self) -> str:
        return self.name
    
    @property
    def role_id(self) -> int:
        return self.value
    
    @classmethod
    def get_role_ids(cls) -> list[int]:
        role_ids: list[int] = []
        for member in cls:
            role_ids.append(member.value)

        return role_ids
    
    @property
    def tier(self) -> int:
        mapping = {
            self.common: 1,
            self.uncommon: 2,
            self.rare: 3
        }
        return mapping[self]
