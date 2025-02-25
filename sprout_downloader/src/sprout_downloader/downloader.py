import os
import re
import subprocess
import tempfile
import multiprocessing as mp
import m3u8
import requests
from Crypto.Cipher import AES

def saveSegment(queue, index, total):
    """Save a video segment."""
    segment = queue.get()
    filename = os.path.join(segment['temp_dir'], segment['filename'])
    
    response = requests.get(segment['url'])
    with open(filename, 'wb') as f:
        f.write(response.content)
    
    return filename

def download_video(video_data, selected_quality, progress=None):
    """Download video in selected quality."""
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
            if progress:
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
            if progress:
                progress(0.1, desc="Downloading segments...")
            with mp.Pool() as pool:
                ts_filenames = []
                for i, _ in enumerate(pool.starmap(saveSegment, [(queue, i, totalSegm) for i in range(totalSegm)])):
                    ts_filenames.append(_)
                    if progress:
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
            if progress:
                progress(0.8, desc="Merging segments...")
            with open(ts_name, 'wb') as merged:
                for ts_file in ts_filenames:
                    with open(ts_file, 'rb') as mergefile:
                        merged.write(cipher.decrypt(mergefile.read()))

            # Convert to MP4
            if progress:
                progress(0.9, desc="Converting to MP4...")
            p = subprocess.run(['ffmpeg', '-y', '-i', ts_name, '-map', '0', '-c', 'copy', mp4_name], capture_output=True)
            if p.returncode == 0:
                os.remove(ts_name)
                if progress:
                    progress(1.0, desc="Download complete!")
                return {"success": True, "file_path": mp4_name}
            else:
                if progress:
                    progress(1.0, desc="Download complete (TS format only)")
                return {"success": True, "file_path": ts_name, "message": "FFMpeg not found. File not converted to MP4!"}
    except Exception as e:
        return {"error": f"Error downloading video: {str(e)}"} 