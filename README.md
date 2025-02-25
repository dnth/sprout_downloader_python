# Sprout Video Downloader

## Pre-requisites

- Python 3.10+
- FFMpeg

## Installation

```bash
pip install -r requirements.txt
```

## Usage

To launch the Gradio UI, run the following command:

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
pixi run python ../sprout_gradio.py  
```

