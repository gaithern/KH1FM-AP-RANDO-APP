import json
import os

import discord
import requests
from discord.ext import commands

import discord_bot_settings

TOKEN = discord_bot_settings.DISCORD_BOT_TOKEN
URL_BASE = discord_bot_settings.URL_BASE

FLASK_REGISTER_URL = os.environ.get('FLASK_WRITE_URL', f'{URL_BASE}/register')
FLASK_AP_GENERATE_URL = os.environ.get('FLASK_AP_UPLOAD_URL', f'{URL_BASE}/generate')
FLASK_AP_DAILY_SEED_URL = os.environ.get('FLASK_AP_DAILY_SEED_URL', f'{URL_BASE}/daily_seed')
FLASK_AP_DAILY_SEED_COMPLETE_URL = os.environ.get('FLASK_AP_DAILY_SEED_COMPLETE_URL', f'{URL_BASE}/daily_seed_complete')
FLASK_AP_DAILY_LEADERBOARD_URL = os.environ.get('FLASK_AP_DAILY_LEADERBOARD_URL', f'{URL_BASE}/daily_leaderboard')
FLASK_AP_DAILY_DUO_TEAM_UP_URL = os.environ.get('FLASK_AP_DAILY_DUO_TEAM_UP_URL', f'{URL_BASE}/daily_duo_team_up')
FLASK_AP_DAILY_DUO_SEED_URL = os.environ.get('FLASK_AP_DAILY_DUO_SEED_URL', f'{URL_BASE}/daily_duo_seed')
FLASK_AP_DAILY_DUO_SEED_COMPLETE_URL = os.environ.get('FLASK_AP_DAILY_DUO_SEED_COMPLETE_URL', f'{URL_BASE}/daily_duo_seed_complete')
FLASK_AP_DAILY_DUO_LEADERBOARD_URL = os.environ.get('FLASK_AP_DAILY_DUO_LEADERBOARD_URL', f'{URL_BASE}/daily_duo_leaderboard')

JSON_HEADERS = {'Content-Type': 'application/json'}
ZIP_CONTENT_TYPES = ['application/zip', 'application/octet-stream']
TEMPORARY_MOD_FILE = "mod.zip"
DOWNLOAD_CHUNK_SIZE = 8192

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=discord_bot_settings.COMMAND_PREFIX, intents=intents)


def author_identity(context):
    return {'discord_id': context.author.id, 'discord_name': context.author.name}


def response_is_zip(response):
    content_type = response.headers.get('Content-Type', '')
    for zip_content_type in ZIP_CONTENT_TYPES:
        if zip_content_type in content_type:
            return True
    return False


async def post_json_and_reply(context, url, payload):
    try:
        response = requests.post(url, headers=JSON_HEADERS, data=json.dumps(payload))
        response.raise_for_status()
        response_data = response.json()
        await context.send(f"{response_data.get('message')}")
    except requests.exceptions.RequestException as error:
        await context.send(f"Error sending data to Flask app: {error}")
    except json.JSONDecodeError:
        await context.send("Error decoding JSON response from Flask app.")


async def send_downloaded_mod(context, response):
    try:
        with open(TEMPORARY_MOD_FILE, 'wb') as mod_file:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                mod_file.write(chunk)
        await context.send(file=discord.File(TEMPORARY_MOD_FILE))
    except Exception as error:
        await context.send(f"Error saving the downloaded file: {error}")
    finally:
        if os.path.exists(TEMPORARY_MOD_FILE):
            os.remove(TEMPORARY_MOD_FILE)


async def reply_with_mod_or_text(context, response, mod_message):
    if response_is_zip(response):
        await context.send(mod_message)
        await send_downloaded_mod(context, response)
    else:
        await context.send(f"Generation completed.\nResponse: {response.text}")


@bot.command(help="Stores data and a count in the Flask app's database.")
async def register(context):
    await post_json_and_reply(context, FLASK_REGISTER_URL, author_identity(context))


@bot.command(help="Generates a single player KH1 AP Randomizer game using the attached YAML")
async def generate(context):
    if not context.message.attachments:
        await context.send("Please attach a file to send.")
        return

    attachment = context.message.attachments[0]
    file_bytes = await attachment.read()
    files = {'file': (attachment.filename, file_bytes)}
    form_data = {'discord_id': context.author.id}

    try:
        async with context.typing():
            response = requests.post(FLASK_AP_GENERATE_URL, files=files, data=form_data, stream=True)
            response.raise_for_status()
            seed_link = response.headers.get('X-Seed-Link', 'No seed link found.')
            mod_message = f"Generation completed\nSeed link is: {seed_link}\nPlease find your mod attached..."
            await reply_with_mod_or_text(context, response, mod_message)
    except requests.exceptions.RequestException as error:
        await context.send(f"An error occurred while sending the file or receiving the response: {error}")
    except Exception as error:
        await context.send(f"An unexpected error occurred: {error}")


@bot.command(help="Returns a room for today's daily seed.  If the daily seed hasn't been generated today, it will generate one.")
async def daily_seed(context):
    payload = author_identity(context)
    try:
        async with context.typing():
            response = requests.post(FLASK_AP_DAILY_SEED_URL, headers=JSON_HEADERS, data=json.dumps(payload))
            response.raise_for_status()
            room_link = response.headers.get('X-Room-Link', 'No room link found.')
            mod_message = f"Daily seed fetch complete\nRoom link is: {room_link}\nPlease find your mod attached..."
            await reply_with_mod_or_text(context, response, mod_message)
    except requests.exceptions.RequestException as error:
        await context.send(f"An error occurred while sending the file or receiving the response: {error}")
    except Exception as error:
        await context.send(f"An unexpected error occurred: {error}")


@bot.command()
async def daily_seed_complete(context):
    payload = {'discord_id': context.author.id}
    await post_json_and_reply(context, FLASK_AP_DAILY_SEED_COMPLETE_URL, payload)


@bot.command()
async def daily_leaderboard(context):
    payload = {'discord_id': context.author.id}
    await post_json_and_reply(context, FLASK_AP_DAILY_LEADERBOARD_URL, payload)


@bot.command()
async def daily_duo_team_up(context):
    if not context.message.mentions:
        await context.send("You must ping another user to team up!")
        return

    mentioned_user = context.message.mentions[0]
    payload = {
        'author': author_identity(context),
        'mentioned': {'discord_id': mentioned_user.id, 'discord_name': mentioned_user.name},
    }
    await post_json_and_reply(context, FLASK_AP_DAILY_DUO_TEAM_UP_URL, payload)


@bot.command()
async def daily_duo_seed(context):
    payload = {'author': author_identity(context)}
    async with context.typing():
        await post_json_and_reply(context, FLASK_AP_DAILY_DUO_SEED_URL, payload)


@bot.command()
async def daily_duo_seed_complete(context):
    payload = {'discord_id': context.author.id}
    await post_json_and_reply(context, FLASK_AP_DAILY_DUO_SEED_COMPLETE_URL, payload)


@bot.command()
async def daily_duo_leaderboard(context):
    payload = {'discord_id': context.author.id}
    await post_json_and_reply(context, FLASK_AP_DAILY_DUO_LEADERBOARD_URL, payload)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')


@bot.event
async def on_message(message):
    message_is_from_this_bot = message.author == bot.user
    if message_is_from_this_bot:
        return
    await bot.process_commands(message)


bot.run(TOKEN)
