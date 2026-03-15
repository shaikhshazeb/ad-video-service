from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
import edge_tts
import subprocess
import os
import uuid
import httpx
import traceback
import json
from typing import Optional, Union
from urllib.parse import quote

app = FastAPI()

class SceneRequest(BaseModel):
    scene: str
    text: str
    image_url: Optional[str] = None
    voice: str = "en-US-JennyNeural"

class AdRequest(BaseModel):
    scenes: Union[list[SceneRequest], str]
    voice: str = "en-US-JennyNeural"

    @field_validator('scenes', mode='before')
    @classmethod
    def parse_scenes(cls, v):
        if isinstance(v, str):
            parsed = json.loads(v)
            return parsed
        return v

@app.get("/")
def root():
    return {"status": "Ad Video Service is running!"}

@app.post("/generate-scene")
async def generate_scene(req: SceneRequest):
    job_id = str(uuid.uuid4())
    tmp_dir = f"/tmp/{job_id}"
    os.makedirs(tmp_dir, exist_ok=True)

    image_path = f"{tmp_dir}/image.jpg"
    audio_path = f"{tmp_dir}/voice.mp3"
    video_path = f"{tmp_dir}/scene.mp4"

    try:
        image_url = req.image_url
        if not image_url:
            prompt = f"cinematic advertisement {req.text[:100]}"
            image_url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?model=flux&width=1280&height=720&nologo=true"

        print(f"Downloading image from: {image_url}")
        async with httpx.AsyncClient(timeout=60) as client:
            img_response = await client.get(image_url, follow_redirects=True)
            if img_response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Image download failed: {img_response.status_code}")
            with open(image_path, "wb") as f:
                f.write(img_response.content)

        print(f"Generating voice...")
        tts = edge_tts.Communicate(req.text, req.voice)
        await tts.save(audio_path)

        duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        duration = float(duration_result.stdout.strip()) if duration_result.stdout.strip() else 5.0

        zoom_filter = f"scale=8000:-1,zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration*25)}:s=1280x720:fps=25,scale=1280:720"

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
            "-filter_complex", zoom_filter,
            "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-shortest", "-r", "25", video_path
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"FFmpeg error: {result.stderr[-500:]}")

        return FileResponse(video_path, media_type="video/mp4", filename=f"scene_{req.scene}.mp4")

    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-ad-video")
async def generate_ad_video(req: AdRequest):
    job_id = str(uuid.uuid4())
    tmp_dir = f"/tmp/{job_id}"
    os.makedirs(tmp_dir, exist_ok=True)
    scene_videos = []

    try:
        for i, scene in enumerate(req.scenes):
            image_path = f"{tmp_dir}/image_{i}.jpg"
            audio_path = f"{tmp_dir}/voice_{i}.mp3"
            video_path = f"{tmp_dir}/scene_{i}.mp4"

            image_url = scene.image_url
            if not image_url:
                prompt = f"cinematic advertisement {scene.text[:100]}"
                image_url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?model=flux&width=1280&height=720&nologo=true"

            async with httpx.AsyncClient(timeout=60) as client:
                img_response = await client.get(image_url, follow_redirects=True)
                if img_response.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Image {i} download failed")
                with open(image_path, "wb") as f:
                    f.write(img_response.content)

            tts = edge_tts.Communicate(scene.text, req.voice)
            await tts.save(audio_path)

            duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
            duration = float(duration_result.stdout.strip()) if duration_result.stdout.strip() else 3.0

            zoom_filter = f"scale=8000:-1,zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration*25)}:s=1280x720:fps=25,scale=1280:720"

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
                "-filter_complex", zoom_filter,
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-shortest", "-r", "25", video_path
            ]

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail=f"FFmpeg scene {i} error: {result.stderr[-300:]}")

            scene_videos.append(video_path)
            print(f"Scene {i} done!")

        final_video = f"{tmp_dir}/final_ad.mp4"
        concat_file = f"{tmp_dir}/concat.txt"

        with open(concat_file, "w") as f:
            for v in scene_videos:
                f.write(f"file '{v}'\n")

        merge_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", final_video]
        merge_result = subprocess.run(merge_cmd, capture_output=True, text=True, timeout=120)
        if merge_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Merge error: {merge_result.stderr[-300:]}")

        return FileResponse(final_video, media_type="video/mp4", filename="final_ad.mp4")

    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
