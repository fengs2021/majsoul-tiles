#!/usr/bin/env python3
"""
majsoul-tiles 悬浮窗服务器

启动本地 HTTP 服务，提供：
- Web 悬浮窗界面（绿色面板，适合 Android 分屏/悬浮窗）
- /api/analyze 接口：接收手牌，返回分析结果
- /api/screenshot 接口：上传截图，自动识别+分析

用法:
  python3 server.py                    # 默认 localhost:8899
  python3 server.py --port 8899        # 指定端口
  python3 server.py --watch-dir /sdcard/Pictures  # 监控截图目录
"""

import json
import sys
import os
import time
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import cv2

BASE_DIR = Path(__file__).parent
WEB_DIR = BASE_DIR / "web"
TEMPLATE_DIR = BASE_DIR / "templates"

# 延迟导入，避免服务启动时加载 OpenCV
from local_match import LocalMatcher
from akagi_bot import AkagiTilesBot, int_to_tile_name

# 全局 bot 实例
bot = AkagiTilesBot(backend="local")
matcher = LocalMatcher(TEMPLATE_DIR)


class OverlayHandler(SimpleHTTPRequestHandler):
    """自定义请求处理：静态文件 + API 路由"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def log_message(self, format, *args):
        # 精简日志
        if "/api/" in str(args):
            print(f"[api] {args[0]}")
        elif "200" in str(args[1]):
            pass  # 忽略静态文件请求
        else:
            print(f"[http] {args}")

    def do_GET(self):
        raw_path = self.path.split("?")[0] if "?" in self.path else self.path
        parsed = urlparse(self.path)

        # === API 路由 ===
        if raw_path == "/api/ping":
            self._json_response({"status": "ok", "templates": len(matcher.templates)})
            return

        # === 首页 ===
        if raw_path == "/" or raw_path == "/overlay":
            self.path = "/web/overlay.html"
            return super().do_GET()

        # === 静态文件 ===
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/screenshot":
            self._handle_screenshot()
            return

        if parsed.path == "/api/analyze":
            self._handle_analyze_post()
            return

        self._json_response({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ========== API 实现 ==========

    def _handle_analyze(self, parsed):
        """GET /api/analyze?hand=三万,五万,五万,..."""
        qs = parse_qs(parsed.query)
        hand_str = qs.get("hand", [""])[0]
        dora_str = qs.get("dora", [""])[0]

        if not hand_str:
            self._json_response({"error": "需要 hand 参数"}, 400)
            return

        labels = [l.strip() for l in hand_str.split(",") if l.strip()]
        dora_labels = [l.strip() for l in dora_str.split(",") if l.strip()] if dora_str else None

        result = bot.analyze(labels, dora_labels)
        self._json_response(result)

    def _handle_analyze_post(self):
        """POST /api/analyze  JSON body: {"hand": [...], "dora": [...]}"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        data = json.loads(body)

        labels = data.get("hand", [])
        dora_labels = data.get("dora", None)

        result = bot.analyze(labels, dora_labels)
        self._json_response(result)

    def _handle_screenshot(self):
        """POST /api/screenshot  接收截图 multipart 或 base64"""
        length = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            body = self.rfile.read(length)
            data = json.loads(body)
            # base64 图片
            import base64
            img_b64 = data.get("image", "")
            img_data = base64.b64decode(img_b64)
            img_path = "/tmp/majsoul_screenshot.png"
            with open(img_path, "wb") as f:
                f.write(img_data)
        else:
            # 原始二进制上传
            img_path = "/tmp/majsoul_screenshot.png"
            with open(img_path, "wb") as f:
                f.write(self.rfile.read(length))

        # 识别
        img = cv2.imread(img_path)
        if img is None:
            self._json_response({"error": "无法读取图片"}, 400)
            return

        results = matcher.match_hand(img)
        labels = [r["label"] for r in results if r["label"]]
        scores = {r["index"]: r["score"] for r in results}

        if len(labels) < 5:
            self._json_response({
                "error": f"识别到的牌太少 ({len(labels)}张)",
                "labels": labels,
                "raw_results": [{"label": r["label"], "score": r["score"], "index": r["index"]}
                                for r in results],
            })
            return

        result = bot.analyze(labels)
        result["recognized"] = labels
        result["scores"] = scores
        self._json_response(result)

    # ========== 工具方法 ==========

    def _json_response(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def start_server(port=8899):
    server = HTTPServer(("0.0.0.0", port), OverlayHandler)
    print(f"\n{'='*50}")
    print(f"  🀄 majsoul-tiles 悬浮窗服务")
    print(f"  📱 手机浏览器打开: http://localhost:{port}")
    print(f"  🖥️  PC 访问: http://<手机IP>:{port}")
    print(f"{'='*50}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n关闭服务...")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8899)
    args = parser.parse_args()
    start_server(args.port)
