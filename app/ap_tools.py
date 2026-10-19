import Utils as ap_utils
import Generate as ap_generate
import io
import json
import os
import re
import shutil
import sys
import time
import zipfile

import requests
from bs4 import BeautifulSoup
from worlds.Files import APWorldContainer

from envr import (
    AP_ROOT,
    AP_UPLOAD_URL,
    AP_LOGIN,
    AP_DAILY_SEED_YAML_DIR,
    AP_DAILY_SEED_OUTPUT_DIR,
    AP_DAILY_DUO_SEED_YAML_DIR,
    AP_DAILY_DUO_SEED_OUTPUT_DIR,
)

ROOM_PORT_POLL_TIMEOUT_SECONDS = 60
ROOM_PORT_POLL_INTERVAL_SECONDS = 3


def get_session():
    session = requests.Session()
    session.get(AP_LOGIN)
    return session


def create_or_empty_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)
        return

    for file_name in os.listdir(path):
        file_path = os.path.join(path, file_name)
        if not os.path.isfile(file_path):
            continue
        try:
            os.remove(file_path)
            print(f"Removed file: {file_path}")
        except OSError as error:
            print(f"Error removing file '{file_path}': {error}")


def move_file(source_path, destination_path):
    try:
        shutil.move(source_path, destination_path)
        print(f"Successfully moved '{source_path}' to '{destination_path}'")
    except FileNotFoundError:
        print(f"Error: Source file not found at '{source_path}'")
    except FileExistsError:
        print(f"Error: Destination file already exists at '{destination_path}'")
    except OSError as error:
        print(f"Error moving file: {error}")


def get_redirected_url(url):
    session = get_session()
    response = session.get(url, allow_redirects=True)
    response.raise_for_status()
    return response.url


def remove_file_and_report(file_path):
    try:
        os.remove(file_path)
        print(f"Removed file: {file_path}")
    except Exception as error:
        print(f"Error removing file '{file_path}': {error}")


def remove_empty_folder_and_report(folder_path):
    try:
        os.rmdir(folder_path)
        print(f"Removed directory: {folder_path}")
    except OSError as error:
        print(f"Error removing directory '{folder_path}': {error}")


def remove_folder_and_contents(path):
    if not os.path.exists(path):
        print(f"Directory not found: {path}")
        return

    try:
        for folder, subfolder_names, file_names in os.walk(path, topdown=False):
            for file_name in file_names:
                remove_file_and_report(os.path.join(folder, file_name))
            for subfolder_name in subfolder_names:
                remove_empty_folder_and_report(os.path.join(folder, subfolder_name))

        try:
            os.rmdir(path)
            print(f"Removed top-level directory: {path}")
        except OSError as error:
            print(f"Error removing top-level directory '{path}': {error}")
    except Exception as error:
        print(f"An error occurred while removing directory '{path}': {error}")


def find_nested_zip_name(zip_file_path):
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
            for name in zip_file.namelist():
                extension = os.path.splitext(name)[1]
                if extension.lower() == '.zip':
                    return name
            return None
    except zipfile.BadZipFile:
        return None


def extract_zip(zip_file_path):
    folder_name = os.path.splitext(zip_file_path)[0]
    with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
        os.makedirs(folder_name, exist_ok=True)
        zip_file.extractall(folder_name)


def set_root():
    ap_utils.local_path.cached_path = AP_ROOT


def build_kh1_apworld():
    world_folder = os.path.join(AP_ROOT, 'worlds', 'kh1')
    manifest_path = os.path.join(world_folder, 'archipelago.json')
    with open(manifest_path, 'r', encoding='utf-8') as manifest_file:
        manifest = json.load(manifest_file)

    apworld = APWorldContainer()
    apworld.game = manifest['game']
    container_format_fields = apworld.get_manifest()
    manifest.update(container_format_fields)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for folder, subfolder_names, file_names in os.walk(world_folder):
            if '__pycache__' in folder.split(os.sep):
                continue
            for file_name in file_names:
                if file_name.endswith('.pyc'):
                    continue
                file_path = os.path.join(folder, file_name)
                path_inside_world = os.path.relpath(file_path, world_folder)
                path_inside_zip = os.path.join('kh1', path_inside_world)
                if file_path == manifest_path:
                    zip_file.writestr(path_inside_zip, json.dumps(manifest))
                else:
                    zip_file.write(file_path, path_inside_zip)
    buffer.seek(0)
    return buffer


def generate(players_folder, server_password=None):
    sys.argv.extend(["--player_files_path", players_folder])
    set_root()
    generation_args, seed = ap_generate.main()

    from Main import main as run_generation
    from settings import get_settings

    baked_server_options = None
    if server_password is not None:
        baked_server_options = dict(get_settings().server_options.as_dict())
        baked_server_options["server_password"] = server_password

    multiworld = run_generation(generation_args, seed, baked_server_options=baked_server_options)
    output_zip_path = f"{AP_ROOT}output/AP_{multiworld.seed_name}.zip"
    return output_zip_path, multiworld


def new_room_link(seed_link):
    new_room_url = seed_link.replace("/seed/", "/new_room/")
    return get_redirected_url(new_room_url)


def get_room_connect_address(room_link):
    session = get_session()
    deadline = time.monotonic() + ROOM_PORT_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        room_html = session.get(room_link).text
        connect_hint = re.search(r"/connect ([^\s:']+):(\d+)", room_html)
        if connect_hint:
            address = connect_hint.group(1)
            port = connect_hint.group(2)
            return f"{address}:{port}"
        time.sleep(ROOM_PORT_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Room at {room_link} never reported a connect address")


def get_seed_link(file_path):
    with open(file_path, 'rb') as zip_file:
        files = {'file': (os.path.basename(file_path), zip_file)}
        session = get_session()
        response = session.post(AP_UPLOAD_URL, files=files)
        response.raise_for_status()

    page = BeautifulSoup(response.text, 'html.parser')
    page_title = page.title.string
    seed = page_title.split("View Seed ")[-1]
    return f"https://archipelago.gg/seed/{seed}"


def remove_output(file_path):
    os.remove(file_path)


def get_inner_zip_name(file_path):
    nested_zip_name = find_nested_zip_name(file_path)
    if not nested_zip_name:
        return file_path
    extract_zip(file_path)
    extracted_folder = file_path.replace(".zip", "")
    return extracted_folder + "/" + nested_zip_name


def generate_into_folder(yaml_folder, output_folder):
    generated_zip_path, multiworld = generate(yaml_folder)
    generated_zip_name = os.path.basename(generated_zip_path)
    move_file(generated_zip_path, output_folder)
    return f"{output_folder}/{generated_zip_name}"


def generate_daily_seed():
    generated_zip = generate_into_folder(AP_DAILY_SEED_YAML_DIR, AP_DAILY_SEED_OUTPUT_DIR)
    inner_zip_name = get_inner_zip_name(generated_zip)
    seed_link = get_seed_link(generated_zip)
    return seed_link, inner_zip_name


def generate_daily_duo_seed():
    generated_zip = generate_into_folder(AP_DAILY_DUO_SEED_YAML_DIR, AP_DAILY_DUO_SEED_OUTPUT_DIR)
    seed_link = get_seed_link(generated_zip)
    return seed_link
