from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp as youtube_dl
import os
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

app = FastAPI()

# Montar os arquivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configurar as credenciais do Spotify
client_credentials_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r") as f:
        return f.read()

@app.get("/convert")
async def convert_spotify_to_mp3(spotify_url: str):
    try:
        # Obter informações da faixa do Spotify
        track = sp.track(spotify_url)
        track_name = track['name']
        artist_name = track['artists'][0]['name']
        
        # Pesquisar no YouTube
        search_query = f"{track_name} {artist_name} audio"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '%(title)s.%(ext)s',
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{search_query}", download=True)['entries'][0]
            filename = f"{info['title']}.mp3"
        
        return FileResponse(filename, media_type='audio/mpeg', filename=filename)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)