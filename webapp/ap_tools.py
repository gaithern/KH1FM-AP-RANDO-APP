import Utils as ap_utils
import Generate as ap_generate
import json
import re
import requests
import io
import os
import shutil
import sys
import time
import zipfile
from bs4 import BeautifulSoup
from worlds.Files import APWorldContainer

from envr import AP_ROOT, AP_UPLOAD_URL, AP_DAILY_SEED_YAML_DIR, AP_DAILY_SEED_OUTPUT_DIR, AP_LOGIN, AP_DAILY_DUO_SEED_YAML_DIR, AP_DAILY_DUO_SEED_OUTPUT_DIR

ROOM_PORT_POLL_TIMEOUT_SECONDS = 60
ROOM_PORT_POLL_INTERVAL_SECONDS = 3

def get_session():
    session = requests.Session()
    session.get(AP_LOGIN)
    return session

def remove_path_from_filepath(filepath):
  """
  Extracts the filename from a given file path, removing the directory path.

  Args:
    filepath (str): The full path to the file.

  Returns:
    str: The filename without the directory path.
         Returns an empty string if the input is None or empty.
  """
  if not filepath:
    return ""
  return os.path.basename(filepath)

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

def move_file(source_path, destination_path):
  """Moves a file from the source path to the destination path.

  Args:
    source_path (str): The full path to the file to be moved.
    destination_path (str): The full path to the destination directory.
                           If the destination path includes a filename, the file
                           will be renamed during the move.
  """
  try:
    shutil.move(source_path, destination_path)
    print(f"Successfully moved '{source_path}' to '{destination_path}'")
  except FileNotFoundError:
    print(f"Error: Source file not found at '{source_path}'")
  except FileExistsError:
    print(f"Error: Destination file already exists at '{destination_path}'")
  except OSError as e:
    print(f"Error moving file: {e}")

def get_redirected_url(url):
    """
    Follows redirects for a given URL and returns the final redirected URL.

    Args:
      url: The initial URL to check.

    Returns:
      The final URL after all redirects, or None if an error occurs.
    """
    try:
        session = get_session()
        response = session.get(url, allow_redirects=True)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.url
    except session.exceptions.RequestException as e:
        print(f"Error during request: {e}")
        return None

def remove_directory_os_walk(path):
    """
    Removes the specified directory and all files and subdirectories within it
    using os.walk to delete files and then the empty directories.
    This can sometimes be more robust with permissions.

    Args:
        path (str): The path to the directory to remove.
    """
    if not os.path.exists(path):
        print(f"Directory not found: {path}")
        return

    try:
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                filepath = os.path.join(root, name)
                try:
                    os.remove(filepath)
                    print(f"Removed file: {filepath}")
                except Exception as e:
                    print(f"Error removing file '{filepath}': {e}")
            for name in dirs:
                dirpath = os.path.join(root, name)
                try:
                    os.rmdir(dirpath)
                    print(f"Removed directory: {dirpath}")
                except OSError as e:
                    print(f"Error removing directory '{dirpath}': {e}")
        try:
            os.rmdir(path)
            print(f"Removed top-level directory: {path}")
        except OSError as e:
            print(f"Error removing top-level directory '{path}': {e}")

    except Exception as e:
        print(f"An error occurred while removing directory '{path}': {e}")

def get_nested_zip(zip_file_path):
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
            for item in zip_file.namelist():
                if os.path.splitext(item)[1].lower() == '.zip':
                    return item
            return None
    except zipfile.BadZipFile:
        return None

def extract_zip(zip_file_path):
    """Extracts a zip file to a folder with the same name."""

    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        # Get the name of the zip file without the extension
        folder_name = os.path.splitext(zip_file_path)[0]

        # Create the folder if it doesn't exist
        os.makedirs(folder_name, exist_ok=True)

        # Extract all contents of the zip file to the folder
        zip_ref.extractall(folder_name)

def set_root():
    ap_utils.local_path.cached_path = AP_ROOT

