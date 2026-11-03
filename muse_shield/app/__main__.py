"""python -m muse_shield.app  ->  http://127.0.0.1:8765"""

import os

import uvicorn

from .server import create_app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    print(f"Muse Shield: http://127.0.0.1:{port}")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
