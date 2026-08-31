import json
import os
from io import BytesIO
from flask import Blueprint, jsonify, render_template, send_from_directory, current_app, request, Response

app_update_bp = Blueprint("app_update", __name__)

VERSION_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "app_version.json")
DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "downloads")


def _load_version_config():
    try:
        with open(VERSION_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


@app_update_bp.route("/api/v1/app-version")
def get_app_version():
    config = _load_version_config()
    if not config:
        return jsonify({"success": False, "error": "config_not_found", "message": "Version configuration is missing."}), 404
    return jsonify({
        "success": True,
        "latest_version": config.get("latest_version", "0.0.0"),
        "version_code": config.get("version_code", 0),
        "apk_url": config.get("apk_url", ""),
        "release_notes": config.get("release_notes", ""),
        "force_update": config.get("force_update", False),
    })


@app_update_bp.route("/downloads")
def download_page():
    config = _load_version_config()
    if not config:
        return render_template("downloads.html", config=None, apk_files=[])

    apk_files = []
    if os.path.isdir(DOWNLOADS_DIR):
        apk_files = [f for f in os.listdir(DOWNLOADS_DIR) if f.endswith(".apk")]
    apk_files.sort(reverse=True)

    return render_template("downloads.html", config=config, apk_files=apk_files)


@app_update_bp.route("/downloads/qr")
def download_qr():
    import qrcode

    url = request.args.get("url")
    if not url:
        url = request.host_url.rstrip("/") + "/downloads"

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1f27", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app_update_bp.route("/downloads/<path:filename>")
def download_file(filename):
    if not os.path.isdir(DOWNLOADS_DIR):
        return jsonify({"success": False, "error": "not_found", "message": "Downloads directory not found."}), 404

    filepath = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({"success": False, "error": "not_found", "message": f"File '{filename}' not found."}), 404

    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True)
