from typing import Any


def inject_skills_system_prompt(
    messages: list[dict[str, Any]], allowed_skills: list[str]
) -> list[dict[str, Any]]:
    rules = ["\n⚠️ 【物理底座算力注入规则约束】:"]

    if "web_search" in allowed_skills:
        rules.append(
            "  - 【联网检索技能】: 如果您需要最新、真实、客观的信息，您可以在回答中插入 `[SEARCH]关键字[/SEARCH]` 标记启动联网搜索。"
        )
    if "code_sandbox" in allowed_skills:
        rules.append(
            "  - 【高精度算术技能】: 如果您需要精确算术、物理/数学逻辑推演，您必须在回答中插入 `[CODE]Python 代码[/CODE]` 标记以安全执行代码，杜绝心算幻觉。"
        )
    if "local_file" in allowed_skills:
        rules.append(
            "  - 【受控本地文件技能】: 读取文件使用 `[READ_FILE]相对路径[/READ_FILE]`；列出目录使用 `[LIST_FILES]相对路径[/LIST_FILES]`。只能访问 Runtime 分配的本地文件根目录。"
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
