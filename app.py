from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import uuid
import threading

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

downloads = {}


@app.route("/")
def home():
    return render_template("index.html")


# =========================
# VIDEO INFORMATION
# =========================

@app.route("/video-info", methods=["POST"])
def video_info():

    url = request.form.get("url", "").strip()

    if not url:
        return jsonify({
            "error": "Please enter a YouTube URL."
        }), 400

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

        return jsonify({
            "title": info.get("title", "Unknown title"),
            "thumbnail": info.get("thumbnail", ""),
            "uploader": info.get("uploader", ""),
            "duration": info.get("duration", 0),
            "views": info.get("view_count", 0)
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 400


# =========================
# DOWNLOAD
# =========================

def download_media(
    task_id,
    url,
    media_format,
    quality
):

    try:

        downloads[task_id] = {
            "status": "downloading",
            "progress": 0,
            "speed": "Starting...",
            "filename": None,
            "error": None
        }

        # =========================
        # MP3
        # =========================

        if media_format == "mp3":

            bitrate = quality

            output_template = os.path.join(
                DOWNLOAD_FOLDER,
                task_id + ".%(ext)s"
            )

            format_selector = "bestaudio/best"

            ydl_opts = {

                "format": format_selector,

                "outtmpl": output_template,

                "noplaylist": True,

                "progress_hooks": [],

                "postprocessors": [
                    {
                        "key":
                            "FFmpegExtractAudio",

                        "preferredcodec":
                            "mp3",

                        "preferredquality":
                            bitrate
                    }
                ]
            }

        # =========================
        # MP4 / WEBM
        # =========================

        else:

            if quality == "best":
                height_filter = ""
            else:
                height_filter = f"[height<={quality}]"


            if media_format == "mp4":

                format_selector = (
                    f"bestvideo"
                    f"{height_filter}"
                    f"[ext=mp4]"
                    f"+bestaudio[ext=m4a]"
                    f"/best"
                    f"{height_filter}"
                    f"[ext=mp4]"
                    f"/best"
                    f"{height_filter}"
                )

            else:

                format_selector = (
                    f"bestvideo"
                    f"{height_filter}"
                    f"[ext=webm]"
                    f"+bestaudio[ext=webm]"
                    f"/best"
                    f"{height_filter}"
                    f"[ext=webm]"
                    f"/best"
                    f"{height_filter}"
                )


            output_template = os.path.join(
                DOWNLOAD_FOLDER,
                task_id + ".%(ext)s"
            )

            ydl_opts = {

                "format": format_selector,

                "outtmpl": output_template,

                "noplaylist": True,

                "merge_output_format":
                    media_format
            }


        # =========================
        # PROGRESS HOOK
        # =========================

        def progress_hook(data):

            if data["status"] == "downloading":

                downloaded = data.get(
                    "downloaded_bytes",
                    0
                )

                total = (
                    data.get("total_bytes")
                    or
                    data.get(
                        "total_bytes_estimate",
                        0
                    )
                )

                if total:
                    percentage = (
                        downloaded / total
                    ) * 100
                else:
                    percentage = 0


                speed = data.get("speed")

                if speed:

                    speed_mb = (
                        speed /
                        1024 /
                        1024
                    )

                    speed_text = (
                        f"{speed_mb:.2f} MB/s"
                    )

                else:

                    speed_text = "Calculating..."


                downloads[task_id]["progress"] = round(
                    percentage,
                    1
                )

                downloads[task_id]["speed"] = speed_text


            elif data["status"] == "finished":

                downloads[task_id]["progress"] = 100

                downloads[task_id]["status"] = "processing"


        ydl_opts["progress_hooks"] = [
            progress_hook
        ]


        # =========================
        # DOWNLOAD
        # =========================

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            original_file = ydl.prepare_filename(
                info
            )


        # =========================
        # FIND RESULT
        # =========================

        if media_format == "mp3":

            base_name = os.path.splitext(
                original_file
            )[0]

            final_file = (
                base_name +
                ".mp3"
            )

        else:

            base_name = os.path.splitext(
                original_file
            )[0]

            final_file = (
                base_name +
                "." +
                media_format
            )


        if not os.path.exists(final_file):

            matching_files = [

                os.path.join(
                    DOWNLOAD_FOLDER,
                    filename
                )

                for filename in os.listdir(
                    DOWNLOAD_FOLDER
                )

                if filename.startswith(task_id)
            ]


            if matching_files:

                final_file = matching_files[0]

            else:

                raise FileNotFoundError(
                    "Downloaded file could not be found."
                )


        downloads[task_id]["status"] = "complete"

        downloads[task_id]["progress"] = 100

        downloads[task_id]["filename"] = final_file


    except Exception as e:

        downloads[task_id]["status"] = "error"

        downloads[task_id]["error"] = str(e)


# =========================
# START DOWNLOAD
# =========================

@app.route(
    "/start-download",
    methods=["POST"]
)
def start_download():

    url = request.form.get(
        "url",
        ""
    ).strip()

    media_format = request.form.get(
        "format",
        "mp4"
    )

    quality = request.form.get(
        "quality",
        "best"
    )


    if not url:

        return jsonify({
            "error":
                "Please enter a YouTube URL."
        }), 400


    if media_format not in [
        "mp4",
        "webm",
        "mp3"
    ]:

        media_format = "mp4"


    if media_format == "mp3":

        if quality not in [
            "128",
            "192",
            "256",
            "320"
        ]:

            quality = "192"

    else:

        if quality not in [
            "360",
            "480",
            "720",
            "1080",
            "best"
        ]:

            quality = "best"


    task_id = str(
        uuid.uuid4()
    )


    thread = threading.Thread(

        target=download_media,

        args=(
            task_id,
            url,
            media_format,
            quality
        )
    )

    thread.daemon = True

    thread.start()


    return jsonify({
        "task_id": task_id
    })


# =========================
# PROGRESS
# =========================

@app.route(
    "/progress/<task_id>"
)
def progress(task_id):

    if task_id not in downloads:

        return jsonify({
            "status": "error",
            "error": "Download task not found."
        }), 404


    return jsonify(
        downloads[task_id]
    )


# =========================
# DOWNLOAD FILE
# =========================

@app.route(
    "/file/<task_id>"
)
def download_file(task_id):

    if task_id not in downloads:

        return "Download not found.", 404


    task = downloads[task_id]


    if task["status"] != "complete":

        return "Download is not ready.", 400


    file_path = task["filename"]


    if (
        not file_path
        or
        not os.path.exists(file_path)
    ):

        return "File not found.", 404


    return send_file(

        file_path,

        as_attachment=True,

        download_name=os.path.basename(
            file_path
        )
    )


# =========================
# RUN
# =========================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )