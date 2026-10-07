#!/usr/bin/env python3
"""
image_toolkit.py — Simple image generation pipeline for Termux/Android.

Supports three backends:
  - Pollinations.ai (free, no API key or billing required — default)
  - Replicate (hosted Stable Diffusion / Flux models, requires billing)
  - OpenAI DALL-E 3 (requires billing)

Usage:
    python image_toolkit.py "your prompt here"                       # uses pollinations, free
    python image_toolkit.py "your prompt here" --backend replicate
    python image_toolkit.py "your prompt here" --backend dalle

Setup:
    pip install requests --break-system-packages  (Termux)

    Pollinations needs no setup at all. For the other backends, set an
    API key as an environment variable before running:
    export REPLICATE_API_TOKEN="r8_xxxxx"
    export OPENAI_API_KEY="sk-xxxxx"

    Add those export lines to ~/.bashrc to persist them across sessions.
"""

import os
import sys
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

OUTPUT_DIR = Path.home() / "generated_images"
OUTPUT_DIR.mkdir(exist_ok=True)


def generate_replicate(prompt: str, aspect_ratio: str = "2:3") -> str:
    """Generate an image using Replicate's hosted Flux model."""
    api_token = os.environ.get("REPLICATE_API_TOKEN")
    if not api_token:
        sys.exit("ERROR: Set REPLICATE_API_TOKEN environment variable first.")

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    # Using Flux Schnell - fast and cheap, good quality
    payload = {
        "input": {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "output_format": "png",
            "num_outputs": 1,
        }
    }

    print("Submitting job to Replicate (Flux)...")
    resp = requests.post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
        headers=headers,
        json=payload,
    )
    resp.raise_for_status()
    prediction = resp.json()
    get_url = prediction["urls"]["get"]

    # Poll until done
    while True:
        time.sleep(2)
        poll = requests.get(get_url, headers=headers).json()
        status = poll["status"]
        print(f"  status: {status}")
        if status == "succeeded":
            image_url = poll["output"][0] if isinstance(poll["output"], list) else poll["output"]
            return download_image(image_url, "replicate")
        elif status == "failed":
            sys.exit(f"Generation failed: {poll.get('error')}")


def generate_dalle(prompt: str, size: str = "1024x1792") -> str:
    """Generate an image using OpenAI's DALL-E 3."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("ERROR: Set OPENAI_API_KEY environment variable first.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": size,
        "quality": "standard",
        "n": 1,
    }

    print("Submitting job to DALL-E 3...")
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers=headers,
        json=payload,
    )
    resp.raise_for_status()
    image_url = resp.json()["data"][0]["url"]
    return download_image(image_url, "dalle")


def generate_pollinations(prompt: str, width: int = 1024, height: int = 1536) -> str:
    """Generate an image using Pollinations.ai — free, no API key or billing required."""
    encoded_prompt = quote(prompt)
    # 'seed' randomizes output; 'nologo' removes watermark; model=flux uses their Flux backend
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={width}&height={height}&nologo=true&model=flux&seed={int(time.time())}"
    )
    print("Requesting image from Pollinations.ai (this can take 10-30s)...")
    return download_image(url, "pollinations")


def download_image(url: str, backend: str) -> str:
    """Download generated image to local output directory, using the correct
    file extension based on the actual content type returned by the server."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    resp = requests.get(url)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "jpeg" in content_type or "jpg" in content_type:
        ext = "jpg"
    elif "webp" in content_type:
        ext = "webp"
    else:
        ext = "png"  # default/fallback

    filename = OUTPUT_DIR / f"{backend}_{timestamp}.{ext}"
    with open(filename, "wb") as f:
        f.write(resp.content)
    return str(filename)


def main():
    parser = argparse.ArgumentParser(description="Generate AI images from a text prompt.")
    parser.add_argument("prompt", help="The image generation prompt")
    parser.add_argument(
        "--backend",
        choices=["replicate", "dalle", "pollinations"],
        default="pollinations",
        help="Which API to use (default: pollinations, free/no billing required)",
    )
    args = parser.parse_args()

    if args.backend == "replicate":
        path = generate_replicate(args.prompt)
    elif args.backend == "dalle":
        path = generate_dalle(args.prompt)
    else:
        path = generate_pollinations(args.prompt)

    print(f"\nSaved image to: {path}")


if __name__ == "__main__":
    main()
