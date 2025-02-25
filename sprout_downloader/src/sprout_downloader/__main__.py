from .ui import create_ui

def main():
    app = create_ui()
    app.launch(inbrowser=True)

if __name__ == "__main__":
    main() 