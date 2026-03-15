from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts
import asyncio
import subprocess
import os
import uuid
import httpx
import tempfile

app = FastAPI()

class AdRequest(BaseModel):
    image_url: str
    script: str
    voice: str = "en-US-JennyNeural"

@app.get("/")
def root():
    return {"status": "Ad Video Service is running!"}

@app.post("/generate-ad-video")
async def generate_ad_video(req: AdRequest):
    job_id = str(uuid.uuid4())
    tmp_dir = f"/tmp/{job_id}"
    os.makedirs(tmp_dir, exist_ok=True)

    image_path = f"{tmp_dir}/image.jpg"
    audio_path = f"{tmp_dir}/voice.mp3"
    video_path = f"{tmp_dir}/ad_video.mp4"

    try:
        # Step 1: Download image
        async with httpx.AsyncClient(timeout=30) as client:
            img_response = await client.get(req.image_url)
            if img_response.status_code != 200:
                raise HTTPException(status_code=400, detail="Image download failed")
            with open(image_path, "wb") as f:
                f.write(img_response.content)

        # Step 2: Generate voice using Edge TTS
        tts = edge_tts.Communicate(req.script, req.voice)
        await tts.save(audio_path)

        # Step 3: Generate video using FFmpeg
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
            video_path
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"FFmpeg error: {result.stderr}")

        return FileResponse(
            video_path,
            media_type="video/mp4",
            filename="ad_video.mp4"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
