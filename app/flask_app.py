import asyncio
import os
import secrets
import threading
import urllib.parse

import requests
from flask import Flask, request, jsonify, send_file, make_response, redirect
from flask_cors import CORS

import ap_tools
import draft_formats
import draft_item_pool
import draft_send_tools
import draft_tools
import mysql_tools
import oauth_tools
import options_tools
from envr import YAMLS_ROOT, DRAFT_YAMLS_ROOT, ALLOWED_RETURN_ORIGINS

BEARER_PREFIX = 'Bearer '

app = Flask(__name__)
CORS(app)


def get_bearer_token():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith(BEARER_PREFIX):
        return None
    return auth_header[len(BEARER_PREFIX):]


def get_identity_from_request(data):
    token = get_bearer_token()
    if token is not None:
        discord_id, discord_name = oauth_tools.verify_session_token(token)
        if discord_id is not None:
            return discord_id, discord_name
    return data.get('discord_id'), data.get('discord_name')


def get_json_body():
    data = request.get_json(silent=True)
    if data is None:
        return {}
    return data


def make_zip_response(zip_path):
    return make_response(send_file(
        zip_path,
        mimetype='application/zip',
        as_attachment=True,
        download_name='mod.zip'
    ))


def get_uploaded_file_error():
    if 'file' not in request.files:
        return 'No file part in the request'
    if request.files['file'].filename == '':
        return 'No selected file'
    return None


def generate_and_send_mod(player_folder):
    generated_zip_path, multiworld = ap_tools.generate(player_folder)
    unzipped_folder_path = generated_zip_path[:-len('.zip')]
    seed_link = ap_tools.get_seed_link(generated_zip_path)
    inner_zip = ap_tools.get_inner_zip_name(generated_zip_path)
    if not os.path.exists(inner_zip):
        return jsonify({'error': 'Generated file not found'}), 500

    response = make_zip_response(inner_zip)
    response.headers['X-Seed-Link'] = seed_link
    response.headers['X-Generation-Message'] = 'Generation completed successfully.'
    response.headers['Access-Control-Expose-Headers'] = 'X-Seed-Link'
    ap_tools.remove_output(generated_zip_path)
    ap_tools.remove_folder_and_contents(unzipped_folder_path)
    return response, 200


@app.route('/generate', methods=['POST'])
def generate():
    discord_id = request.form.get('discord_id')
    file_error = get_uploaded_file_error()
    if file_error is not None:
        return jsonify({'error': file_error}), 400
    file = request.files['file']

    player_folder = f'{YAMLS_ROOT}/{discord_id}/'
    ap_tools.create_or_empty_folder(player_folder)
    yaml_path = os.path.join(player_folder, file.filename)
    try:
        file.save(yaml_path)
    except Exception as error:
        return jsonify({'error': f'Error saving file: {error}'}), 500

    try:
        return generate_and_send_mod(player_folder)
    except Exception as error:
        print(f'Internal server error: {error}')
        return jsonify({'error': f'Internal server error: {error}'}), 500


@app.route('/daily_seed', methods=['POST'])
def daily_seed():
    data = get_json_body()
    discord_id, discord_name = get_identity_from_request(data)

    mysql_tools.register_player(discord_id, discord_name)
    room_link, seed_zip_path = mysql_tools.get_players_daily_seed(discord_id)

    if not os.path.exists(seed_zip_path):
        return jsonify({'error': 'Generated file not found'}), 500
    try:
        response = make_zip_response(seed_zip_path)
        response.headers['X-Room-Link'] = room_link
        response.headers['Access-Control-Expose-Headers'] = 'X-Room-Link'
        return response, 200
    except Exception:
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/daily_seed_complete', methods=['POST'])
def daily_seed_complete():
    try:
        data = get_json_body()
        discord_id, discord_name = get_identity_from_request(data)
        message = mysql_tools.check_daily_seed_complete(discord_id)
        return jsonify({'message': message}), 200
    except Exception as error:
        print(f'Error in daily_seed_complete: {error}')
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/daily_leaderboard', methods=['POST'])
def daily_leaderboard():
    try:
        message, leaderboard = mysql_tools.get_daily_leaderboard()
        return jsonify({'message': message, 'leaderboard': leaderboard}), 200
    except Exception as error:
        print(f'Error in daily_leaderboard: {error}')
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/daily_duo_team_up', methods=['POST'])
def daily_duo_team_up():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON payload received'}), 400

        author = data.get('author', {})
        mentioned = data.get('mentioned', {})

        discord_id_1, discord_name_1 = get_identity_from_request(author)
        discord_id_2 = mentioned.get('discord_id')
        discord_name_2 = mentioned.get('discord_name')

        if None in (discord_id_1, discord_name_1, discord_id_2, discord_name_2):
            return jsonify({'error': 'Missing required data'}), 400

        message = mysql_tools.daily_duo_team_up(discord_id_1, discord_name_1, discord_id_2, discord_name_2)
        return jsonify({'message': message}), 200
    except Exception as error:
        return jsonify({'error': f'Something went wrong: {error}'}), 500


