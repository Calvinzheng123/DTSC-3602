import os
import shlex
import subprocess
from pathlib import Path

import modal

# Paths to local files
streamlit_script_local_path = Path(__file__).parent / "streamlit_app.py"
articles_local_path = Path(__file__).parent / "articles_all.csv"
fraud_local_path = Path(__file__).parent / "fraud_articles.csv"

# Where they'll live inside container
streamlit_script_remote_path = "/root/streamlit_app.py"
articles_remote_path = "/root/articles_all.csv"
fraud_remote_path = "/root/fraud_articles.csv"

# Build the image: Python + all deps +  app files
image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install_from_requirements("requirements.txt")
    .add_local_file(streamlit_script_local_path, streamlit_script_remote_path)
    .add_local_file(articles_local_path, articles_remote_path)
    .add_local_file(fraud_local_path, fraud_remote_path)
)

app = modal.App(name="dtsc3602-streamlit", image=image)

@app.function(
    secrets=[modal.Secret.from_name("dtsc3602-env")]  
)
@modal.web_server(8000)
def run():
    # Work from /root so the CSVs are in the CWD
    os.chdir("/root")

    cmd = (
        f"streamlit run {shlex.quote(streamlit_script_remote_path)} "
        "--server.port 8000 "
        "--server.address 0.0.0.0 "
        "--server.enableCORS=false "
        "--server.enableXsrfProtection=false"
    )

    # Start Streamlit in the background; Modal keeps the container alive
    subprocess.Popen(cmd, shell=True)