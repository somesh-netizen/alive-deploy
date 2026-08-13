#!/usr/bin/env bash
# Build the bundle image and push it to a container registry.
# Usage: deploy/build_and_push.sh <registry>/<repo>:<tag>
set -euo pipefail
IMAGE="${1:?usage: build_and_push.sh <registry>/<repo>:<tag>}"
docker build -t "$IMAGE" .
docker push "$IMAGE"
echo "Pushed $IMAGE — set var image=\"$IMAGE\" in deploy/terraform/<cloud> and run terraform apply."