@app.route('/daily_duo_seed', methods=['POST'])
def daily_duo_seed():
    try:
        data = get_json_body()
        author = data.get('author', {})
        discord_id, discord_name = get_identity_from_request(author)
        message = mysql_tools.get_teams_daily_seed(discord_id)
        return jsonify({'message': message}), 200
    except Exception as error:
        return jsonify({'error': f'Something went wrong: {error}'}), 500


@app.route('/daily_duo_seed_complete', methods=['POST'])
def daily_duo_seed_complete():
    try:
        data = get_json_body()
        discord_id, discord_name = get_identity_from_request(data)
        message = mysql_tools.check_daily_duo_seed_complete(discord_id)
        return jsonify({'message': message}), 200
    except Exception:
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/daily_duo_leaderboard', methods=['POST'])
def daily_duo_leaderboard():
    try:
        message = mysql_tools.get_daily_duo_leaderboard()
        return jsonify({'message': message}), 200
    except Exception as error:
        print(f'Error in daily_duo_leaderboard: {error}')
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/draft/item_categories', methods=['GET'])
def draft_item_categories():
    return jsonify({
        'categories': draft_item_pool.available_categories(),
        'default': draft_item_pool.DEFAULT_CATEGORIES,
    }), 200


def register_and_get_draft_player_id(data):
    discord_id, discord_name = get_identity_from_request(data)
    if discord_id is None:
        return None
    mysql_tools.register_player(discord_id, discord_name)
    return draft_tools.get_player_id(discord_id)


def get_draft_player_id_from_bearer_token():
    token = get_bearer_token()
    if token is None:
        return None
    discord_id, discord_name = oauth_tools.verify_session_token(token)
    if not discord_id:
        return None
    return draft_tools.get_player_id(discord_id)


