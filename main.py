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

class AdRequest(BaseModel):
    scenes: Union[list[SceneRequest], str]
    voice: str = "en-US-JennyNeural"

    @field_validator('scenes', mode='before')
    @classmethod
    def parse_scenes(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

@app.get("/")
def root():
    return {"status": "Ad Video Service is running!"}

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

            # Download image
            image_url = scene.image_url
            if not image_url:
                prompt = quote(f"cinematic advertisement {scene.text[:80]}")
                image_url = f"https://image.pollinations.ai/prompt/{prompt}?model=flux&width=1280&height=720&nologo=true"

            async with httpx.AsyncClient(timeout=60) as client:
                img_response = await client.get(image_url, follow_redirects=True)
                if img_response.status_code != 200:
                    raise HTTPException(status_code=400, detail=f"Image {i} download failed")
                with open(image_path, "wb") as f:
                    f.write(img_response.content)

            # Generate voice
            tts = edge_tts.Communicate(scene.text, req.voice)
            await tts.save(audio_path)

            # Get audio duration
            duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
            duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
            duration = float(duration_result.stdout.strip()) if duration_result.stdout.strip() else 3.0

            # Simple video — no heavy effects
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", image_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
                "-preset", "ultrafast",
                "-shortest",
                "-t", str(duration + 0.5),
                video_path
            ]

            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail=f"FFmpeg scene {i} error: {result.stderr[-300:]}")

            scene_videos.append(video_path)
            print(f"Scene {i} done!")

        # Merge all scenes
        final_video = f"{tmp_dir}/final_ad.mp4"
        concat_file = f"{tmp_dir}/concat.txt"

        with open(concat_file, "w") as f:
            for v in scene_videos:
                f.write(f"file '{v}'\n")

        merge_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", final_video]
        merge_result = subprocess.run(merge_cmd, capture_output=True, text=True, timeout=60)
        if merge_result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Merge error: {merge_result.stderr[-300:]}")

        print("Final ad video ready!")
        return FileResponse(final_video, media_type="video/mp4", filename="final_ad.mp4")

    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
