from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Mapping

from infrastructure.tools.config import load_tool_configs

logger = logging.getLogger("infrastructure.tools.search")


class WebSearchPlugin:
    """防幻觉内嵌联网搜索工具"""

    def __init__(
        self,
        *,
        provider: str = "duckduckgo",
        api_base: str = "",
        api_key: str = "",
        max_results: int = 3,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.provider = provider
        self.api_base = api_base
        self.api_key = api_key
        self.max_results = max(1, min(int(max_results), 10))
        self.timeout_seconds = max(0.1, min(float(timeout_seconds), 30.0))
        # 默认的 Mock 检索库，以备网络不可用或无 API Key 时使用
        self._mock_database = {
            "elfie": "Elfie 仿生生命体是新一代智能宠物系统，采用三层大脑架构（顶层认知、中层生理情绪记忆、底层感知驱动）结合算力底座，具有生命涌现感。",
            "elfienest": "ElfieNest（精灵盒子）是 Elfie 仿生生命体的虚拟生态环境容器。它负责管理时间、重力、环境温度，并协调多个 Elfie 之间的物理相撞与社交。",
            "天气": "今日天气晴朗，气温 22°C - 26°C，微风，非常适宜 Elfie 小精灵去室外活动和补充能量。",
            "token": "ElfieNest 第一阶段只记录模型调用与工具调用观测事件，不做计费扣减或额度阻断。",
        }

    @classmethod
    def from_runtime_policy(
        cls, runtime_policy: Mapping[str, Any] | None
    ) -> WebSearchPlugin:
        config = load_tool_configs(runtime_policy)["web_search"]
        return cls(
            provider=str(config.get("provider") or "duckduckgo"),
            api_base=str(config.get("api_base") or ""),
            api_key=str(config.get("api_key") or ""),
            max_results=int(config.get("max_results") or 3),
            timeout_seconds=float(config.get("timeout_seconds") or 5.0),
        )

    def search(self, query: str, max_results: int | None = None) -> str:
        """
        执行联网搜索
        :param query: 搜索关键词
        :param max_results: 最大返回条数
        :return: 序列化为 Markdown 字符串的搜索结果
        """
        logger.info("正在使用 %s 进行网络检索: %r", self.provider, query)
        max_results = max_results or self.max_results

        # 尝试使用 DuckDuckGo Lite 进行真实联网抓取
        try:
            if self.provider == "brave":
                results = self._brave_search(query, max_results)
            elif self.provider == "tavily":
                results = self._tavily_search(query, max_results)
            else:
                results = self._real_ddg_search(query, max_results)
            if results:
                return self._format_results(results)
        except Exception as e:
            logger.error(f"真实联网检索失败: {e}")
            raise RuntimeError(
                f"【网络层异常】联网搜索检索失败 (可能无网络): {str(e)}"
            ) from e

        raise RuntimeError(f"【检索空状态】未找到关于 '{query}' 的有效网络检索结果")

    def _brave_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            raise RuntimeError("Brave Search 尚未配置 API Key")
        base = self.api_base or "https://api.search.brave.com/res/v1/web/search"
        url = f"{base}?q={urllib.parse.quote(query)}&count={max_results}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key,
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            {
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("description") or ""),
                "source": str(item.get("url") or "Brave"),
            }
            for item in payload.get("web", {}).get("results", [])[:max_results]
        ]

    def _tavily_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        if not self.api_key:
            raise RuntimeError("Tavily 尚未配置 API Key")
        base = self.api_base or "https://api.tavily.com/search"
        body = json.dumps(
            {"api_key": self.api_key, "query": query, "max_results": max_results}
        ).encode("utf-8")
        request = urllib.request.Request(
            base,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            {
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("content") or ""),
                "source": str(item.get("url") or "Tavily"),
            }
            for item in payload.get("results", [])[:max_results]
        ]

    def _real_ddg_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """调用 DuckDuckGo html 版本的真实搜索 (无 API Key 免费限制)"""
        # 注意：在受限沙箱中，真实网络抓取可能受阻，本段代码结构标准，失败会安全触发 exception
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
            html = response.read().decode("utf-8")

        # 使用极简规则从 HTML 中解析标题和 Snippet（避免引入 bs4 额外依赖）
        # 这里仅作底层真实联网流程演示，如果解析失败或超时会自动回退到本地
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.in_result = False
                self.in_snippet = False
                self.in_title = False
                self.temp_result: Dict[str, str] = {}
                self.results: List[Dict[str, str]] = []

            def handle_starttag(
                self, tag: str, attrs: List[tuple[str, str | None]]
            ) -> None:
                attrs_dict = dict(attrs)
                cls = attrs_dict.get("class") or ""
                if tag == "div" and "result__body" in cls:
                    self.in_result = True
                    self.temp_result = {}
                elif tag == "a" and "result__snippet" in cls:
                    self.in_snippet = True
                elif tag == "a" and "result__url" in cls:
                    self.in_title = True

            def handle_data(self, data: str) -> None:
                if self.in_title:
                    self.temp_result["title"] = (
                        self.temp_result.get("title", "") + data.strip()
                    )
                elif self.in_snippet:
                    self.temp_result["snippet"] = (
                        self.temp_result.get("snippet", "") + data.strip()
                    )

            def handle_endtag(self, tag: str) -> None:
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
        formatted: List[str] = []
        for i, res in enumerate(results, 1):
            formatted.append(
                f"[{i}] 标题: {res.get('title', '无标题')}\n"
                f"    来源: {res.get('source', '未知')}\n"
                f"    摘要: {res.get('snippet', '')}"
            )
        return "\n\n".join(formatted)
