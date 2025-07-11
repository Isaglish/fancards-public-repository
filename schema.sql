DO $$ BEGIN
    CREATE TYPE card_rarity AS ENUM (
        'common', 'uncommon',
        'rare', 'epic',
        'mythic', 'legendary',
        'exotic', 'nightmare',
        'exclusive - icicle'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE card_condition as ENUM (
        'damaged',
        'poor',
        'good',
        'near mint',
        'mint',
        'pristine'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE card_special_rarity as ENUM (
        'unknown',
        'shiny'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE item as ENUM (
        'glistening gem',
        'fusion crystal',
        'card sleeve',
        'crown',
        'rare card pack'
        'epic card pack'
        'mythic card pack'
        'legendary card pack'
        'exotic card pack'
        'premium drop'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    silver BIGINT DEFAULT 0,
    star BIGINT DEFAULT 0,
    gem BIGINT DEFAULT 0,
    voucher BIGINT DEFAULT 0,
    registered_at TIMESTAMP WITH TIME ZONE,
    backpack_level INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS levels (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    current_exp INTEGER DEFAULT 0,
    current_level INTEGER DEFAULT 1,
    max_exp INTEGER DEFAULT 42
);

CREATE TABLE IF NOT EXISTS cards (
    card_id VARCHAR(6) PRIMARY KEY,
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    rarity card_rarity,
    condition card_condition,
    special_rarity card_special_rarity,
    character_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE,
    has_sleeve BOOLEAN DEFAULT FALSE,
    locked BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS inventory (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    item item,
    amount INTEGER,
    UNIQUE (item, owner_id)
);

CREATE TABLE IF NOT EXISTS config (
    guild_id BIGINT PRIMARY KEY,
    level_toggle BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS daily (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    claimed_at TIMESTAMP WITH TIME ZONE,
    reset_at TIMESTAMP WITH TIME ZONE,
    streak INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vote (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    voted_at TIMESTAMP WITH TIME ZONE,
    vote_streak INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS blacklist (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    reason VARCHAR(255)
);
