from typing import Any


def inject_skills_system_prompt(
    messages: list[dict[str, Any]], allowed_skills: list[str]
) -> list[dict[str, Any]]:
    safe_skills = {
        skill for skill in allowed_skills if skill in {"web_search", "local_file"}
    }
    if not safe_skills:
        return messages
    rules = ["\n⚠️ 【物理底座算力注入规则约束】:"]

    if "web_search" in safe_skills:
        rules.append(
            "  - 【联网检索技能】: 如果您需要最新、真实、客观的信息，您可以在回答中插入 `[SEARCH]关键字[/SEARCH]` 标记启动联网搜索。"
        )
    if "local_file" in safe_skills:
        rules.append(
            "  - 【受控本地文件技能】: 读取文件使用 `[READ_FILE]相对路径[/READ_FILE]`；列出目录使用 `[LIST_FILES]相对路径[/LIST_FILES]`。只能访问 Runtime 分配的本地文件根目录。"
        )
    rules.append(
        "请注意：如果您发出了上述标记，底座会智能拦截并回调运行结果至您的上下文，再次向您提问以生成最终回答。所以，请大胆地使用这些标签！"
    )
    rules_text = "\n".join(rules)

    system_idx = -1
    for idx, msg in enumerate(messages):
        if msg["role"] == "system":
            system_idx = idx
            break

    if system_idx != -1:
        messages[system_idx]["content"] += "\n" + rules_text
        return messages

    if len(messages) > 0 and isinstance(messages[0]["content"], str):
        messages[0]["content"] = rules_text + "\n\n" + messages[0]["content"]

    return messages
