import re, pickle, base64, json, sys, os, shutil, subprocess
import multiprocessing as mp
import tempfile
import time

import m3u8, requests, validators
from Crypto.Cipher import AES

import gradio as gr

def printError(error):
    return {"error": error}

def fetch_video_data(video_url, password=None):
    if not validators.url(video_url):
        return {"error": "Invalid URL"}

    session = requests.Session()
    data = session.get(video_url)
    
    # Handle password protected videos
    if data.status_code != 200 and re.search(r"Password Protected Video", data.text, re.I):
        if password is None:
            return {"need_password": True}
        
        token = re.search(r"name='authenticity_token' value='(.*?)'", data.text).group(1)
        data = session.post(video_url, data={'password': password, 'authenticity_token': token, '_method': 'put'})
        
        if data.status_code != 200:
            return {"error": "Wrong password"}
        else:
            data = requests.get(re.search(r'<meta\s*content="(.*?)"\s*name="twitter:player"\s*\/>', data.text).group(1)).text
    elif data.status_code != 200:
        return {"error": f"Can't get the link. Status code: {data.status_code}"}
    elif "sproutvideo.com" in video_url:
        data = data.text
    else:
        return {"error": "URL is not related to sproutvideos"}

    try:
        data_match = re.search(r"var dat = '(.*?)'", data)
        if not data_match:
            return {"error": "Could not find video data"}
            
        data = data_match.group(1)
        data = base64.b64decode(data).decode('utf8')
        data = json.loads(data)

        # Remove the double quotes in the title name
        title = data.get('title').replace('"', '')

        m3u8Param = data.get('signatures').get('m')
        keyParam = data.get('signatures').get('k')
        tsParam = data.get('signatures').get('t')

        def paramToSig(param):
            return "?Policy=" + param.get('CloudFront-Policy') + "&Signature=" + param.get('CloudFront-Signature') + "&Key-Pair-Id=" + param.get('CloudFront-Key-Pair-Id') + "&sessionID=" + data.get('sessionID')

        def sign(url):
            if url.endswith('m3u8'):
                return url + paramToSig(m3u8Param)
            elif url.endswith('key'):
                return url + paramToSig(keyParam)
            else:
                return url + paramToSig(tsParam)

        baseUrl = 'https://hls2.videos.sproutvideo.com/' + data.get('s3_user_hash') + '/' + data.get('s3_video_hash') + '/video/'

        m3u8_obj = m3u8.load(sign(baseUrl + 'index.m3u8'))
        playlists = []

        for i, playlist in enumerate(m3u8_obj.playlists):
            quality = playlist.uri.split('.')[0] + 'p'
            playlists.append({
                "index": i,
                "quality": quality,
                "uri": playlist.uri,
                "url": sign(baseUrl + playlist.uri)
            })

        # Get preview URL for the video
        preview_playlist = playlists[-1]  # Use highest quality for preview
        preview_url = sign(baseUrl + preview_playlist["uri"])
        
        # Create a direct preview URL that's more compatible with Gradio
        direct_preview_url = video_url if "embed" in video_url else video_url.replace("https://videos.sproutvideo.com/", "https://videos.sproutvideo.com/embed/")
        
        return {
            "title": title,
            "baseUrl": baseUrl,
            "playlists": playlists,
            "preview_url": preview_url,
            "direct_preview_url": direct_preview_url,
            "data": data,
            "m3u8Param": m3u8Param,
            "keyParam": keyParam,
            "tsParam": tsParam
        }
    except Exception as e:
        return {"error": f"Error processing video data: {str(e)}"}

def saveSegment(queue, currentSegm, total_segments):
    args = queue.get()
    with requests.get(args['url'], stream=True) as tsStream:
        with open(os.path.join(args['temp_dir'], args['filename']), "wb") as f:
            shutil.copyfileobj(tsStream.raw, f)
        return f.name

