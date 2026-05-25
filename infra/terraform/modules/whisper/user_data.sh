#!/bin/bash
set -euo pipefail

# Install Docker and AWS CLI
apt-get update -q
apt-get install -y -q docker.io awscli curl

systemctl enable docker
systemctl start docker

# Create Docker volume for model cache (persists across container restarts)
docker volume create whisper_cache || true

# Write systemd unit
cat > /etc/systemd/system/whisper.service <<'UNIT'
[Unit]
Description=Whisper transcription service
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=30
ExecStartPre=/bin/bash -c 'aws ecr get-login-password --region ${aws_region} | docker login --username AWS --password-stdin ${ecr_repo_url}'
ExecStartPre=-/usr/bin/docker stop whisper
ExecStartPre=-/usr/bin/docker rm whisper
ExecStartPre=/usr/bin/docker pull ${ecr_repo_url}:latest
ExecStart=/usr/bin/docker run \
  --name whisper \
  --rm \
  -p 8080:8080 \
  -e WHISPER_MODEL=${whisper_model} \
  -e WHISPER_DEVICE=cpu \
  -e WHISPER_COMPUTE_TYPE=int8 \
  -v whisper_cache:/root/.cache/huggingface \
  ${ecr_repo_url}:latest
ExecStop=/usr/bin/docker stop whisper

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable whisper
# Image doesn't exist yet on first apply — start after CI pushes the image.
# Run: sudo systemctl start whisper
