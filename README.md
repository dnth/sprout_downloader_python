# Sprout Video Downloader

## Pre-requisites

- Python 3.10+
- FFMpeg

## Installation

```bash
pip install -r requirements.txt
```

## Usage

> [!TIP]
> For Windows, you can use the `run_sprout.bat` file to launch the application. 

If you're not on Windows, you can launch the Gradio UI by running the following command:

```bash
python sprout_gradio.py
```

To use without the Gradio UI

```bash
python sprout.py
```

To use with Pixi, first install [pixi](https://pixi.sh/latest/#installation)

```bash
cd sprout_downloader
pixi install
```


Then 

```bash
pixi run python -m sprout_downloader
```

