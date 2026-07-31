from ai_runtime.gateway.skills_prompt import inject_skills_system_prompt


def test_inject_skills_system_prompt_advertises_only_enabled_safe_tools():
    messages = [{"role": "user", "content": "Hello"}]

    result = inject_skills_system_prompt(messages, ["web_search", "code_sandbox"])

    assert "[SEARCH]" in result[0]["content"]
    assert "[CODE]" not in result[0]["content"]


def test_inject_skills_system_prompt_extends_existing_system_message():
    messages = [
        {"role": "system", "content": "You are careful."},
        {"role": "user", "content": "Hello"},
    ]

    result = inject_skills_system_prompt(messages, ["skills_evolution"])

    assert result[0]["content"] == "You are careful."
    assert "[WRITE_SKILL]" not in result[0]["content"]
    assert result[1]["content"] == "Hello"


def test_inject_skills_system_prompt_keeps_empty_skill_set_quiet():
    messages = [{"role": "user", "content": "Hello"}]

    result = inject_skills_system_prompt(messages, [])

    assert "[SEARCH]" not in result[0]["content"]
    assert "[CODE]" not in result[0]["content"]
    assert "[WRITE_SKILL]" not in result[0]["content"]
