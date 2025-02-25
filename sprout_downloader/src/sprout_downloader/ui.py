import gradio as gr
from .downloader import download_video
from .fetcher import fetch_video_data

def app_logic(url, password=None, selected_quality=None, state=None):
    """Main application logic for handling UI interactions."""
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
    """Create the Gradio UI interface."""
    with gr.Blocks(title="Sprout Video Downloader") as app:
        gr.Markdown("# Sprout Video Downloader")
        gr.Markdown("A simple tool to download Sprout videos. \n1. Paste the video URL, click Load Video. \n\t2. Select the quality you want to download. \n\t3. Click Download. \n\t4. The video will download to the downloads folder.")
        
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