def build_kh1_apworld():
    """Zips the worlds/kh1 package into an in-memory .apworld archive."""
    world_dir = os.path.join(AP_ROOT, 'worlds', 'kh1')
    manifest_path = os.path.join(world_dir, 'archipelago.json')
    with open(manifest_path, 'r', encoding='utf-8') as manifest_file:
        manifest = json.load(manifest_file)

    # Container format fields (version/compatible_version) describe the .apworld zip
    # scheme itself, not the world, so they're pulled live from Files.py rather than
    # hand-maintained in archipelago.json. Mirrors Archipelago's own "Build APWorlds"
    # launcher component (worlds/LauncherComponents.py: _build_apworlds).
    apworld = APWorldContainer()
    apworld.game = manifest['game']
    manifest.update(apworld.get_manifest())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(world_dir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for filename in files:
                if filename.endswith('.pyc'):
                    continue
                file_path = os.path.join(root, filename)
                arcname = os.path.join('kh1', os.path.relpath(file_path, world_dir))
                if file_path == manifest_path:
                    zip_file.writestr(arcname, json.dumps(manifest))
                else:
                    zip_file.write(file_path, arcname)
    buffer.seek(0)
    return buffer

def generate(players_folder, server_password=None):
    """Generates a multiworld from the YAMLs in players_folder. If
    server_password is given, it's baked into the multidata so any room
    created from the resulting zip can be administered via `!admin login
    <server_password>` - otherwise (the default, used by /generate,
    /daily_seed, /daily_duo_seed) admin is disabled, unchanged from
    today's behavior. Returns (output_zip_path, multiworld) - callers that
    need the resolved player name (e.g. after a YAML's `name:` used a
    template placeholder like {number}) can read
    multiworld.get_player_name(1)."""
    sys.argv.extend(["--player_files_path", players_folder])
    set_root()
    erargs, seed = ap_generate.main()
    from Main import main as ERmain
    from settings import get_settings
    baked_server_options = None
    if server_password is not None:
        baked_server_options = {**get_settings().server_options.as_dict(), "server_password": server_password}
    multiworld = ERmain(erargs, seed, baked_server_options=baked_server_options)
    return (f"{AP_ROOT}output/AP_{multiworld.seed_name}.zip", multiworld)

def new_room_link(seed_link):
    """Derives a fresh room from an already-uploaded seed link, same as
    mysql_tools.get_players_daily_seed does per-player for the daily seed."""
    return get_redirected_url(seed_link.replace("/seed/", "/new_room/"))

def get_room_connect_address(room_link):
    """Polls the room page for its `/connect <address>:<port>` hint (shown
    once the real archipelago.gg site has launched that room's server
    process - this can lag a few seconds behind room creation) and returns
    the address:port string an AP client can connect to."""
    session = get_session()
    deadline = time.monotonic() + ROOM_PORT_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        room_html = session.get(room_link).text
        match = re.search(r"/connect ([^\s:']+):(\d+)", room_html)
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        time.sleep(ROOM_PORT_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Room at {room_link} never reported a connect address")

def get_seed_link(file_path):
    with open(file_path, 'rb') as f:
        files = {'file': (os.path.basename(file_path), f)}
        session = get_session()
        response = session.post(AP_UPLOAD_URL, files=files)
        response.raise_for_status()
        html_string = response.text
        soup = BeautifulSoup(html_string, 'html.parser')
        title_text = soup.title.string
        seed = title_text.split("View Seed ")[-1]
        seed_url = f"https://archipelago.gg/seed/{seed}"
        return seed_url

def remove_output(file_path):
    os.remove(file_path)

def get_inner_zip_name(file_path):
    ap_zip_file = file_path
    nested_zip = get_nested_zip(ap_zip_file)
    if nested_zip:
        extract_zip(ap_zip_file)
        ap_zip_file = ap_zip_file.replace(".zip", "") + "/" + nested_zip
    return ap_zip_file

def generate_daily_seed(date):
    generation_zip_filepath, _ = generate(AP_DAILY_SEED_YAML_DIR)
    generation_zip_filename = remove_path_from_filepath(generation_zip_filepath)
    move_file(generation_zip_filepath, AP_DAILY_SEED_OUTPUT_DIR)
    generation_zip = f"{AP_DAILY_SEED_OUTPUT_DIR}/{generation_zip_filename}"
    inner_zip_name = get_inner_zip_name(generation_zip)
    seed_link = get_seed_link(generation_zip)
    return seed_link, inner_zip_name

def generate_daily_duo_seed(date):
    generation_zip_filepath, _ = generate(AP_DAILY_DUO_SEED_YAML_DIR)
    generation_zip_filename = remove_path_from_filepath(generation_zip_filepath)
    move_file(generation_zip_filepath, AP_DAILY_DUO_SEED_OUTPUT_DIR)
    generation_zip = f"{AP_DAILY_DUO_SEED_OUTPUT_DIR}/{generation_zip_filename}"
    seed_link = get_seed_link(generation_zip)
    return seed_link