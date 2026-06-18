import discord_bot_settings_dev as dbs

import discord
from discord.ext import commands
import os
import requests
import json
from bs4 import BeautifulSoup
import random
import aiohttp

TOKEN = os.environ.get('DISCORD_BOT_TOKEN_DEV', dbs.DISCORD_BOT_TOKEN)

FLASK_REGISTER_URL = os.environ.get('FLASK_WRITE_URL', f'{dbs.URL_BASE}/register')
FLASK_AP_GENERATE_URL = os.environ.get('FLASK_AP_UPLOAD_URL', f'{dbs.URL_BASE}/generate')
FLASK_AP_DAILY_SEED_URL = os.environ.get('FLASK_AP_DAILY_SEED_URL', f'{dbs.URL_BASE}/daily_seed')
FLASK_AP_DAILY_SEED_COMPLETE_URL = os.environ.get('FLASK_AP_DAILY_SEED_COMPLETE_URL', f'{dbs.URL_BASE}/daily_seed_complete')
FLASK_AP_DAILY_LEADERBOARD_URL = os.environ.get('FLASK_AP_DAILY_LEADERBOARD_URL', f'{dbs.URL_BASE}/daily_leaderboard')
FLASK_AP_DAILY_DUO_TEAM_UP_URL = os.environ.get('FLASK_AP_DAILY_DUO_TEAM_UP_URL', f'{dbs.URL_BASE}/daily_duo_team_up')
FLASK_AP_DAILY_DUO_SEED_URL = os.environ.get('FLASK_AP_DAILY_DUO_SEED_URL', f'{dbs.URL_BASE}/daily_duo_seed')
FLASK_AP_DAILY_DUO_SEED_COMPLETE_URL = os.environ.get('FLASK_AP_DAILY_DUO_SEED_COMPLETE_URL', f'{dbs.URL_BASE}/daily_duo_seed_complete')
FLASK_AP_DAILY_DUO_LEADERBOARD_URL = os.environ.get('FLASK_AP_DAILY_DUO_LEADERBOARD_URL', f'{dbs.URL_BASE}/daily_duo_leaderboard')

intents = discord.Intents.default()
intents.message_content = True  # Enable if you need to read message content

# Initialize the bot with a command prefix
bot = commands.Bot(command_prefix=dbs.COMMAND_PREFIX, intents=intents)

