import re
import base64
import json
import requests
import validators
import m3u8

def fetch_video_data(video_url, password=None):
    """Fetch video data from Sprout Video URL."""
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