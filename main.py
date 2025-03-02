import os
import sqlite3
import aiohttp
import random
import discord
import io
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

def init_db():
    with sqlite3.connect('gyazo_tokens.db') as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS gyazo_tokens (
                user_id INTEGER PRIMARY KEY,
                access_token TEXT NOT NULL
            )
        ''')
        conn.commit()

def get_access_token(user_id):
    with sqlite3.connect('gyazo_tokens.db') as conn:
        c = conn.cursor()
        c.execute('SELECT access_token FROM gyazo_tokens WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        return result[0] if result else None

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()

@bot.tree.command(name='authenticate', description='Authenticate with Gyazo using your access token')
async def authenticate(interaction: discord.Interaction, access_token: str):
    try:
        access_token = access_token.strip()
        with sqlite3.connect('gyazo_tokens.db') as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO gyazo_tokens (user_id, access_token)
                VALUES (?, ?)
            ''', (interaction.user.id, access_token))
            conn.commit()
        await interaction.response.send_message('Authentication successful.', ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f'Error: {e}', ephemeral=True)

@bot.tree.command(name='randomphoto', description='Get a random photo from your Gyazo account')
async def randomphoto(interaction: discord.Interaction):
    access_token = get_access_token(interaction.user.id)
    if not access_token:
        await interaction.response.send_message('Please authenticate first using the /authenticate command.', ephemeral=True)
        return
    try:
        images = []
        page = 1
        per_page = 100
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(
                    'https://api.gyazo.com/api/images',
                    headers={'Authorization': f'Bearer {access_token}'},
                    params={'page': page, 'per_page': per_page}
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"HTTP error {response.status}: {text}")
                    page_images = await response.json()
                    if not page_images:
                        break
                    images.extend(page_images)
                    page += 1
        if images:
            random_image = random.choice(images)
            image_url = random_image.get('url')
            await interaction.response.send_message(f'Random image: {image_url}', ephemeral=True)
        else:
            await interaction.response.send_message('No images found in your Gyazo account.', ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f'Error fetching images: {e}', ephemeral=True)

@bot.tree.command(name='uploadphoto', description='Upload a photo to your Gyazo account')
async def uploadphoto(interaction: discord.Interaction, file: discord.Attachment):
    access_token = get_access_token(interaction.user.id)
    if not access_token:
        await interaction.response.send_message('Please authenticate first using the /authenticate command.', ephemeral=True)
        return
    try:
        image_data = await file.read()
        data = aiohttp.FormData()
        data.add_field('access_token', access_token)
        data.add_field('imagedata', image_data, filename=file.filename, content_type=file.content_type)
        async with aiohttp.ClientSession() as session:
            async with session.post('https://upload.gyazo.com/api/upload', data=data) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"HTTP error {response.status}: {text}")
                resp_json = await response.json()
        permalink_url = resp_json.get('permalink_url')
        await interaction.response.send_message(
            f'Image uploaded successfully!\nView it here: {permalink_url}',
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f'Error uploading image: {e}', ephemeral=True)

async def download_image(session, url, image_id):
    async with session.get(url) as response:
        if response.status != 200:
            raise Exception(f"Error downloading image {image_id}: HTTP {response.status}")
        image_data = await response.read()
        image_filename = f"gyazo_image_{image_id}.png"
        return (image_data, image_filename)

@bot.tree.command(name='lastimage', description='Get the last image(s) uploaded to Gyazo')
async def lastimage(interaction: discord.Interaction, number: int = 1):
    if number < 1 or number > 10:
        await interaction.response.send_message('Please request between 1 and 10 images.', ephemeral=True)
        return
    access_token = get_access_token(interaction.user.id)
    if not access_token:
        await interaction.response.send_message('Please authenticate first using the /authenticate command.', ephemeral=True)
        return
    try:
        images = []
        page = 1
        per_page = 100
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(
                    'https://api.gyazo.com/api/images',
                    headers={'Authorization': f'Bearer {access_token}'},
                    params={'page': page, 'per_page': per_page}
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"HTTP error {response.status}: {text}")
                    page_images = await response.json()
                    if not page_images:
                        break
                    images.extend(page_images)
                    page += 1
        if not images:
            await interaction.response.send_message('No images found in your Gyazo account.', ephemeral=True)
            return
        requested_images = images[-number:]
        if number == 1:
            image = requested_images[0]
            embed = discord.Embed(title="Gyazo Image", description="Image from your Gyazo account", color=discord.Color.blue())
            embed.set_image(url=image.get('url'))
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            async with aiohttp.ClientSession() as session:
                tasks = []
                for image in requested_images:
                    image_url = image.get('url')
                    tasks.append(download_image(session, image_url, image.get('id')))
                downloaded_images = await asyncio.gather(*tasks, return_exceptions=True)
            attachments = []
            for result in downloaded_images:
                if isinstance(result, tuple):
                    image_data, image_filename = result
                    file_obj = discord.File(io.BytesIO(image_data), filename=image_filename)
                    attachments.append(file_obj)
            if attachments:
                await interaction.response.send_message(files=attachments, ephemeral=True)
            else:
                await interaction.response.send_message('There was an issue retrieving the images.', ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f'Error fetching images: {e}', ephemeral=True)

if __name__ == "__main__":
    init_db()
    bot.run(DISCORD_TOKEN)
