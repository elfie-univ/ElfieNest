import logging
import urllib.parse
import urllib.request
from typing import Dict, List

logger = logging.getLogger("runtime.plugins.web_search")


class WebSearchPlugin:
    """防幻觉内嵌联网搜索工具"""

    def __init__(self):
        # 默认的 Mock 检索库，以备网络不可用或无 API Key 时使用
        self._mock_database = {
            "elfie": "Elfie 仿生生命体是新一代智能宠物系统，采用三层大脑架构（顶层认知、中层生理情绪记忆、底层感知驱动）结合算力底座，具有生命涌现感。",
            "elfienest": "ElfieNest（精灵盒子）是 Elfie 仿生生命体的虚拟生态环境容器。它负责管理时间、重力、环境温度，并协调多个 Elfie 之间的物理相撞与社交。",
            "天气": "今日天气晴朗，气温 22°C - 26°C，微风，非常适宜 Elfie 小精灵去室外活动和补充能量。",
            "灵币": "灵币是 Elfie 算力底座的 Token 计费体系，深度推理任务需要消耗更多灵币，通过夜间休眠或完成主人任务可以恢复能量及灵币。",
        }

    def search(self, query: str, max_results: int = 3) -> str:
        """
        执行联网搜索
        :param query: 搜索关键词
        :param max_results: 最大返回条数
        :return: 序列化为 Markdown 字符串的搜索结果
        """
        logger.info(f"正在进行网络检索: '{query}'")

        # 尝试使用 DuckDuckGo Lite 进行真实联网抓取
        try:
            results = self._real_ddg_search(query, max_results)
            if results:
                return self._format_results(results)
        except Exception as e:
            logger.error(f"真实联网检索失败: {e}")
            raise RuntimeError(f"【网络层异常】联网搜索检索失败 (可能无网络): {str(e)}") from e

        raise RuntimeError(f"【检索空状态】未找到关于 '{query}' 的有效网络检索结果")

    def _real_ddg_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """调用 DuckDuckGo html 版本的真实搜索 (无 API Key 免费限制)"""
        # 注意：在受限沙箱中，真实网络抓取可能受阻，本段代码结构标准，失败会安全触发 exception
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode("utf-8")

        # 使用极简规则从 HTML 中解析标题和 Snippet（避免引入 bs4 额外依赖）
        # 这里仅作底层真实联网流程演示，如果解析失败或超时会自动回退到本地
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_result = False
                self.in_snippet = False
                self.in_title = False
                self.temp_result = {}
                self.results = []

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                cls = attrs_dict.get("class", "")
                if tag == "div" and "result__body" in cls:
                    self.in_result = True
                    self.temp_result = {}
                elif tag == "a" and "result__snippet" in cls:
                    self.in_snippet = True
                elif tag == "a" and "result__url" in cls:
                    self.in_title = True

            def handle_data(self, data):
                if self.in_title:
                    self.temp_result["title"] = (
                        self.temp_result.get("title", "") + data.strip()
                    )
                elif self.in_snippet:
                    self.temp_result["snippet"] = (
                        self.temp_result.get("snippet", "") + data.strip()
                    )

            def handle_endtag(self, tag):
                if tag == "a" and self.in_title:
                    self.in_title = False
                elif tag == "a" and self.in_snippet:
                    self.in_snippet = False
                elif tag == "div" and self.in_result:
                    self.in_result = False
                    if "snippet" in self.temp_result:
                        self.temp_result["source"] = "DuckDuckGo"
                        self.results.append(self.temp_result)

        parser = DDGParser()
        parser.feed(html)
        return parser.results[:max_results]

    def _format_results(self, results: List[Dict[str, str]]) -> str:
        formatted = []
        for i, res in enumerate(results, 1):
            formatted.append(
                f"[{i}] 标题: {res.get('title', '无标题')}\n"
                f"    来源: {res.get('source', '未知')}\n"
                f"    摘要: {res.get('snippet', '')}"
            )
        return "\n\n".join(formatted)
