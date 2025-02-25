@echo off
echo Starting Sprout Video Downloader...
cd sprout_downloader
pixi install
pixi run python -m sprout_downloader
pause