import os
import tempfile
import asyncio
import time
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
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

def download_audio(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
        'keepvideo': False,  # Remover o arquivo de vídeo original após conversão
    }

    if FFMPEG_PATH:
        os.environ['PATH'] = FFMPEG_PATH + os.pathsep + os.environ['PATH']
    
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Dicionário para armazenar o progresso das conversões
conversion_progress = {}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    logger.debug("Serving index.html")
    with open("static/index.html", "r") as file:
        content = file.read()
    return HTMLResponse(content=content)

@app.get("/progress")
async def get_progress(url: str = Query(..., description="URL do link de qualquer plataforma")):
    progress = conversion_progress.get(url, {"progress": 0, "status": "Iniciando..."})
    return JSONResponse(progress)

@app.get("/convert")
async def convert_link_to_mp3(background_tasks: BackgroundTasks, url: str = Query(..., description="URL de qualquer plataforma")):
    filename = None
    try:
        logger.debug(f"Iniciando conversão para a URL: {url}")
        conversion_progress[url] = {"progress": 0, "status": "Identificando plataforma..."}

        platform = identify_platform(url)
        logger.debug(f"Plataforma identificada: {platform}")

        # Definindo ydl_opts dentro da função
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'keepvideo': False,  # Remover o arquivo de vídeo original após conversão
        }

        if FFMPEG_PATH:
            os.environ['PATH'] = FFMPEG_PATH + os.pathsep + os.environ['PATH']

        if platform == "spotify":
            # Lógica existente para Spotify
            track = sp.track(url)
            artist = track['artists'][0]['name']
            song_name = track['name']
            search_query = f"{artist} - {song_name}"

            conversion_progress[url] = {"progress": 20, "status": "Procurando vídeo correspondente..."}

            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(f"ytsearch:{search_query}", download=True)['entries'][0]
                    logger.debug(f"Info retornada: {info}")  # Log do retorno do info
                    filename = os.path.join(TEMP_DIR, f"{info['title']}.mp3")  # Defina o filename aqui
                    logger.debug(f"File path definido: {filename}")  # Log do filename
                    logger.debug(f"File downloaded: {filename}")

                    # Aguardar um pouco para garantir que a conversão seja concluída
                    time.sleep(2)

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

        elif platform == "youtube":
            logger.debug("Iniciando download...")
            conversion_progress[url] = {"progress": 20, "status": "Baixando vídeo..."}
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                try:
                    logger.debug(f"Opções do ydl: {ydl_opts}")
                    info = ydl.extract_info(url, download=True)  # Use a URL diretamente
                    logger.debug(f"Info retornada: {info}")  # Log do retorno do info
                    filename = os.path.join(TEMP_DIR, f"{info['title']}.mp3")  # Defina o filename aqui
                    logger.debug(f"File path definido: {filename}")  # Log do filename
                    logger.debug(f"File downloaded: {filename}")

                    # Aguardar um pouco para garantir que a conversão seja concluída
                    time.sleep(2)

                except Exception as e:
                    logger.error(f"Error during YouTube download: {str(e)}")
                    raise HTTPException(status_code=500, detail={
                        "message": f"Erro ao baixar o áudio do YouTube: {str(e)}",
                        "url": url
                    })

        else:
            raise HTTPException(status_code=400, detail="Plataforma não suportada")

        # Verificar se o arquivo foi realmente criado
        if filename is None or not os.path.exists(filename):
            logger.error(f"MP3 file not created: {filename}")
            raise HTTPException(status_code=500, detail="O arquivo MP3 não foi criado corretamente")

        logger.debug(f"Conversão concluída: {filename}")
        conversion_progress[url] = {"progress": 100, "status": "Conversão concluida!"}
        background_tasks.add_task(delayed_file_removal, filename, delay=120)
        return FileResponse(filename, media_type='audio/mpeg', filename=os.path.basename(filename))

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail={"message": f"Erro inesperado: {str(e)}"})
    finally:
        if url in conversion_progress:
            del conversion_progress[url]

@app.get("/spotify.html", response_class=HTMLResponse)
async def spotify_page():
    logger.debug("Serving spotify.html")
    with open("static/spotify.html", "r") as file:
        content = file.read()
    return HTMLResponse(content=content)

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

def identify_platform(url):
    # Simplificação: vamos tratar todos os links diretamente
    if "spotify.com" in url:
        return "spotify"
    elif "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    # Adicione mais verificações conforme necessário
    return "generic"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
