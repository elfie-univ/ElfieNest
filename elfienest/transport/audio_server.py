import http.server
import logging
import os
import socketserver
import threading
from typing import Optional

logger = logging.getLogger("elfienest.transport.audio_server")


class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """压制大量 HTTP 静态请求日志的极简 RequestHandler"""

    def log_message(self, format, *args):
        # 保持控制台日志干练清爽，仅在 Debug 时记录 HTTP 请求
        logger.debug(f"[语音服务器] 请求: {format % args}")


class AudioServer:
    """封装 HTTP 静态音频分发服务器的启动/停止逻辑。

    在独立线程中运行 QuietHTTPRequestHandler，提供线程安全的 start/stop 接口。
    """

    def __init__(self, directory: str, port: int = 8000, host: str = "127.0.0.1"):
        self.directory = os.path.abspath(directory)
        self.port = port
        self.host = host
        self.httpd: Optional[socketserver.TCPServer] = None
        self._http_thread: Optional[threading.Thread] = None

    def start(self):
        """在独立线程中拉起极简语音静态分发服务器"""
        try:
            os.makedirs(self.directory, exist_ok=True)

            def handler(*args, **kwargs):
                return QuietHTTPRequestHandler(
                    *args, directory=self.directory, **kwargs
                )

            # 允许端口快速重用，避开 TIME_WAIT
            socketserver.TCPServer.allow_reuse_address = True
            self.httpd = socketserver.TCPServer(
                (self.host, self.port), handler
            )

            self._http_thread = threading.Thread(
                target=self.httpd.serve_forever,
                daemon=True,
                name="ElfieNest_HTTP_Thread",
            )
            self._http_thread.start()
            logger.info(
                f"🎵 [语音服务] 静态音频分发服务器已在 http://{self.host}:{self.port} 成功挂载！映射目录: {self.directory}"
            )
        except Exception as e:
            logger.error(f"❌ [语音服务] 启动 HTTP 服务失败，无法播放高品质语音: {e}")

    def stop(self):
        """停止 HTTP 服务器并清理套接字"""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
