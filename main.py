import os
import uuid
import mimetypes
from abc import ABC, abstractmethod
from io import BytesIO
from functools import lru_cache

from flask import Flask, request, send_file, render_template_string, abort
from werkzeug.utils import secure_filename

# =============================
# Storage Interface
# =============================
class ObjectStorage(ABC):
    @abstractmethod
    def upload(self, key, file, content_type):
        pass

    @abstractmethod
    def download(self, key):
        pass


# =============================
# AWS S3
# =============================
class S3Storage(ObjectStorage):
    def __init__(self):
        import boto3
        self.bucket = os.getenv("S3_BUCKET_NAME")
        if not self.bucket:
            raise RuntimeError("Missing env var S3_BUCKET_NAME")
        region = os.getenv("AWS_DEFAULT_REGION", "eu-central-1")
        self.client = boto3.client("s3", region_name=region)

    def upload(self, key, file, content_type):
        self.client.upload_fileobj(
            file, self.bucket, key,
            ExtraArgs={"ContentType": content_type or "application/octet-stream"}
        )

    def download(self, key):
        buffer = BytesIO()
        self.client.download_fileobj(self.bucket, key, buffer)
        buffer.seek(0)
        return buffer


# =============================
# Azure Blob
# =============================
class AzureBlobStorage(ObjectStorage):
    def __init__(self):
        from azure.storage.blob import BlobServiceClient
        conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        container = os.getenv("AZURE_CONTAINER_NAME")
        if not conn:
            raise RuntimeError("Missing env var AZURE_STORAGE_CONNECTION_STRING")
        if not container:
            raise RuntimeError("Missing env var AZURE_CONTAINER_NAME")
        service = BlobServiceClient.from_connection_string(conn)
        self.container = service.get_container_client(container)

    def upload(self, key, file, content_type):
        from azure.storage.blob import ContentSettings
        blob = self.container.get_blob_client(key)
        blob.upload_blob(
            file,
            overwrite=True,
            content_settings=ContentSettings(
                content_type=content_type or "application/octet-stream"
            )
        )

    def download(self, key):
        blob = self.container.get_blob_client(key)
        stream = blob.download_blob()
        return BytesIO(stream.readall())


# =============================
# GCP Storage
# =============================
class GCSStorage(ObjectStorage):
    def __init__(self):
        from google.cloud import storage
        bucket_name = os.getenv("GCP_BUCKET_NAME")
        if not bucket_name:
            raise RuntimeError("Missing env var GCP_BUCKET_NAME")
        client = storage.Client()
        self.bucket = client.bucket(bucket_name)

    def upload(self, key, file, content_type):
        blob = self.bucket.blob(key)
        blob.upload_from_file(file, content_type=content_type or "application/octet-stream")

    def download(self, key):
        blob = self.bucket.blob(key)
        buffer = BytesIO()
        blob.download_to_file(buffer)
        buffer.seek(0)
        return buffer


# =============================
# Storage Factory
# =============================
def get_storage():
    provider = (os.getenv("STORAGE_PROVIDER") or "").strip().lower()
    if provider == "aws":
        return S3Storage()
    if provider == "azure":
        return AzureBlobStorage()
    if provider == "gcp":
        return GCSStorage()
    raise RuntimeError("Invalid STORAGE_PROVIDER. Use: aws | azure | gcp")


@lru_cache(maxsize=1)
def storage_client():
    return get_storage()


# =============================
# Flask App
# =============================
app = Flask(__name__)

ALLOWED = {"png", "jpg", "jpeg", "gif"}

def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


# =============================
# UI Page
# =============================
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Cloud Image Upload</title>

    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea, #764ba2);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
        }

        .card {
            background: white;
            width: 100%;
            max-width: 520px;
            border-radius: 14px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        }

        h2 {
            margin-top: 0;
            text-align: center;
            color: #333;
        }

        p.subtitle {
            text-align: center;
            color: #666;
            font-size: 14px;
            margin-bottom: 25px;
        }

        form {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        input[type="file"] {
            padding: 12px;
            border: 2px dashed #ccc;
            border-radius: 10px;
            cursor: pointer;
        }

        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px;
            border-radius: 10px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.2s ease, transform 0.1s ease;
        }

        button:hover {
            background: #5a67d8;
            transform: translateY(-1px);
        }

        .result {
            margin-top: 30px;
            text-align: center;
        }

        .result img {
            max-width: 100%;
            border-radius: 12px;
            margin-top: 15px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
        }

        .links {
            margin-top: 15px;
            display: flex;
            justify-content: center;
            gap: 20px;
        }

        .links a {
            text-decoration: none;
            color: #667eea;
            font-weight: 500;
        }

        .links a:hover {
            text-decoration: underline;
        }

        footer {
            margin-top: 25px;
            text-align: center;
            font-size: 12px;
            color: #aaa;
        }
    </style>
