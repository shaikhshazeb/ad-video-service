# Ad Video Service

FastAPI service jo Edge TTS + FFmpeg se Ad Videos banata hai.

## Railway Deployment Steps:

1. Yeh repo GitHub pe upload karo
2. Railway pe jao → New Project → Deploy from GitHub
3. Yeh repo select karo
4. Railway automatically Dockerfile detect karega
5. Deploy hone ke baad URL milega jaise:
   `https://your-service.railway.app`

## n8n mein Use Kaise Karein:

HTTP Request node mein:
- Method: POST
- URL: `https://your-service.railway.app/generate-ad-video`
- Body (JSON):
```json
{
  "image_url": "{{$json.imageUrl}}",
  "script": "{{$json.text}}",
  "voice": "en-US-JennyNeural"
}
```
- Response Format: File

## Available Voices:
- `en-US-JennyNeural` — Female American
- `en-US-GuyNeural` — Male American
- `en-GB-SoniaNeural` — Female British
- `en-IN-NeerjaNeural` — Female Indian English
