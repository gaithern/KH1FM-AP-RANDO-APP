from flask import Flask, request, jsonify, send_file, make_response, redirect
from flask_cors import CORS
import pymysql  # Import the PyMySQL library
import asyncio
import os
import requests
import secrets
import threading
import urllib.parse
from envr import AP_UPLOAD_URL, YAMLS_ROOT, DRAFT_YAMLS_ROOT, ALLOWED_RETURN_ORIGINS
import mysql_tools
import ap_tools
import oauth_tools
import draft_formats
import draft_item_pool
import draft_send_tools
import draft_tools

app = Flask(__name__)
CORS(app)

def get_identity_from_request(data):
    """Prefers the verified Discord identity from a Bearer session token
    (website login flow) and falls back to the discord_id/discord_name the
    caller supplied directly (Discord bot flow, which already gets a
    trustworthy ID from ctx.author.id)."""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        discord_id, discord_name = oauth_tools.verify_session_token(auth_header[len('Bearer '):])
        if discord_id is not None:
            return discord_id, discord_name
    return data.get('discord_id'), data.get('discord_name')

def prepare_path(path):
    if not os.path.exists(path):
        os.makedirs(path)
    else:
        for filename in os.listdir(path):
            file_path = os.path.join(path, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    print(f"Removed file: {file_path}")
                except OSError as e:
                    print(f"Error removing file '{file_path}': {e}")

@app.route('/generate', methods=['POST'])
def generate():
    discord_id = request.form.get('discord_id')
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        player_path = f'{YAMLS_ROOT}/{discord_id}/'
        prepare_path(player_path)
        filename = os.path.join(player_path, file.filename)
        try:
            file.save(filename)
            try:
                file_path, _ = ap_tools.generate(player_path)
                unzipped_folder_path = file_path[:-4]
                seed_link = ap_tools.get_seed_link(file_path)
                inner_zip = ap_tools.get_inner_zip_name(file_path)
                if os.path.exists(inner_zip):
                    response = make_response(send_file(
                        inner_zip,
                        mimetype='application/zip',
                        as_attachment=True,
                        download_name='mod.zip'
                    ))
                    response.headers['X-Seed-Link'] = seed_link
                    response.headers['X-Generation-Message'] = 'Generation completed successfully.'
                    response.headers['Access-Control-Expose-Headers'] = 'X-Seed-Link'
                    ap_tools.remove_output(file_path)
                    ap_tools.remove_directory_os_walk(unzipped_folder_path)
                    return response, 200
                else:
                    return jsonify({'error': 'Generated file not found'}), 500
                return jsonify({'message': f'Generation completed successfully.  Seed link: {seed_link}'}), 200
            except Exception as e:
                print(f'Internal server error: {e}')
                return jsonify({'error': f'Internal server error: {e}'}), 500
        except Exception as e:
            return jsonify({'error': f'Error saving file: {e}'}), 500
    return jsonify({'error': 'Something went wrong'}), 500

@app.route('/daily_seed', methods=['POST'])
def daily_seed():
    data = request.get_json(silent=True) or {}
    discord_id, discord_name = get_identity_from_request(data)

    mysql_tools.register_player(discord_id, discord_name)
    room_link, seed_zip_path = mysql_tools.get_players_daily_seed(discord_id)

    if os.path.exists(seed_zip_path):
        try:
            response = make_response(send_file(
                seed_zip_path,
                mimetype='application/zip',
                as_attachment=True,
                download_name='mod.zip'
            ))
            response.headers['X-Room-Link'] = room_link
            response.headers['Access-Control-Expose-Headers'] = 'X-Room-Link'
            return response, 200
        except Exception as e:
            return jsonify({'error': 'Something went wrong'}), 500
    else:
        return jsonify({'error': 'Generated file not found'}), 500

@app.route('/daily_seed_complete', methods=['POST'])
def daily_seed_complete():
    try:
        data = request.get_json(silent=True) or {}
        discord_id, _ = get_identity_from_request(data)
        return_string = mysql_tools.check_daily_seed_complete(discord_id)
        return jsonify({'message': return_string}), 200
    except Exception as e:
        print(f'Error in daily_seed_complete: {e}')
        return jsonify({'error': 'Something went wrong'}), 500

@app.route('/daily_leaderboard', methods=['POST'])
def daily_leaderboard():
    try:
        message, leaderboard = mysql_tools.get_daily_leaderboard()
        return jsonify({'message': message, 'leaderboard': leaderboard}), 200
    except Exception as e:
        print(f'Error in daily_leaderboard: {e}')
        return jsonify({'error': 'Something went wrong'}), 500

from flask import Flask, request, jsonify
import mysql_tools  # assuming your helper functions are here

@app.route('/daily_duo_team_up', methods=['POST'])
def daily_duo_team_up():
    try:
        data = request.get_json()  # Parse JSON payload
        if not data:
            return jsonify({'error': 'No JSON payload received'}), 400

        author = data.get('author', {})
        mentioned = data.get('mentioned', {})

        discord_id_1, discord_name_1 = get_identity_from_request(author)
        discord_id_2 = mentioned.get('discord_id')
        discord_name_2 = mentioned.get('discord_name')

        if None in (discord_id_1, discord_name_1, discord_id_2, discord_name_2):
            return jsonify({'error': 'Missing required data'}), 400

        # Call your existing logic
        return_string = mysql_tools.daily_duo_team_up(
            discord_id_1, discord_name_1, discord_id_2, discord_name_2
        )
        return jsonify({'message': return_string}), 200
    except Exception as e:
        return jsonify({'error': f'Something went wrong: {e}'}), 500

@app.route('/daily_duo_seed', methods=['POST'])
def daily_duo_seed():
    try:
        data = request.get_json(silent=True) or {}
        author = data.get('author', {})
        discord_id, discord_name = get_identity_from_request(author)

        # Call your existing logic
        return_string = mysql_tools.get_teams_daily_seed(discord_id)
        return jsonify({'message': return_string}), 200
    except Exception as e:
        return jsonify({'error': f'Something went wrong: {e}'}), 500

@app.route('/daily_duo_seed_complete', methods=['POST'])
def daily_duo_seed_complete():
    try:
        data = request.get_json(silent=True) or {}
        discord_id, _ = get_identity_from_request(data)
        return_string = mysql_tools.check_daily_duo_seed_complete(discord_id)
        return jsonify({'message': return_string}), 200
    except Exception as e:
        return jsonify({'error': 'Something went wrong'}), 500

@app.route('/daily_duo_leaderboard', methods=['POST'])
def daily_duo_leaderboard():
    try:
        return_string = mysql_tools.get_daily_duo_leaderboard()
        return jsonify({'message': return_string}), 200
    except Exception as e:
        print(f'Error in daily_duo_leaderboard: {e}')
        return jsonify({'error': 'Something went wrong'}), 500

@app.route('/draft/item_categories', methods=['GET'])
def draft_item_categories():
    return jsonify({
        'categories': draft_item_pool.available_categories(),
        'default': draft_item_pool.DEFAULT_CATEGORIES,
    }), 200

def _require_draft_identity(data):
    """Like get_identity_from_request, but also registers the player and
    resolves their internal player_id (draft_tools' tables key off
    player_id, same as the rest of the schema)."""
    discord_id, discord_name = get_identity_from_request(data)
    if discord_id is None:
        return None
    mysql_tools.register_player(discord_id, discord_name)
    return draft_tools.get_player_id(discord_id)

def _draft_identity_from_bearer():
    """GET requests carry no JSON body, so /state only supports the
    website-login Bearer token flow, not the discord_id/discord_name
    fallback the bot uses."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    discord_id, _ = oauth_tools.verify_session_token(auth_header[len('Bearer '):])
    return draft_tools.get_player_id(discord_id) if discord_id else None

@app.route('/draft/create', methods=['POST'])
def draft_create():
    data = request.get_json(silent=True) or {}
    player_id = _require_draft_identity(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        draft_type = data.get('draft_type', 'snake')
        join_code = draft_tools.create_game(
            player_id,
            draft_type,
            int(data['max_players']),
            data.get('item_categories') or draft_item_pool.DEFAULT_CATEGORIES,
            picks_per_player=int(data['picks_per_player']) if draft_type != 'grid' else None,
            num_grids=int(data['num_grids']) if draft_type == 'grid' else None,
        )
        return jsonify({'join_code': join_code}), 200
    except (ValueError, KeyError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

@app.route('/draft/join', methods=['POST'])
def draft_join():
    data = request.get_json(silent=True) or {}
    player_id = _require_draft_identity(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(data.get('join_code', ''))
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    try:
        seat_number = draft_tools.join_game(game_id, player_id)
        return jsonify({'seat_number': seat_number}), 200
    except (ValueError, KeyError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

@app.route('/draft/<join_code>/start', methods=['POST'])
def draft_start(join_code):
    data = request.get_json(silent=True) or {}
    player_id = _require_draft_identity(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(join_code)
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    try:
        draft_tools.start_game(game_id, player_id)
        return jsonify({'message': 'Draft started'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@app.route('/draft/<join_code>/pick', methods=['POST'])
def draft_pick(join_code):
    data = request.get_json(silent=True) or {}
    player_id = _require_draft_identity(data)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(join_code)
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    game = draft_tools.get_game(game_id)
    try:
        if game['draft_type'] == 'grid':
            draft_tools.record_grid_pick(
                game_id, player_id,
                int(data['grid_number']), data.get('line_type'), int(data['line_index']),
            )
        else:
            item_name = data.get('item_name')
            if not item_name:
                return jsonify({'error': 'item_name is required'}), 400
            draft_tools.record_pick(game_id, player_id, item_name)
        return jsonify({'message': 'Pick recorded'}), 200
    except (ValueError, KeyError, TypeError) as e:
        return jsonify({'error': str(e)}), 400

@app.route('/draft/<join_code>/state', methods=['GET'])
def draft_state(join_code):
    player_id = _draft_identity_from_bearer()
    game_id = draft_tools.resolve_join_code(join_code)
    game = draft_tools.get_game(game_id) if game_id is not None else None
    if game is None:
        return jsonify({'error': 'No such draft game'}), 404

    seats = draft_tools.get_seats(game_id)
    picks = draft_tools.get_picks(game_id)
    my_seat = next((s for s in seats if s['player_id'] == player_id), None) if player_id else None
    is_grid = game['draft_type'] == 'grid'

    on_the_clock_seat = None
    if game['status'] == draft_tools.STATUS_DRAFTING and seats:
        draft_format = draft_formats.get_draft_format(game['draft_type'])
        pool_size = draft_tools.total_items(game, len(seats))
        on_the_clock_index = draft_format.seat_on_the_clock(len(seats), picks, pool_size)
        on_the_clock_seat = seats[on_the_clock_index]['seat_number'] if on_the_clock_index is not None else None

    grids = None
    current_grid_number = None
    if is_grid and game['status'] != draft_tools.STATUS_LOBBY:
        cells = draft_tools.get_grid(game_id)
        grids = [[[None] * 3 for _ in range(3)] for _ in range(game['num_grids'])]
        for cell in cells:
            grids[cell['grid_number']][cell['grid_row']][cell['grid_col']] = {
                'item_name': cell['item_name'],
                'category': cell['category'],
                'taken': cell['taken_flag'] == 'Y',
            }
        untaken_grid_numbers = {cell['grid_number'] for cell in cells if cell['taken_flag'] == 'N'}
        current_grid_number = min(untaken_grid_numbers) if untaken_grid_numbers else None

    return jsonify({
        'status': game['status'],
        'draft_type': game['draft_type'],
        'max_players': game['max_players'],
        'picks_per_player': game['picks_per_player'],
        'num_grids': game['num_grids'],
        'item_categories': game['item_categories'].split(','),
        'is_host': player_id is not None and player_id == game['created_by_player_id'],
        'seats': [{'seat_number': s['seat_number'], 'discord_name': s['discord_name']} for s in seats],
        'pool': draft_tools.get_pool(game_id) if (not is_grid and game['status'] != draft_tools.STATUS_LOBBY) else [],
        'grids': grids,
        'current_grid_number': current_grid_number,
        'picks': picks,
        'on_the_clock_seat': on_the_clock_seat,
        'your_turn': bool(my_seat) and on_the_clock_seat == (my_seat or {}).get('seat_number'),
        'room_link': my_seat['room_link'] if my_seat else None,
        'error_message': game['error_message'],
    }), 200

@app.route('/draft/<join_code>/upload_yaml', methods=['POST'])
def draft_upload_yaml(join_code):
    player_id = _require_draft_identity(request.form)
    if player_id is None:
        return jsonify({'error': 'Not logged in'}), 401
    game_id = draft_tools.resolve_join_code(join_code)
    if game_id is None:
        return jsonify({'error': 'No such draft game'}), 404
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    game_folder = f'{DRAFT_YAMLS_ROOT}/{game_id}/'
    prepare_path(game_folder)
    filepath = os.path.join(game_folder, file.filename)
    file.save(filepath)

    try:
        draft_tools.start_generation(game_id, player_id, filepath)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    threading.Thread(target=_run_draft_finalize, args=(game_id, game_folder), daemon=True).start()
    return jsonify({'message': 'Generating seed...'}), 200

def _run_draft_finalize(game_id, game_folder):
    """Runs off the request thread: generates the seed once, then creates
    one room per seat and delivers that seat's own drafted items into it.
    Any failure is recorded on the game so the frontend can surface it
    instead of polling forever."""
    try:
        server_password = secrets.token_urlsafe(16)
        file_path, multiworld = ap_tools.generate(game_folder, server_password=server_password)
        # The host's YAML `name:` can use AP's templating placeholders (e.g.
        # "Player{number}") that only get resolved during generation, so the
        # real slot name has to come from the generated multiworld, not a
        # text-parse of the uploaded YAML.
        slot_name = multiworld.get_player_name(1)
        seed_link = ap_tools.get_seed_link(file_path)
        ap_tools.remove_output(file_path)
        draft_tools.set_generation_result(game_id, server_password, seed_link, slot_name)

        game = draft_tools.get_game(game_id)
        for seat in draft_tools.get_seats(game_id):
            room_link = ap_tools.new_room_link(seed_link)
            draft_tools.set_seat_room_link(game_id, seat['seat_number'], room_link)

            connect_address = ap_tools.get_room_connect_address(room_link)
            item_names = [p['item_name'] for p in draft_tools.get_picks(game_id)
                          if p['seat_number'] == seat['seat_number']]
            asyncio.run(draft_send_tools.send_drafted_items(
                connect_address, game['slot_name'], server_password, item_names))
            draft_tools.set_seat_items_sent(game_id, seat['seat_number'])
    except Exception as e:
        print(f'Error finalizing draft game {game_id}: {e}')
        draft_tools.set_error(game_id, str(e))

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
    except Exception as e:
        print(f'Error in kh1_apworld: {e}')
        return jsonify({'error': 'Something went wrong'}), 500

@app.route('/oauth/login', methods=['GET'])
def oauth_login():
    return_to = request.args.get('return_to', '')
    parsed = urllib.parse.urlparse(return_to)
    origin = f'{parsed.scheme}://{parsed.netloc}'
    if not parsed.scheme or origin not in ALLOWED_RETURN_ORIGINS:
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
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Failed to complete Discord login: {e}'}), 502

    token = oauth_tools.make_session_token(discord_id, discord_name)
    return redirect(f'{return_to}#token={token}')

if __name__ == '__main__':
    app.run(debug=True)