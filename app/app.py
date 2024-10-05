import os
import tempfile
import asyncio
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp as youtube_dl
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# Configuração do Spotify
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

client_credentials_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# Configuração do youtube-dl
FFMPEG_PATH = os.getenv('FFMPEG_PATH')
TEMP_DIR = tempfile.gettempdir()

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'ffmpeg_location': FFMPEG_PATH,
    'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
}

# Dicionário para armazenar o progresso das conversões
conversion_progress = {}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("static/index.html")

@app.get("/progress")
async def get_progress(url: str = Query(..., description="URL do Spotify")):
    progress = conversion_progress.get(url, {"progress": 0, "status": "Iniciando..."})
    return JSONResponse(progress)

@app.get("/convert")
async def convert_spotify_to_mp3(background_tasks: BackgroundTasks, url: str = Query(..., description="URL do Spotify")):
    filename = None
    try:
        conversion_progress[url] = {"progress": 0, "status": "Buscando informações da música..."}
        
        track = sp.track(url)
        artist = track['artists'][0]['name']
        song_name = track['name']
        search_query = f"{artist} - {song_name}"
        
        conversion_progress[url] = {"progress": 20, "status": "Procurando vídeo correspondente..."}
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            try:
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        progress = int(float(d['downloaded_bytes']) / float(d['total_bytes']) * 60) + 20
                        conversion_progress[url] = {"progress": progress, "status": "Baixando áudio..."}
                        logger.debug(f"Download progress: {progress}%")
                    elif d['status'] == 'finished':
                        conversion_progress[url] = {"progress": 80, "status": "Convertendo para MP3..."}
                        logger.debug("Download finished, starting conversion")

                ydl_opts['progress_hooks'] = [progress_hook]
                logger.debug(f"Searching for: {search_query}")
                info = ydl.extract_info(f"ytsearch:{search_query}", download=True)['entries'][0]
                filename = os.path.join(TEMP_DIR, f"{info['title']}.mp3")
                logger.debug(f"File downloaded: {filename}")
            except Exception as e:
                logger.error(f"Error during YouTube download: {str(e)}")
                raise HTTPException(status_code=500, detail={
                    "message": f"Erro ao baixar o áudio do YouTube: {str(e)}",
                    "spotify_info": {
                        "track": song_name,
                        "artist": artist,
                        "url": url
                    }
                })

        # Verificar se o arquivo foi realmente criado
        if not os.path.exists(filename):
            logger.error(f"MP3 file not created: {filename}")
            raise HTTPException(status_code=500, detail="O arquivo MP3 não foi criado corretamente")

        logger.debug(f"Conversion completed: {filename}")
        conversion_progress[url] = {"progress": 100, "status": "Conversão concluída!"}
        background_tasks.add_task(delayed_file_removal, filename, delay=120)
        return FileResponse(filename, media_type='audio/mpeg', filename=os.path.basename(filename))
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {str(e)}")
    finally:
        if url in conversion_progress:
            del conversion_progress[url]

async def delayed_file_removal(file_path, delay):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Arquivo temporário removido: {file_path}")
        else:
            print(f"Arquivo temporário não encontrado: {file_path}")
    except Exception as e:
        print(f"Erro ao remover o arquivo temporário: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)