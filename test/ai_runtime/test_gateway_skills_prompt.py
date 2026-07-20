from ai_runtime.gateway.agent import RuntimeAgent
from ai_runtime.gateway.skills_prompt import inject_skills_system_prompt


def test_inject_skills_system_prompt_matches_agent_wrapper():
    agent = RuntimeAgent()
    messages = [{"role": "user", "content": "Hello"}]
    wrapper_messages = [{"role": "user", "content": "Hello"}]

    result = inject_skills_system_prompt(messages, ["web_search", "code_sandbox"])
    wrapper_result = agent._inject_skills_system_prompt(
        wrapper_messages, ["web_search", "code_sandbox"]
    )

    assert result == wrapper_result
    assert "[SEARCH]" in result[0]["content"]
    assert "[CODE]" in result[0]["content"]


def test_inject_skills_system_prompt_extends_existing_system_message():
    messages = [
        {"role": "system", "content": "You are careful."},
        {"role": "user", "content": "Hello"},
    ]

    result = inject_skills_system_prompt(messages, ["skills_evolution"])

    assert result[0]["content"].startswith("You are careful.")
    assert "[WRITE_SKILL]" in result[0]["content"]
    assert result[1]["content"] == "Hello"


def test_inject_skills_system_prompt_keeps_empty_skill_set_quiet():
    messages = [{"role": "user", "content": "Hello"}]

    result = inject_skills_system_prompt(messages, [])

    assert "[SEARCH]" not in result[0]["content"]
    assert "[CODE]" not in result[0]["content"]
    assert "[WRITE_SKILL]" not in result[0]["content"]