def download_video(video_data, selected_quality, progress=gr.Progress()):
    try:
        if "error" in video_data:
            return {"error": video_data["error"]}
            
        data = video_data["data"]
        title = video_data["title"]
        # Clean the title by removing special characters that are problematic for filenames
        clean_title = re.sub(r'[\\/*?:"<>|]', '', title)
        baseUrl = video_data["baseUrl"]
        playlists = video_data["playlists"]
        
        # Get the selected playlist
        selected_playlist = None
        for playlist in playlists:
            if playlist["quality"] == selected_quality:
                selected_playlist = playlist
                break
                
        if not selected_playlist:
            return {"error": "Selected quality not found"}
            
        def sign(url):
            if url.endswith('m3u8'):
                return url + paramToSig(video_data["m3u8Param"])
            elif url.endswith('key'):
                return url + paramToSig(video_data["keyParam"])
            else:
                return url + paramToSig(video_data["tsParam"])
                
        def paramToSig(param):
            return "?Policy=" + param.get('CloudFront-Policy') + "&Signature=" + param.get('CloudFront-Signature') + "&Key-Pair-Id=" + param.get('CloudFront-Key-Pair-Id') + "&sessionID=" + data.get('sessionID')
            
        play_link = baseUrl + selected_playlist["uri"]
        m3u8_obj = m3u8.load(sign(play_link))

        key_obj = m3u8_obj.keys[-1]
        keyURI = baseUrl + key_obj.uri
        iv = bytes.fromhex(key_obj.iv[2:])

        session = requests.Session()
        keyBytes = session.get(sign(keyURI)).content
        cipher = AES.new(keyBytes, AES.MODE_CBC, iv=iv)

        # Create temporary directory for segments
        with tempfile.TemporaryDirectory() as temp_dir:
            m = mp.Manager()
            queue = m.Queue()

            totalSegm = len(m3u8_obj.segments)
            progress(0, desc="Preparing download...")

            # Queue all segments for download
            for segment in m3u8_obj.segments:
                queue.put({
                    'url': sign(baseUrl + segment.uri), 
                    'filename': segment.uri, 
                    'temp_dir': temp_dir, 
                    'total': totalSegm
                })

            # Download segments
            progress(0.1, desc="Downloading segments...")
            with mp.Pool() as pool:
                ts_filenames = []
                for i, _ in enumerate(pool.starmap(saveSegment, [(queue, i, totalSegm) for i in range(totalSegm)])):
                    ts_filenames.append(_)
                    progress((i + 1) / totalSegm * 0.7 + 0.1, desc=f"Downloading segments: {i+1}/{totalSegm}")

            # Sort filenames
            ts_filenames.sort()
            
            # Create output directory if it doesn't exist
            output_dir = "downloads"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            ts_name = os.path.join(output_dir, f"{clean_title}.ts")
            mp4_name = os.path.join(output_dir, f"{clean_title}.mp4")

            # Merge and decrypt segments
            progress(0.8, desc="Merging segments...")
            with open(ts_name, 'wb') as merged:
                for ts_file in ts_filenames:
                    with open(ts_file, 'rb') as mergefile:
                        merged.write(cipher.decrypt(mergefile.read()))

            # Convert to MP4
            progress(0.9, desc="Converting to MP4...")
            p = subprocess.run(['ffmpeg', '-y', '-i', ts_name, '-map', '0', '-c', 'copy', mp4_name], capture_output=True)
            if p.returncode == 0:
                os.remove(ts_name)
                progress(1.0, desc="Download complete!")
                return {"success": True, "file_path": mp4_name}
            else:
                progress(1.0, desc="Download complete (TS format only)")
                return {"success": True, "file_path": ts_name, "message": "FFMpeg not found. File not converted to MP4!"}
    except Exception as e:
        return {"error": f"Error downloading video: {str(e)}"}

def app_logic(url, password=None, selected_quality=None, state=None):
    if state is None or "video_data" not in state:
        # First fetch the video data
        result = fetch_video_data(url, password)
        
        if "error" in result:
            return None, None, result["error"], None, {"message": result["error"]}
            
        if "need_password" in result and result["need_password"]:
            return None, None, "Password required", gr.update(visible=True), {"message": "Password required", "need_password": True}
            
        # Successfully fetched video data
        qualities = [p["quality"] for p in result["playlists"]]
        
        # Create an iframe HTML element to embed the video
        embed_url = result["direct_preview_url"]
        iframe_html = f'<iframe src="{embed_url}" width="100%" height="400" frameborder="0" allowfullscreen></iframe>'
        
        return iframe_html, gr.update(choices=qualities, value=qualities[-1], visible=True), "", gr.update(visible=False), {"video_data": result, "message": "Video loaded successfully"}
    
    # If we already have video data and a quality is selected, download the video
    if selected_quality:
        download_result = download_video(state["video_data"], selected_quality)
        
        if "error" in download_result:
            return None, None, download_result["error"], None, state
            
        if "success" in download_result and download_result["success"]:
            file_path = download_result["file_path"]
            message = f"Video downloaded successfully to {file_path}"
            if "message" in download_result:
                message += f". {download_result['message']}"
                
            return None, None, message, None, {"message": message, "file_path": file_path}
    
    return None, None, "Please select a quality", None, state

def create_ui():
    with gr.Blocks(title="Sprout Video Downloader") as app:
        gr.Markdown("# Sprout Video Downloader")
        
        with gr.Row():
            url_input = gr.Textbox(label="Video URL", placeholder="Enter Sprout Video URL")
            password_input = gr.Textbox(label="Password (if required)", visible=False)
        
        with gr.Row():
            submit_btn = gr.Button("Load Video")
        
        with gr.Row():
            video_preview = gr.HTML(label="Video Preview")
        
        with gr.Row():
            quality_dropdown = gr.Dropdown(label="Select Quality", choices=[], visible=False)
            download_btn = gr.Button("Download", visible=False)
        
        status_text = gr.Textbox(label="Status", interactive=False)
        
        state = gr.State({})
        
        # Event handlers
        submit_btn.click(
            fn=app_logic,
            inputs=[url_input, password_input, quality_dropdown, state],
            outputs=[video_preview, quality_dropdown, status_text, password_input, state]
        )
        
        quality_dropdown.change(
            fn=lambda x: gr.update(visible=True),
            inputs=[quality_dropdown],
            outputs=[download_btn]
        )
        
        download_btn.click(
            fn=app_logic,
            inputs=[url_input, password_input, quality_dropdown, state],
            outputs=[video_preview, quality_dropdown, status_text, password_input, state]
        )
        
    return app

if __name__ == "__main__":
    app = create_ui()
    app.launch() 