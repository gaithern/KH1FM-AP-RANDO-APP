from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
import pymysql  # Import the PyMySQL library
import os
import requests
from envr import AP_UPLOAD_URL, YAMLS_ROOT
import mysql_tools
import ap_tools

app = Flask(__name__)
CORS(app)

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
                        download_name=os.path.basename(inner_zip)
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
    data = request.get_json()
    discord_id = data.get('discord_id')
    discord_name = data.get('discord_name')

    mysql_tools.register_player(discord_id, discord_name)
    room_link, seed_zip_path = mysql_tools.get_players_daily_seed(discord_id)

    if os.path.exists(seed_zip_path):
        try:
            response = make_response(send_file(
                seed_zip_path,
                mimetype='application/zip',
                as_attachment=True,
                download_name=os.path.basename(seed_zip_path)
            ))
            response.headers['X-Room-Link'] = room_link
            return response, 200
        except Exception as e:
            return jsonify({'error': 'Something went wrong'}), 500
    else:
        return jsonify({'error': 'Generated file not found'}), 500

@app.route('/daily_seed_complete', methods=['POST'])
def daily_seed_complete():
    try:
        data = request.get_json()
        discord_id = data.get('discord_id')
        return_string = mysql_tools.check_daily_seed_complete(discord_id)
        return jsonify({'message': return_string}), 200
    except Exception as e:
        return jsonify({'error': 'Something went wrong'}), 500

@app.route('/daily_leaderboard', methods=['POST'])
def daily_leaderboard():
    try:
        return_string = mysql_tools.get_daily_leaderboard()
        return jsonify({'message': return_string}), 200
    except Exception as e:
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

        discord_id_1 = author.get('discord_id')
        discord_name_1 = author.get('discord_name')
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
        data = request.get_json()  # Parse JSON payload
        if not data:
            return jsonify({'error': 'No JSON payload received'}), 400

        author = data.get('author', {})
        discord_id = author.get('discord_id')
        discord_name = author.get('discord_name')

        # Call your existing logic
        return_string = mysql_tools.get_teams_daily_seed(discord_id)
        return jsonify({'message': return_string}), 200
    except Exception as e:
        return jsonify({'error': f'Something went wrong: {e}'}), 500

@app.route('/daily_duo_seed_complete', methods=['POST'])
def daily_duo_seed_complete():
    try:
        data = request.get_json()
        discord_id = data.get('discord_id')
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
        return jsonify({'error': 'Something went wrong'}), 500

if __name__ == '__main__':
    app.run(debug=True)