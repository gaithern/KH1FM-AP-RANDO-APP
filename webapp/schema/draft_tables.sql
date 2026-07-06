-- Tables backing the KH1 item draft feature (draft_tools.py).
-- Not applied automatically - run manually against the PythonAnywhere MySQL
-- database for both the dev and prod environments. Uses the existing
-- `players` table (see mysql_tools.register_player) for player identity.
--
-- Migration for grid draft support, if draft_games/draft_pool/draft_picks
-- already exist from before grid draft was added:
--   ALTER TABLE draft_games MODIFY picks_per_player INT NULL;
--   ALTER TABLE draft_games ADD COLUMN num_grids INT NULL;
--   ALTER TABLE draft_pool ADD COLUMN grid_number INT NULL;
--   ALTER TABLE draft_pool ADD COLUMN grid_row INT NULL;
--   ALTER TABLE draft_pool ADD COLUMN grid_col INT NULL;
--   ALTER TABLE draft_picks ADD COLUMN turn_number INT NOT NULL DEFAULT 0;
--   UPDATE draft_picks SET turn_number = pick_number WHERE turn_number = 0;

CREATE TABLE draft_games (
    game_id               INT AUTO_INCREMENT PRIMARY KEY,
    -- Public identifier (URLs, API paths) - a random code rather than the
    -- sequential game_id, so games can't be found by guessing low integers.
    join_code             VARCHAR(10) NULL UNIQUE,
    created_by_player_id  INT NOT NULL,
    draft_type            VARCHAR(32) NOT NULL DEFAULT 'snake',
    status                VARCHAR(32) NOT NULL DEFAULT 'lobby',
    max_players           INT NOT NULL,
    -- NULL for grid drafts (num_grids drives the item count there instead).
    picks_per_player       INT NULL,
    -- Only set for draft_type = 'grid': number of 3x3 grids to draft
    -- through (9 items each), drafted one at a time in sequence.
    num_grids             INT NULL,
    item_categories       VARCHAR(255) NOT NULL,
    slot_name             VARCHAR(255) NULL,
    server_password       VARCHAR(64) NULL,
    seed_link             VARCHAR(255) NULL,
    seed_zip_path         VARCHAR(500) NULL,
    error_message         VARCHAR(1000) NULL,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by_player_id) REFERENCES players(player_id)
);

CREATE TABLE draft_seats (
    game_id          INT NOT NULL,
    seat_number      INT NOT NULL,
    player_id        INT NOT NULL,
    room_link        VARCHAR(255) NULL,
    items_sent_flag  CHAR(1) NOT NULL DEFAULT 'N',
    joined_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_id, seat_number),
    FOREIGN KEY (game_id) REFERENCES draft_games(game_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

-- item_name is NOT unique per game_id - build_pool() fills out small
-- category selections with duplicate items rather than leaving the draft
-- short, so pool_id is the row identity, not (game_id, item_name).
CREATE TABLE draft_pool (
    pool_id     INT AUTO_INCREMENT PRIMARY KEY,
    game_id     INT NOT NULL,
    item_name   VARCHAR(255) NOT NULL,
    category    VARCHAR(64) NOT NULL,
    taken_flag  CHAR(1) NOT NULL DEFAULT 'N',
    -- Only set for draft_type = 'grid': which 3x3 grid (0-based) this item
    -- belongs to, and its row/col (0-2) within that grid. NULL for snake.
    grid_number INT NULL,
    grid_row    INT NULL,
    grid_col    INT NULL,
    FOREIGN KEY (game_id) REFERENCES draft_games(game_id)
);

CREATE TABLE draft_picks (
    game_id      INT NOT NULL,
    pick_number  INT NOT NULL,
    seat_number  INT NOT NULL,
    item_name    VARCHAR(255) NOT NULL,
    -- Groups picks made in the same turn. Always equal to pick_number for
    -- snake draft (one turn claims one item). Grid draft claims a whole
    -- row/column/diagonal per turn, so several pick_number rows can share
    -- one turn_number - whose turn it is next depends on turn count, not
    -- item count.
    turn_number  INT NOT NULL,
    picked_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_id, pick_number),
    FOREIGN KEY (game_id) REFERENCES draft_games(game_id)
);
