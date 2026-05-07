#!/usr/bin/env python3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
import os
import posixpath


APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parent


class IMUReplayHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = unquote(path.split("?", 1)[0].split("#", 1)[0])
        normalized = posixpath.normpath(path)
        parts = [part for part in normalized.split("/") if part and part != ".."]

        if parts and parts[0] == "temp_data":
            base = REPO_ROOT
        else:
            base = APP_ROOT

        resolved = base
        for part in parts:
            resolved = resolved / part
        return str(resolved)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    port = int(os.environ.get("IMU_REPLAY_PORT", "8090"))
    server = ThreadingHTTPServer(("0.0.0.0", port), IMUReplayHandler)
    print(f"Starting IMU Replay Lab on port {port}...")
    print(f"Open http://localhost:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
