#!/bin/bash
set -e

echo "=== Updating system ==="
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

echo "=== Cloning repository ==="
git clone https://github.com/Varshraghu98/flask-image-upload.git
cd flask-image-upload

echo "=== Creating virtual environment ==="
python3 -m venv venv
source venv/bin/activate

echo "=== Installing Python dependencies ==="
pip install --upgrade pip
python3 -m pip install Flask Werkzeug boto3 azure-storage-blob google-cloud-storage

echo "=== Setting application environment variables ==="
export STORAGE_PROVIDER=aws
export S3_BUCKET_NAME=aws-images-thesis
export AWS_DEFAULT_REGION=us-east-1



echo "Export aws s3 secret credentials manually to prevent git exposure"


