import os
import sqlite3
import requests
import random
import discord
import io
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()

def init_db():
    conn = sqlite3.connect('gyazo_tokens.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS gyazo_tokens (
            user_id INTEGER PRIMARY KEY,
            access_token TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def get_access_token(user_id):
    conn = sqlite3.connect('gyazo_tokens.db')
    c = conn.cursor()
    c.execute('SELECT access_token FROM gyazo_tokens WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

@bot.tree.command(name='authenticate', description='Authenticate with Gyazo using your access token')
async def authenticate(interaction: discord.Interaction, access_token: str):
    try:
        access_token = access_token.strip()
        conn = sqlite3.connect('gyazo_tokens.db')
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO gyazo_tokens (user_id, access_token)
            VALUES (?, ?)
        ''', (interaction.user.id, access_token))
        conn.commit()
        conn.close()
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
        while True:
            response = requests.get(
                'https://api.gyazo.com/api/images',
                headers={'Authorization': f'Bearer {access_token}'},
                params={'page': page, 'per_page': per_page}
            )
            response.raise_for_status()
            page_images = response.json()
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
    except requests.exceptions.RequestException as e:
        print(f"Error fetching images: {str(e)}")
        await interaction.response.send_message(f'Error fetching images: {str(e)}', ephemeral=True)

@bot.tree.command(name='uploadphoto', description='Upload a photo to your Gyazo account')
async def uploadphoto(interaction: discord.Interaction, file: discord.Attachment):
    access_token = get_access_token(interaction.user.id)
    if not access_token:
        await interaction.response.send_message('Please authenticate first using the /authenticate command.', ephemeral=True)
        return
    try:
        image_data = await file.read()
        files = {
            'access_token': (None, access_token),
            'imagedata': (file.filename, image_data, file.content_type)
        }
        response = requests.post('https://upload.gyazo.com/api/upload', files=files)
        response.raise_for_status()
        data = response.json()
        permalink_url = data.get('permalink_url')
        await interaction.response.send_message(
            f'Image uploaded successfully!\nView it here: {permalink_url}',
            ephemeral=True
        )
    except requests.exceptions.RequestException as e:
        await interaction.response.send_message(f'Error uploading image: {e}', ephemeral=True)

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
        while True:
            response = requests.get(
                'https://api.gyazo.com/api/images',
                headers={'Authorization': f'Bearer {access_token}'},
                params={'page': page, 'per_page': per_page}
            )
            response.raise_for_status()
            page_images = response.json()
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
            attachments = []
            for image in requested_images:
                image_url = image.get('url')
                response = requests.get(image_url)
                if response.status_code == 200:
                    image_data = response.content
                    image_filename = f"gyazo_image_{image.get('id')}.png"
                    file = discord.File(io.BytesIO(image_data), filename=image_filename)
                    attachments.append(file)
            if attachments:
                await interaction.response.send_message(files=attachments, ephemeral=True)
            else:
                await interaction.response.send_message('There was an issue retrieving the images.', ephemeral=True)
    except requests.exceptions.RequestException as e:
        await interaction.response.send_message(f'Error fetching images: {e}', ephemeral=True)

bot.run(DISCORD_TOKEN)
