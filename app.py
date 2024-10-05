import os
import re
import asyncio
import tempfile
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp as youtube_dl
from pydantic import BaseModel, HttpUrl, field_validator
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

TEMP_DIR = tempfile.mkdtemp(prefix="spotify_converter_")
print(f"Diretório temporário criado: {TEMP_DIR}")

app.mount("/static", StaticFiles(directory="static"), name="static")

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise ValueError("As credenciais do Spotify não estão configuradas corretamente.")

client_credentials_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f:
        return f.read()

@app.get("/convert")
async def convert_spotify_to_mp3(background_tasks: BackgroundTasks, url: str = Query(..., description="URL do Spotify")):
    filename = None
    try:
        spotify_pattern = r'^https?://open\.spotify\.com/(track|album|playlist)/[a-zA-Z0-9]+(\?si=[a-zA-Z0-9]+)?$'
        if not re.match(spotify_pattern, url):
            raise ValueError('URL inválida do Spotify')

        track = sp.track(url)
        track_name = track['name']
        artist_name = track['artists'][0]['name']
        
        search_query = f"{track_name} {artist_name} audio"
        
        ffmpeg_path = os.getenv('FFMPEG_PATH', 'ffmpeg')
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'ffmpeg_location': ffmpeg_path,
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch:{search_query}", download=True)['entries'][0]
                filename = os.path.join(TEMP_DIR, f"{info['title']}.mp3")
            except Exception as e:
                raise HTTPException(status_code=404, detail={
                    "message": "Música não encontrada",
                    "spotify_info": {
                        "track": track_name,
                        "artist": artist_name,
                        "url": url
                    }
                })

        background_tasks.add_task(delayed_file_removal, filename, delay=120)
        return FileResponse(filename, media_type='audio/mpeg', filename=os.path.basename(filename))
    
    except spotipy.exceptions.SpotifyException as e:
        raise HTTPException(status_code=400, detail="URL do Spotify inválida")
    except Exception as e:
        if filename and os.path.exists(filename):
            os.remove(filename)
        raise HTTPException(status_code=500, detail=str(e))

async def delayed_file_removal(filename: str, delay: int):
    await asyncio.sleep(delay)
    if os.path.exists(filename):
        os.remove(filename)

async def cleanup_temp_files():
    while True:
        now = datetime.now()
        for filename in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, filename)
            if now - datetime.fromtimestamp(os.path.getmtime(file_path)) > timedelta(minutes=10):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
        await asyncio.sleep(600)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_temp_files())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)