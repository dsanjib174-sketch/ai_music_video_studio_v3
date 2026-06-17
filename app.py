import os
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
OUTPUT_DIR = BASE_DIR / "static" / "outputs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024

ALLOWED_AUDIO = {"mp3", "wav", "m4a", "aac"}
ALLOWED_IMAGE = {"jpg", "jpeg", "png", "webp"}

LOCATION_BACKGROUNDS = {
    "New York": (30, 35, 55),
    "Paris": (80, 55, 80),
    "Switzerland": (80, 115, 140),
    "Dubai": (150, 105, 50),
    "Venice": (65, 95, 120),
    "Maldives": (30, 135, 155),
    "Santorini": (80, 140, 180),
}


def ext_ok(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def make_frame(image_path, location, style, index, size=(1920, 1080)):
    w, h = size
    bg_color = LOCATION_BACKGROUNDS.get(location, (40, 45, 65))
    bg = Image.new("RGB", size, bg_color)

    # cinematic gradient overlay
    grad = Image.new("L", size, 0)
    gd = ImageDraw.Draw(grad)
    for y in range(h):
        val = int(255 * (y / h) * 0.65)
        gd.line([(0, y), (w, y)], fill=val)
    overlay = Image.new("RGB", size, (0, 0, 0))
    bg = Image.composite(overlay, bg, grad).filter(ImageFilter.GaussianBlur(1))

    img = Image.open(image_path).convert("RGB")
    img.thumbnail((int(w * 0.72), int(h * 0.74)))
    x = (w - img.width) // 2
    y = int(h * 0.14)

    # soft shadow
    shadow = Image.new("RGBA", (img.width + 70, img.height + 70), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((35, 35, img.width + 35, img.height + 35), radius=30, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24))
    bg.paste(shadow.convert("RGB"), (x - 35, y - 20), shadow)
    bg.paste(img, (x, y))

    draw = ImageDraw.Draw(bg)
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    except Exception:
        font_big = font_small = None

    title = f"{location}"
    subtitle = f"{style} Music Video Scene {index + 1}"
    draw.text((70, 60), title, fill=(255, 255, 255), font=font_big)
    draw.text((75, 135), subtitle, fill=(230, 230, 230), font=font_small)
    draw.text((70, h - 90), "AI Music Video Studio V3 | Real MP4 Preview", fill=(235, 235, 235), font=font_small)

    output_frame = UPLOAD_DIR / f"frame_{uuid.uuid4().hex}.jpg"
    bg.save(output_frame, quality=95)
    return str(output_frame)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    try:
        if "song" not in request.files:
            return jsonify({"ok": False, "error": "Please upload a song file."}), 400
        song = request.files["song"]
        photos = request.files.getlist("photos")
        if not song.filename or not ext_ok(song.filename, ALLOWED_AUDIO):
            return jsonify({"ok": False, "error": "Song must be MP3, WAV, M4A, or AAC."}), 400
        photos = [p for p in photos if p.filename and ext_ok(p.filename, ALLOWED_IMAGE)]
        if not photos:
            return jsonify({"ok": False, "error": "Please upload at least one photo."}), 400

        style = request.form.get("style", "Cinematic Romantic")
        quality = request.form.get("quality", "1080p")
        locations = request.form.getlist("locations") or ["New York", "Paris", "Switzerland", "Dubai"]
        resolution = (3840, 2160) if quality == "4K" else (1920, 1080)

        job_id = uuid.uuid4().hex[:10]
        song_name = secure_filename(song.filename)
        song_path = UPLOAD_DIR / f"{job_id}_{song_name}"
        song.save(song_path)

        photo_paths = []
        for i, photo in enumerate(photos):
            name = secure_filename(photo.filename)
            path = UPLOAD_DIR / f"{job_id}_{i}_{name}"
            photo.save(path)
            photo_paths.append(path)

        audio = AudioFileClip(str(song_path))
        duration = min(audio.duration, 300)  # max 5 minutes
        scene_count = max(6, min(36, int(duration // 8)))
        clip_duration = duration / scene_count

        clips = []
        for i in range(scene_count):
            photo_path = photo_paths[i % len(photo_paths)]
            location = locations[i % len(locations)]
            frame_path = make_frame(photo_path, location, style, i, resolution)
            clip = ImageClip(frame_path).set_duration(clip_duration)
            # Ken Burns effect
            clip = clip.resize(lambda t: 1 + 0.035 * (t / clip_duration)).set_position("center")
            clips.append(clip)

        final = concatenate_videoclips(clips, method="compose").set_audio(audio.subclip(0, duration))
        output_name = f"ai_music_video_v3_{job_id}.mp4"
        output_path = OUTPUT_DIR / output_name
        final.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", preset="medium", threads=4)
        audio.close()
        final.close()

        return jsonify({
            "ok": True,
            "video_url": f"/static/outputs/{output_name}",
            "download_url": f"/download/{output_name}",
            "duration": round(duration, 2),
            "scenes": scene_count,
            "quality": quality
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
