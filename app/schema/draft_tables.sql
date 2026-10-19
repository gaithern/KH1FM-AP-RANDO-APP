CREATE TABLE draft_games (
    game_id               INT AUTO_INCREMENT PRIMARY KEY,
    join_code             VARCHAR(10) NULL UNIQUE,
    created_by_player_id  INT NOT NULL,
    draft_type            VARCHAR(32) NOT NULL DEFAULT 'snake',
    status                VARCHAR(32) NOT NULL DEFAULT 'lobby',
    max_players           INT NOT NULL,
    picks_per_player      INT NULL,
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

CREATE TABLE draft_pool (
    pool_id     INT AUTO_INCREMENT PRIMARY KEY,
    game_id     INT NOT NULL,
    item_name   VARCHAR(255) NOT NULL,
    category    VARCHAR(64) NOT NULL,
    taken_flag  CHAR(1) NOT NULL DEFAULT 'N',
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
    turn_number  INT NOT NULL,
    picked_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_id, pick_number),
    FOREIGN KEY (game_id) REFERENCES draft_games(game_id)
);

CREATE TABLE draft_candidates (
    game_id    INT NOT NULL,
    item_name  VARCHAR(255) NOT NULL,
    category   VARCHAR(64) NOT NULL,
    quantity   INT NOT NULL,
    PRIMARY KEY (game_id, item_name),
    FOREIGN KEY (game_id) REFERENCES draft_games(game_id)
);
