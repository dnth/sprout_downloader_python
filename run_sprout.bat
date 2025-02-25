@echo off
echo Starting Sprout Video Downloader...
cd sprout_downloader
pixi install
pixi run python ../sprout_gradio.py
pause