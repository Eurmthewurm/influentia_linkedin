#!/usr/bin/env python3
"""Render demo.html to MP4 by capturing frames at exact time positions."""

import asyncio
import os
import subprocess
import shutil
import time

from playwright.async_api import async_playwright

HTML_PATH = "/Users/ermoegberts/Desktop/linkedin_outreach/landing/demo.html"
OUT_DIR = "/Users/ermoegberts/Desktop/linkedin_outreach/landing/demo_frames"
OUTPUT = "/Users/ermoegberts/Desktop/linkedin_outreach/landing/demo.mp4"
FPS = 30
DURATION = 32  # seconds

async def main():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    total_frames = FPS * DURATION
    print(f"Rendering {total_frames} frames at {FPS}fps ({DURATION}s)...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})

        await page.goto(f"file://{HTML_PATH}", wait_until="networkidle")
        await asyncio.sleep(0.3)

        t0 = time.time()
        for i in range(total_frames):
            t = i / FPS
            # Set the demo time and render
            await page.evaluate(f"window.demoTime = {t}; render({t});")
            # Small wait for rendering
            await asyncio.sleep(0.01)

            frame_path = os.path.join(OUT_DIR, f"frame_{i:05d}.png")
            await page.screenshot(path=frame_path)

            if i % 30 == 0:
                elapsed = time.time() - t0
                fps_actual = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"  Frame {i:>5}/{total_frames}  t={t:>5.1f}s  ({fps_actual:.1f} fps)")

        await browser.close()

    elapsed = time.time() - t0
    print(f"\nCapture done in {elapsed:.1f}s")

    # Compile to MP4
    print(f"Compiling video...")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(OUT_DIR, "frame_%05d.png"),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        OUTPUT
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr[-800:]}")
        return

    size_mb = os.path.getsize(OUTPUT) / (1024 * 1024)
    print(f"Done! {OUTPUT} ({size_mb:.1f} MB)")

    # Cleanup frames
    shutil.rmtree(OUT_DIR)
    print("Cleaned up frames.")

asyncio.run(main())
