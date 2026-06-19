from flask import Flask, request, jsonify, send_file, make_response, redirect
from flask_cors import CORS
import pymysql  # Import the PyMySQL library
import os
import requests
import urllib.parse
from envr import AP_UPLOAD_URL, YAMLS_ROOT, ALLOWED_RETURN_ORIGINS
import mysql_tools
import ap_tools
import oauth_tools

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
                file_path = ap_tools.generate(player_path)
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