@bot.command()
async def register(ctx):
    """Stores data and a count in the Flask app's database."""
    payload = {'discord_id': ctx.author.id, 'discord_name': ctx.author.name}
    headers = {'Content-Type': 'application/json'}  # Tell the server we're sending JSON

    try:
        response = requests.post(FLASK_REGISTER_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for bad status codes

        response_data = response.json()
        await ctx.send(f"{response_data.get('message')}")

    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error sending data to Flask app: {e}")
    except json.JSONDecodeError:
        await ctx.send("Error decoding JSON response from Flask app.")

@bot.command()
async def generate(ctx):
    """Generates a single player KH1 AP Randomizer game using the attached YAML"""
    if not ctx.message.attachments:
        await ctx.send("Please attach a file to send.")
        return

    data = {'discord_id': ctx.author.id}
    attachment = ctx.message.attachments[0]
    file_name = attachment.filename
    file_bytes = await attachment.read()  # Read the file content as bytes
    files = {'file': (file_name, file_bytes)}

    try:
        async with ctx.typing():  # Show "typing..." indicator
            response = requests.post(FLASK_AP_GENERATE_URL, files=files, data=data, stream=True)
            response.raise_for_status()
            
            seed_link = response.headers.get('X-Seed-Link', 'No seed link found.')

            # Check if the response indicates a file download
            if 'application/zip' in response.headers.get('Content-Type', '') or 'application/octet-stream' in response.headers.get('Content-Type', ''):
                await ctx.send(f"Generation completed\nSeed link is: {seed_link}\nPlease find your patch file attached...")
                temp_file_path = f"patch.kh1rpatch" # Create a temporary filename
                try:
                    with open(temp_file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    await ctx.send(file=discord.File(temp_file_path))
                except Exception as e:
                    await ctx.send(f"Error saving the downloaded file: {e}")
                finally:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
            else:
                # If the response is not a file, send the text content
                await ctx.send(f"Generation completed.\nResponse: {response.text}")

    except requests.exceptions.RequestException as e:
        await ctx.send(f"An error occurred while sending the file or receiving the response: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

@bot.command()
async def daily_seed(ctx):
    """Returns a room for today's daily seed.  If the daily seed hasn't been generated today, it will generate one."""
    payload = {'discord_id': ctx.author.id, 'discord_name': ctx.author.name}
    headers = {'Content-Type': 'application/json'}  # Tell the server we're sending JSON

    try:
        async with ctx.typing():  # Show "typing..." indicator
            response = requests.post(FLASK_AP_DAILY_SEED_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            
            room_link = response.headers.get('X-Room-Link', 'No room link found.')

            # Check if the response indicates a file download
            if 'application/zip' in response.headers.get('Content-Type', '') or 'application/octet-stream' in response.headers.get('Content-Type', ''):
                await ctx.send(f"Daily seed fetch complete\nRoom link is: {room_link}\nPlease find your patch file attached...")
                temp_file_path = "patch.kh1rpatch" # Create a temporary filename
                try:
                    with open(temp_file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    await ctx.send(file=discord.File(temp_file_path))
                except Exception as e:
                    await ctx.send(f"Error saving the downloaded file: {e}")
                finally:
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
            else:
                # If the response is not a file, send the text content
                await ctx.send(f"Generation completed.\nResponse: {response.text}")

    except requests.exceptions.RequestException as e:
        await ctx.send(f"An error occurred while sending the file or receiving the response: {e}")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

@bot.command()
async def daily_seed_complete(ctx):
    payload = {'discord_id': ctx.author.id}
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(FLASK_AP_DAILY_SEED_COMPLETE_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        response_data = response.json()
        await ctx.send(f"{response_data.get('message')}")
    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error sending data to Flask app: {e}")
    except json.JSONDecodeError:
        await ctx.send("Error decoding JSON response from Flask app.")

@bot.command()
async def daily_leaderboard(ctx):
    payload = {'discord_id': ctx.author.id}
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(FLASK_AP_DAILY_LEADERBOARD_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        response_data = response.json()
        await ctx.send(f"{response_data.get('message')}")
    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error sending data to Flask app: {e}")
    except json.JSONDecodeError:
        await ctx.send("Error decoding JSON response from Flask app.")

@bot.command()
async def daily_duo_team_up(ctx):
    # Require exactly one mentioned user
    if not ctx.message.mentions:
        await ctx.send("You must ping another user to team up!")
        return

    mentioned_user = ctx.message.mentions[0]

    # Prepare payload
    payload = {
        'author': {'discord_id': ctx.author.id, 'discord_name': ctx.author.name},
        'mentioned': {'discord_id': mentioned_user.id, 'discord_name': mentioned_user.name}
    }

    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(FLASK_AP_DAILY_DUO_TEAM_UP_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        response_data = response.json()
        await ctx.send(f"{response_data.get('message')}")
    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error sending data to Flask app: {e}")
    except json.JSONDecodeError:
        await ctx.send("Error decoding JSON response from Flask app.")

@bot.command()
async def daily_duo_seed(ctx):
    
    # Prepare payload
    payload = {
        'author': {'discord_id': ctx.author.id, 'discord_name': ctx.author.name},
    }

    headers = {'Content-Type': 'application/json'}

    try:
        async with ctx.typing():  # Show "typing..." indicator
            response = requests.post(FLASK_AP_DAILY_DUO_SEED_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            response_data = response.json()
            await ctx.send(f"{response_data.get('message')}")
    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error sending data to Flask app: {e}")
    except json.JSONDecodeError:
        await ctx.send("Error decoding JSON response from Flask app.")

@bot.command()
async def daily_duo_seed_complete(ctx):
    payload = {'discord_id': ctx.author.id}
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(FLASK_AP_DAILY_DUO_SEED_COMPLETE_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        response_data = response.json()
        await ctx.send(f"{response_data.get('message')}")
    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error sending data to Flask app: {e}")
    except json.JSONDecodeError:
        await ctx.send("Error decoding JSON response from Flask app.")

@bot.command()
async def daily_duo_leaderboard(ctx):
    payload = {'discord_id': ctx.author.id}
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(FLASK_AP_DAILY_DUO_LEADERBOARD_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        response_data = response.json()
        await ctx.send(f"{response_data.get('message')}")
    except requests.exceptions.RequestException as e:
        await ctx.send(f"Error sending data to Flask app: {e}")
    except json.JSONDecodeError:
        await ctx.send("Error decoding JSON response from Flask app.")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignore messages sent by the bot itself

    # You still need to process commands using bot.process_commands
    await bot.process_commands(message)

# Run the bot
bot.run(TOKEN)