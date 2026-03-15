from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts
import asyncio
import subprocess
import os
import uuid
import httpx
import traceback

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
        print(f"Downloading image from: {req.image_url}")
        async with httpx.AsyncClient(timeout=30) as client:
            img_response = await client.get(req.image_url, follow_redirects=True)
            print(f"Image response status: {img_response.status_code}")
            if img_response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Image download failed: {img_response.status_code}")
            with open(image_path, "wb") as f:
                f.write(img_response.content)
        print(f"Image saved to: {image_path}")

        # Step 2: Generate voice using Edge TTS
        print(f"Generating voice for script: {req.script[:50]}...")
        tts = edge_tts.Communicate(req.script, req.voice)
        await tts.save(audio_path)
        print(f"Audio saved to: {audio_path}")

        # Step 3: Generate video using FFmpeg
        print("Generating video with FFmpeg...")
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
        print(f"FFmpeg stderr: {result.stderr[-500:] if result.stderr else 'none'}")

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"FFmpeg error: {result.stderr[-500:]}")

        print("Video generated successfully!")
        return FileResponse(
            video_path,
            media_type="video/mp4",
            filename="ad_video.mp4"
        )

    except HTTPException:
        raise
    except Exception as e:
        error_detail = traceback.format_exc()
        print(f"Error: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))
