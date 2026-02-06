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
<html>
<head>
    <title>Cloud Image Upload</title>
    <style>
        body { font-family: sans-serif; max-width: 600px; margin: auto; }
        img { max-width: 100%; margin-top: 20px; }
    </style>
</head>
<body>
<h2>Upload Image</h2>

<form method="POST" enctype="multipart/form-data">
    <input type="file" name="file" required>
    <button type="submit">Upload</button>
</form>

{% if image_id %}
    <h3>Uploaded Image</h3>
    <img src="/images/{{ image_id }}">
    <br><br>
    <a href="/download/{{ image_id }}">Download image</a>
{% endif %}
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)