@app.route('/draft/create', methods=['POST'])
def draft_create():
    data = get_json_body()
    player_id = register_and_get_draft_player_id(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        draft_type = data.get('draft_type', 'snake')
        max_players = int(data['max_players'])

        item_categories = data.get('item_categories')
        if not item_categories:
            item_categories = draft_item_pool.available_categories()

        picks_per_player = None
        num_grids = None
        if draft_type == 'grid':
            num_grids = int(data['num_grids'])
        else:
            picks_per_player = int(data['picks_per_player'])

        join_code = draft_tools.create_game(
            player_id,
            draft_type,
            max_players,
            item_categories,
            picks_per_player=picks_per_player,
            num_grids=num_grids,
        )
        return jsonify({'join_code': join_code}), 200
    except (ValueError, KeyError, TypeError) as error:
        return jsonify({'error': str(error)}), 400


@app.route('/draft/join', methods=['POST'])
def draft_join():
    data = get_json_body()
    player_id = register_and_get_draft_player_id(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(data.get('join_code', ''))
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    try:
        seat_number = draft_tools.join_game(game_id, player_id)
        return jsonify({'seat_number': seat_number}), 200
    except (ValueError, KeyError, TypeError) as error:
        return jsonify({'error': str(error)}), 400


@app.route('/draft/<join_code>/start', methods=['POST'])
def draft_start(join_code):
    data = get_json_body()
    player_id = register_and_get_draft_player_id(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(join_code)
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    try:
        selected_item_names = data.get('items')
        draft_tools.start_game(game_id, player_id, selected_item_names)
        return jsonify({'message': 'Draft started'}), 200
    except (ValueError, TypeError) as error:
        return jsonify({'error': str(error)}), 400


@app.route('/draft/<join_code>/pick', methods=['POST'])
def draft_pick(join_code):
    data = get_json_body()
    player_id = register_and_get_draft_player_id(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(join_code)
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    game = draft_tools.get_game(game_id)
    try:
        if game['draft_type'] == 'grid':
            draft_tools.record_grid_pick(
                game_id,
                player_id,
                int(data['grid_number']),
                data.get('line_type'),
                int(data['line_index']),
            )
        else:
            item_name = data.get('item_name')
            if not item_name:
                return jsonify({'error': 'item_name is required'}), 400
            draft_tools.record_pick(game_id, player_id, item_name)
    except (ValueError, KeyError, TypeError) as error:
        return jsonify({'error': str(error)}), 400

    game_after_pick = draft_tools.get_game(game_id)
    if game_after_pick['status'] == draft_tools.STATUS_SENDING_ITEMS:
        start_background_task(run_draft_deliver, game_id)
    return jsonify({'message': 'Pick recorded'}), 200


def get_on_the_clock_seat_number(game, seats, picks):
    if game['status'] != draft_tools.STATUS_DRAFTING:
        return None
    if not seats:
        return None
    draft_format = draft_formats.get_draft_format(game['draft_type'])
    pool_size = draft_tools.total_items(game, len(seats))
    on_the_clock_index = draft_format.seat_on_the_clock(len(seats), picks, pool_size)
    if on_the_clock_index is None:
        return None
    return seats[on_the_clock_index]['seat_number']


def build_empty_grids(number_of_grids):
    grids = []
    for grid_number in range(number_of_grids):
        grid = []
        for row in range(draft_tools.GRID_SIZE):
            grid.append([None] * draft_tools.GRID_SIZE)
        grids.append(grid)
    return grids


def build_grids(game_id, number_of_grids):
    cells = draft_tools.get_grid(game_id)
    grids = build_empty_grids(number_of_grids)
    untaken_grid_numbers = set()
    for cell in cells:
        is_taken = cell['taken_flag'] == 'Y'
        grids[cell['grid_number']][cell['grid_row']][cell['grid_col']] = {
            'item_name': cell['item_name'],
            'category': cell['category'],
            'taken': is_taken,
        }
        if cell['taken_flag'] == 'N':
            untaken_grid_numbers.add(cell['grid_number'])

    current_grid_number = None
    if untaken_grid_numbers:
        current_grid_number = min(untaken_grid_numbers)
    return grids, current_grid_number


@app.route('/draft/<join_code>/state', methods=['GET'])
def draft_state(join_code):
    player_id = get_draft_player_id_from_bearer_token()
    game_id = draft_tools.resolve_join_code(join_code)
    game = None
    if game_id is not None:
        game = draft_tools.get_game(game_id)
    if game is None:
        return jsonify({'error': 'No such draft game'}), 404

    seats = draft_tools.get_seats(game_id)
    picks = draft_tools.get_picks(game_id)

    my_seat = None
    if player_id:
        my_seat = draft_tools.find_seat_for_player(seats, player_id)

    is_grid = game['draft_type'] == 'grid'
    pool_is_built = game['status'] not in draft_tools.STATUSES_BEFORE_DRAFT_STARTS
    on_the_clock_seat = get_on_the_clock_seat_number(game, seats, picks)

    grids = None
    current_grid_number = None
    if is_grid and pool_is_built:
        grids, current_grid_number = build_grids(game_id, game['num_grids'])

    pool = []
    if not is_grid and pool_is_built:
        pool = draft_tools.get_pool(game_id)

    your_turn = False
    room_link = None
    if my_seat is not None:
        your_turn = on_the_clock_seat == my_seat['seat_number']
        room_link = my_seat['room_link']

    is_host = player_id is not None and player_id == game['created_by_player_id']

    public_seats = []
    for seat in seats:
        public_seats.append({'seat_number': seat['seat_number'], 'discord_name': seat['discord_name']})

    return jsonify({
        'status': game['status'],
        'draft_type': game['draft_type'],
        'max_players': game['max_players'],
        'picks_per_player': game['picks_per_player'],
        'num_grids': game['num_grids'],
        'item_categories': game['item_categories'].split(','),
        'is_host': is_host,
        'seats': public_seats,
        'candidates': draft_tools.get_candidates(game_id),
        'required_pool_size': draft_tools.total_items(game, len(seats)),
        'pool': pool,
        'grids': grids,
        'current_grid_number': current_grid_number,
        'picks': picks,
        'on_the_clock_seat': on_the_clock_seat,
        'your_turn': your_turn,
        'room_link': room_link,
        'error_message': game['error_message'],
    }), 200


@app.route('/draft/<join_code>/upload_yaml', methods=['POST'])
def draft_upload_yaml(join_code):
    player_id = register_and_get_draft_player_id(request.form)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(join_code)
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    file_error = get_uploaded_file_error()
    if file_error is not None:
        return jsonify({'error': file_error}), 400
    file = request.files['file']

    game_folder = f'{DRAFT_YAMLS_ROOT}/{game_id}/'
    ap_tools.create_or_empty_folder(game_folder)
    yaml_path = os.path.join(game_folder, file.filename)
    file.save(yaml_path)

    try:
        draft_tools.start_generation(game_id, player_id, yaml_path)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    start_background_task(run_draft_generate, game_id, game_folder)
    return jsonify({'message': 'Generating seed...'}), 200


def start_background_task(task_function, *task_arguments):
    thread = threading.Thread(target=task_function, args=task_arguments, daemon=True)
    thread.start()


def run_draft_generate(game_id, game_folder):
    try:
        server_password = secrets.token_urlsafe(16)
        generated_zip_path, multiworld = ap_tools.generate(game_folder, server_password=server_password)
        slot_name = multiworld.get_player_name(draft_item_pool.HOST_PLAYER_NUMBER)
        game = draft_tools.get_game(game_id)
        item_categories = game['item_categories'].split(',')
        candidates = draft_item_pool.seed_candidates(multiworld, item_categories)
        seed_link = ap_tools.get_seed_link(generated_zip_path)
        ap_tools.remove_output(generated_zip_path)
        draft_tools.set_generation_result(game_id, server_password, seed_link, slot_name, candidates)
    except Exception as error:
        print(f'Error generating draft game {game_id}: {error}')
        draft_tools.set_generation_failed(game_id, str(error))


def get_item_names_picked_by_seat(game_id, seat_number):
    item_names = []
    for pick in draft_tools.get_picks(game_id):
        if pick['seat_number'] == seat_number:
            item_names.append(pick['item_name'])
    return item_names


def run_draft_deliver(game_id):
    try:
        game = draft_tools.get_game(game_id)
        for seat in draft_tools.get_seats(game_id):
            seat_number = seat['seat_number']
            room_link = ap_tools.new_room_link(game['seed_link'])
            draft_tools.set_seat_room_link(game_id, seat_number, room_link)

            connect_address = ap_tools.get_room_connect_address(room_link)
            item_names = get_item_names_picked_by_seat(game_id, seat_number)
            asyncio.run(draft_send_tools.send_drafted_items(
                connect_address, game['slot_name'], game['server_password'], item_names))
            draft_tools.set_seat_items_sent(game_id, seat_number)
    except Exception as error:
        print(f'Error delivering items for draft game {game_id}: {error}')
        draft_tools.set_error(game_id, str(error))


@app.route('/kh1.apworld', methods=['GET'])
def kh1_apworld():
    try:
        buffer = ap_tools.build_kh1_apworld()
        return send_file(
            buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='kh1.apworld'
        )
    except Exception as error:
        print(f'Error in kh1_apworld: {error}')
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/kh1_options', methods=['GET'])
def kh1_options():
    try:
        return jsonify(options_tools.get_kh1_options_schema()), 200
    except Exception as error:
        print(f'Error in kh1_options: {error}')
        return jsonify({'error': 'Something went wrong'}), 500


@app.route('/oauth/login', methods=['GET'])
def oauth_login():
    return_to = request.args.get('return_to', '')
    parsed_url = urllib.parse.urlparse(return_to)
    origin = f'{parsed_url.scheme}://{parsed_url.netloc}'
    if not parsed_url.scheme or origin not in ALLOWED_RETURN_ORIGINS:
        return jsonify({'error': 'Invalid return_to origin'}), 400
    return redirect(oauth_tools.build_authorize_url(return_to))


@app.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    error = request.args.get('error')
    if error:
        return jsonify({'error': f'Discord OAuth error: {error}'}), 400

    return_to = oauth_tools.verify_state(request.args.get('state', ''))
    if return_to is None:
        return jsonify({'error': 'Invalid or expired OAuth state'}), 400

    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'Missing authorization code'}), 400

    try:
        discord_id, discord_name = oauth_tools.exchange_code_for_user(code)
    except requests.exceptions.RequestException as request_error:
        return jsonify({'error': f'Failed to complete Discord login: {request_error}'}), 502

    token = oauth_tools.make_session_token(discord_id, discord_name)
    return redirect(f'{return_to}#token={token}')


if __name__ == '__main__':
    app.run(debug=True)