</head>

<body>
    <div class="card">
        <h2>Cloud Image Upload</h2>
        <p class="subtitle">
            Stored in <strong>AWS S3 / Azure Blob / GCP Storage</strong><br>
            Provider selected via environment variables
        </p>

        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="file" required>
            <button type="submit">Upload Image</button>
        </form>

        {% if image_id %}
        <div class="result">
            <h3>Upload Successful ☁️</h3>
            <img src="/images/{{ image_id }}">
            <div class="links">
                <a href="/images/{{ image_id }}">View</a>
                <a href="/download/{{ image_id }}">Download</a>
            </div>
        </div>
        {% endif %}

        <footer>
            Flask • Multi-Cloud Object Storage • AWS / Azure / GCP
        </footer>
    </div>
</body>
</html>
"""


# =============================
# Routes
# =============================
@app.route("/", methods=["GET", "POST"])
def index():
    image_id = None

    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename:
            filename = secure_filename(file.filename)
            if allowed(filename):
                ext = filename.rsplit(".", 1)[1].lower()
                image_id = f"{uuid.uuid4()}.{ext}"
                key = f"images/{image_id}"
                storage_client().upload(key, file, file.content_type)

    return render_template_string(HTML, image_id=image_id)


@app.route("/images/<image_id>")
def show_image(image_id):
    key = f"images/{image_id}"
    try:
        file = storage_client().download(key)
    except Exception:
        abort(404)

    mime = mimetypes.guess_type(image_id)[0] or "application/octet-stream"
    return send_file(file, mimetype=mime)


@app.route("/download/<image_id>")
def download_image(image_id):
    key = f"images/{image_id}"
    try:
        file = storage_client().download(key)
    except Exception:
        abort(404)

    mime = mimetypes.guess_type(image_id)[0] or "application/octet-stream"
    return send_file(file, mimetype=mime, download_name=image_id, as_attachment=True)

from flask import jsonify

# -----------------------------
# Helper for consistent JSON errors
# -----------------------------
def json_error(message, status=400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


# =============================
# Plain APIs for Load Testing
# =============================

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Plain upload endpoint for load testing.
    Request: multipart/form-data with field name 'file'
    Response: JSON with image_id and URLs
    """
    file = request.files.get("file")
    if not file or not file.filename:
        return json_error("Missing file in form-data. Use field name 'file'.", 400)

    filename = secure_filename(file.filename)
    if not allowed(filename):
        return json_error(
            "File type not allowed.",
            415,
            allowed_extensions=sorted(list(ALLOWED)),
        )

    ext = filename.rsplit(".", 1)[1].lower()
    image_id = f"{uuid.uuid4()}.{ext}"
    key = f"images/{image_id}"

    try:
        storage_client().upload(key, file, file.content_type)
    except Exception as e:
        return json_error("Upload failed.", 500, details=str(e))

    return jsonify({
        "image_id": image_id,
        "view_url": f"/api/images/{image_id}",
        "download_url": f"/api/download/{image_id}",
        "legacy_view_url": f"/images/{image_id}",
        "legacy_download_url": f"/download/{image_id}",
    }), 201


@app.route("/api/images/<image_id>", methods=["GET"])
def api_show_image(image_id):
    """
    Plain view endpoint for load testing (returns raw image bytes).
    """
    key = f"images/{image_id}"
    try:
        file = storage_client().download(key)
    except Exception:
        return json_error("Not found.", 404)

    mime = mimetypes.guess_type(image_id)[0] or "application/octet-stream"
    return send_file(file, mimetype=mime)


@app.route("/api/download/<image_id>", methods=["GET"])
def api_download_image(image_id):
    """
    Plain download endpoint for load testing (forces attachment download).
    """
    key = f"images/{image_id}"
    try:
        file = storage_client().download(key)
    except Exception:
        return json_error("Not found.", 404)

    mime = mimetypes.guess_type(image_id)[0] or "application/octet-stream"
    return send_file(file, mimetype=mime, download_name=image_id, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)