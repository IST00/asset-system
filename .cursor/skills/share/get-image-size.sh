#!/usr/bin/env bash
# 获取远程图片的宽高，输出 JSON：{"width":750,"height":1334}
# 用法：bash get-image-size.sh <IMAGE_URL>
# 支持 PNG / JPEG / WebP / GIF / HEIC 等主流格式（依赖 macOS 内置 sips）

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "用法: $0 <IMAGE_URL>" >&2
  exit 1
fi

url="$1"
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

curl -sL "$url" -o "$tmp"

sips -g pixelWidth -g pixelHeight "$tmp" \
  | awk '/pixelWidth/{w=$2} /pixelHeight/{h=$2} END{print "{\"width\":"w",\"height\":"h"}"}'
