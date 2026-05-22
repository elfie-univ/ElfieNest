# -*- coding: utf-8 -*-

import os
import json
import base64
import mimetypes
import urllib.request
import urllib.error
import logging
from typing import Dict, Any, List

from runtime.config import LLMRuntimeConfig
from runtime.model_registry import ModelRegistry
from runtime.ollama_manager import OllamaManager, OllamaNotReadyError
from runtime.permission_manager import PermissionManager, PermissionDeniedError
from runtime.plugins.web_search import WebSearchPlugin
from runtime.plugins.code_sandbox import CodeSandboxPlugin
from runtime.plugins.skills_evolution import SkillsSelfEvolutionPlugin
from runtime.model_router import ModelRouter

logger = logging.getLogger("runtime.agent")

class UnsupportedModalError(Exception):
    """当模型不支持所传入的多模态媒介（图片/声音）时抛出的异常"""
    pass

class RuntimeAgent:
    """外包算力工厂底层 Agent - 拥有三轨自演化技能与原生多模态 Payload 组装能力"""

    def __init__(self, config: LLMRuntimeConfig = None):
        self.config = config or LLMRuntimeConfig()
        
        # 1. 注册核心设施
        self.registry = ModelRegistry(self.config)
        self.ollama_manager = OllamaManager(self.config)
        self.permission_manager = PermissionManager(self.config)
        
        # 2. 挂载能力插件
        self.search_plugin = WebSearchPlugin()
        self.sandbox_plugin = CodeSandboxPlugin()
        self.skills_evolution_plugin = SkillsSelfEvolutionPlugin(self.permission_manager)
        
        # 3. 智能路由模块挂载
        self.router = ModelRouter(self.config)

    def ask(
        self,
        prompt: str,
        energy: float = 100.0,
        task_complexity: int = 1,
        allowed_skills: List[str] = None
    ) -> str:
        """
        向后兼容旧的脑皮层 ask 接口，内部自动调度 ModelRouter 进行智能模型与算力路由
        """
        # 1. 智能路由评估
        mode, decision = self.router.route_request(prompt, energy, task_complexity)
        
        # 2. 映射对应的算力 Model Key
        if mode == "local":
            model_key = "local_fast"
        else:
            model_key = "remote_deep"
            
        logger.info(f"🔮 [智能算力分配] 路由模式为 '{mode}'，最终分发至 model_key: '{model_key}'")
        
        # 3. 组装单轮单用户消息 payload
        messages = [{"role": "user", "content": prompt}]
        
        # 默认注入并放行三轨核心能力
        if allowed_skills is None:
            allowed_skills = ["web_search", "code_sandbox", "skills_evolution"]
            
        # 4. 调用高弹性 generate 接口，限制最长自进化/防幻觉多轮迭代上限为 3 次
        return self.generate(
            model_key=model_key,
            messages=messages,
            allowed_skills=allowed_skills,
            max_loops=3
        )

    def generate(
        self,
        model_key: str,
        messages: List[Dict[str, str]],
        images: List[str] = None,
        audio: str = None,
        temperature: float = None,
        max_tokens: int = None,
        allowed_skills: List[str] = None,
        max_loops: int = 1,
        admin_token: str = None
    ) -> str:
        """
        高度可控的多模态大模型 generate 接口
        :param model_key: 算力套餐中的 Model Key (如 "local_fast", "remote_deep")
        :param messages: 完整的对话上下文历史
        :param images: 待处理图片本地绝对路径列表
        :param audio: 待处理音频本地绝对路径
        :param temperature: 随机温度 (不传使用 config 默认值)
        :param max_tokens: 最大Token限制
        :param allowed_skills: 允许调用的技能列表 (如 ["web_search", "code_sandbox", "skills_evolution"])
        :param max_loops: 多轮推理循环迭代上限
        :param admin_token: 特权令牌，用于 N3 重构时代谢技能
        :return: 大模型最终的纯文本响应
        """
        # 1. 校验模型激活状态与多模态兼容性
        model_info = self.registry.get_model_info(model_key)
        if not model_info["active"]:
            raise ValueError(f"❌ 目标模型 Key '{model_key}' 未激活，请核对云端 API Key 或本地配置。")
            
        model_name = model_info["name"]
        provider = model_info["provider"]
        
        # 检查多模态支持
        if images and not model_info["is_vision"]:
            raise UnsupportedModalError(f"❌ 模型 '{model_name}' 不支持处理视觉(图片)多模态输入！")
        if audio and not model_info["is_audio"]:
            raise UnsupportedModalError(f"❌ 模型 '{model_name}' 不支持原生处理音频(语音)多模态输入！")

        # 2. 运行期快速拉起保障 (如果是本地模型)
        if provider == "ollama":
            self.ollama_manager.ensure_service_started()

        # 拷贝 messages 避免外部入参篡改
        local_messages = [dict(m) for m in messages]

        # 3. 拼装多模态媒体载荷至最新的一条 User Message
        if images or audio:
            local_messages = self._assemble_multimodal_payload(
                local_messages, images, audio, provider
            )

        # 4. 根据允许的技能，动态向上下文顶部(或者 System )注入防幻觉指令规约
        if allowed_skills:
            local_messages = self._inject_skills_system_prompt(local_messages, allowed_skills)

        # 5. 推理/自进化循环拦截
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens if max_tokens is not None else self.config.max_tokens

        for loop_idx in range(max_loops):
            logger.info(f"⚡ 大模型底座交互循环 #{loop_idx + 1}/{max_loops} (Model: {model_name})...")
            
            # 发起 API 调用 (出现连接、认证等错误将直接爆裂抛出，不进行 Mock 兜底)
            response_text = self._call_llm_api(provider, model_name, local_messages, temp, tokens)
            
            has_action = False
            
            # 联合匹配拦截三轨语法
            
            # (A) 联网搜索拦截与回调
            if "web_search" in (allowed_skills or []) and "[SEARCH]" in response_text and "[/SEARCH]" in response_text:
                has_action = True
                query = response_text.split("[SEARCH]")[1].split("[/SEARCH]")[0].strip()
                
                # 联网搜索
                search_res = self.search_plugin.search(query)
                
                local_messages.append({"role": "assistant", "content": response_text})
                local_messages.append({
                    "role": "user", 
                    "content": f"【联网搜索反馈】\n结合以下最新网络检索事实数据，修正并生成最终回答，去掉 [SEARCH] 标签：\n{search_res}"
                })
                logger.info("已成功回调联网检索数据。")
                
            # (B) 代码沙箱拦截与回调
            elif "code_sandbox" in (allowed_skills or []) and "[CODE]" in response_text and "[/CODE]" in response_text:
                has_action = True
                code = response_text.split("[CODE]")[1].split("[/CODE]")[0].strip()
                
                # 执行沙箱前，权限审计自动过
                self.permission_manager.verify_action("RUN_SKILL", file_path="code_sandbox")
                
                exec_res = self.sandbox_plugin.execute(code)
                
                sandbox_feedback = (
                    f"【Python 沙箱执行反馈】\n"
                    f"标准输出: {exec_res['stdout']}\n"
                    f"请基于上述代码计算的精确物理结果，修改并生成你最终、可信的完整回答，去掉 [CODE] 标签。"
                )
                local_messages.append({"role": "assistant", "content": response_text})
                local_messages.append({"role": "user", "content": sandbox_feedback})
                logger.info("已成功回调沙箱算术运算结果。")
                
            # (C) 技能自进化沉淀拦截与回调 (WRITE_SKILL)
            elif "skills_evolution" in (allowed_skills or []) and "[WRITE_SKILL]" in response_text and "[/WRITE_SKILL]" in response_text:
                has_action = True
                raw_block = response_text.split("[WRITE_SKILL]")[1].split("[/WRITE_SKILL]")[0].strip()
                # 解析 name|code 结构
                if "|" in raw_block:
                    skill_name, skill_code = raw_block.split("|", 1)
                    skill_name = skill_name.strip()
                    skill_code = skill_code.strip()
                    
                    write_feedback = self.skills_evolution_plugin.write_skill(skill_name, skill_code, admin_token)
                else:
                    write_feedback = "❌ 语法解析错误：[WRITE_SKILL] 格式必须是 [WRITE_SKILL]文件名|Python代码[/WRITE_SKILL]"
                    
                local_messages.append({"role": "assistant", "content": response_text})
                local_messages.append({"role": "user", "content": write_feedback})
                logger.info("已完成技能沉淀拦截与回调。")
                
            # (D) 技能自进化重用拦截与回调 (RUN_SKILL)
            elif "skills_evolution" in (allowed_skills or []) and "[RUN_SKILL]" in response_text and "[/RUN_SKILL]" in response_text:
                has_action = True
                raw_block = response_text.split("[RUN_SKILL]")[1].split("[/RUN_SKILL]")[0].strip()
                if "|" in raw_block:
                    skill_name, skill_args = raw_block.split("|", 1)
                    skill_name = skill_name.strip()
                    skill_args = skill_args.strip()
                else:
                    skill_name = raw_block.strip()
                    skill_args = ""
                    
                run_res = self.skills_evolution_plugin.run_skill(skill_name, skill_args)
                
                if run_res["exit_code"] == 0:
                    run_feedback = (
                        f"【习得技能 '{skill_name}' 运行成功】\n"
                        f"标准输出 (stdout): {run_res['stdout']}\n"
                        f"请根据此结果重新生成你最终的文本回复，去掉 [RUN_SKILL] 标签。"
                    )
                else:
                    run_feedback = (
                        f"【习得技能 '{skill_name}' 运行故障】\n"
                        f"错误流 (stderr): {run_res['stderr']}\n"
                        f"请根据此错误日志进行反思并重新回答。"
                    )
                    
                local_messages.append({"role": "assistant", "content": response_text})
                local_messages.append({"role": "user", "content": run_feedback})
                logger.info("已完成技能运行拦截与回调。")

            # (E) 列出所有技能拦截与回调 (LIST_SKILLS)
            elif "skills_evolution" in (allowed_skills or []) and "[LIST_SKILLS]" in response_text and "[/LIST_SKILLS]" in response_text:
                has_action = True
                list_feedback = self.skills_evolution_plugin.list_skills()
                local_messages.append({"role": "assistant", "content": response_text})
                local_messages.append({"role": "user", "content": list_feedback})
                logger.info("已完成技能库检索与回调。")

            # 若无拦截，直接跳出推理环返回结果
            if not has_action:
                return response_text

        # 超过 max_loops 仍未收敛
        raise TimeoutError("❌ 算力底座在防幻觉与自进化迭代循环中超出了迭代轮数上限，请精简您的 Prompt 语境。")

    def _assemble_multimodal_payload(
        self,
        messages: List[Dict[str, str]],
        images: List[str] = None,
        audio: str = None,
        provider: str = "ollama"
    ) -> List[Dict[str, str]]:
        """拼装多模态媒体载荷 (Base64 转码与格式适配)"""
        # 获取最新的一条 User Message
        user_msg_idx = -1
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx]["role"] == "user":
                user_msg_idx = idx
                break
                
        if user_msg_idx == -1:
            # 极罕见状态：没有 user message 时强制追加一条
            messages.append({"role": "user", "content": ""})
            user_msg_idx = len(messages) - 1
            
        original_text = messages[user_msg_idx]["content"]
        
        # 1. 本地 Ollama 视觉格式拼装
        if provider == "ollama":
            # Ollama API 仅在 "/api/chat" 级别接收 "images" 的 Base64 列表
            images_base64 = []
            if images:
                for img_path in images:
                    if not os.path.exists(img_path):
                        raise FileNotFoundError(f"❌ 找不到图片文件: '{img_path}'")
                    with open(img_path, "rb") as f:
                        images_base64.append(base64.b64encode(f.read()).decode("utf-8"))
                # 直接挂载到最新 user 消息的 extra 字段里，供 Ollama 接口调用解析
                messages[user_msg_idx]["images"] = images_base64
            return messages
            
        # 2. 云端 (OpenAI/Gemini/DeepSeek 兼容) 多模态消息体拼装
        else:
            content_list = [{"type": "text", "text": original_text}]
            
            # 拼装图片
            if images:
                for img_path in images:
                    if not os.path.exists(img_path):
                        raise FileNotFoundError(f"❌ 找不到图片文件: '{img_path}'")
                    mime_type, _ = mimetypes.guess_type(img_path)
                    mime_type = mime_type or "image/jpeg"
                    with open(img_path, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode("utf-8")
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                    })
                    
            # 拼装原生音频 (语音直传)
            if audio:
                if not os.path.exists(audio):
                    raise FileNotFoundError(f"❌ 找不到音频文件: '{audio}'")
                mime_type, _ = mimetypes.guess_type(audio)
                mime_type = mime_type or "audio/mp3"
                # 处理常见的 mp3 后缀拼写兼容
                if mime_type == "audio/mpeg" and audio.endswith(".mp3"):
                    mime_type = "audio/mp3"
                    
                with open(audio, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                
                # 不同云端服务商有细微差异，我们支持标准的 OpenAI 音频多模态 Payload 规范
                content_list.append({
                    "type": "input_audio",
                    "input_audio": {
                        "data": b64_data,
                        "format": mime_type.split("/")[-1]
                    }
                })
                
            # 将 user 消息重写为 list 格式的消息体
            messages[user_msg_idx]["content"] = content_list
            return messages

    def _inject_skills_system_prompt(self, messages: List[Dict[str, str]], allowed_skills: List[str]) -> List[Dict[str, str]]:
        """动态在大脑指令最前端或 System Prompt 中注入允许调用的防幻觉标记说明"""
        rules = ["\n⚠️ 【物理底座算力注入规则约束】:"]
        
        if "web_search" in allowed_skills:
            rules.append(
                "  - 【联网检索技能】: 如果您需要最新、真实、客观的信息，您可以在回答中插入 `[SEARCH]关键字[/SEARCH]` 标记启动联网搜索。"
            )
        if "code_sandbox" in allowed_skills:
            rules.append(
                "  - 【高精度算术技能】: 如果您需要精确算术、物理/数学逻辑推演，您必须在回答中插入 `[CODE]Python 代码[/CODE]` 标记以安全执行代码，杜绝心算幻觉。"
            )
        if "skills_evolution" in allowed_skills:
            rules.append(
                "  - 【技能自演化系统】: 您拥有创建与重用技能脚本的能力！\n"
                "    1. 沉淀技能: 当有通用的算法、正则或提取规则需要永久保存时，请发出 `[WRITE_SKILL]技能文件名|Python代码[/WRITE_SKILL]`，它会沉淀下来。\n"
                "    2. 运行技能: 在后续推理中，直接发出 `[RUN_SKILL]技能文件名|参数[/RUN_SKILL]` 即可直接运行并复用该脚本，无需再次生成大段源码。\n"
                "    3. 检索技能库: 发出 `[LIST_SKILLS][/LIST_SKILLS]` 可以列出当前已习得的所有技能文件清单。"
            )
            
        rules.append(
            "请注意：如果您发出了上述标记，底座会智能拦截并回调运行结果至您的上下文，再次向您提问以生成最终回答。所以，请大胆地使用这些标签！"
        )
        
        rules_text = "\n".join(rules)
        
        # 寻找 system message 进行注入，如果没有则强行追加在第一条 User Message 顶部
        system_idx = -1
        for idx, msg in enumerate(messages):
            if msg["role"] == "system":
                system_idx = idx
                break
                
        if system_idx != -1:
            messages[system_idx]["content"] += "\n" + rules_text
        else:
            # 注入在第一条消息顶部
            if len(messages) > 0 and isinstance(messages[0]["content"], str):
                messages[0]["content"] = rules_text + "\n\n" + messages[0]["content"]
                
        return messages

    def _call_llm_api(self, provider: str, model_name: str, messages: List[Dict[str, Any]], temperature: float, max_tokens: int) -> str:
        """底层物理 API 交互，拒绝 Mock，网络异常直接抛出"""
        headers = {"Content-Type": "application/json"}
        
        # 0. 动态解析此 provider 的专属 API Key 与 Base 节点
        provider_cfg = self.config.providers.get(provider, {})
        api_key = provider_cfg.get("api_key", "")
        api_base = provider_cfg.get("api_base", "")
        
        # 1. 本地 Ollama 算力调用
        if provider == "ollama":
            ollama_host = api_base or self.config.ollama_host
            url = f"{ollama_host}/api/chat"
            payload = {
                "model": model_name,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "think": False  # ⚠️ 锁死思考模式参数以防止太慢与啰嗦
                }
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            
            try:
                with urllib.request.urlopen(req, timeout=300) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    return res_data["message"]["content"]
            except Exception as e:
                logger.error(f"本地 Ollama 调用异常: {e}")
                raise OllamaNotReadyError(
                    f"❌ 物理层无法连通本地 Ollama 算力服务 (Ollama host: {ollama_host})，错误信息: {e}"
                )
                
        # 2. 远程多模态大模型兼容 OpenAI 格式接口调用
        else:
            if not api_base:
                raise ValueError(f"❌ 未找到大模型服务商 '{provider}' 的有效 API Base 配置！")
            
            url = f"{api_base}/chat/completions"
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    return res_data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"云端大模型 API 调用异常: {e}")
                # 捕获 HTTP 401 等具体报错状态码
                if isinstance(e, urllib.error.HTTPError):
                    err_msg = e.read().decode("utf-8", errors="ignore")
                    raise RuntimeError(
                        f"❌ 云端大模型接口 ({provider}) 返回 HTTP {e.code} 错误。响应详情: {err_msg}"
                    )
                raise RuntimeError(f"❌ 物理层无法连通云端大模型服务接口 ({provider}): {e}")
