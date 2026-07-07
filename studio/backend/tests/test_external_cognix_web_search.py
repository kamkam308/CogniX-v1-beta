from routes.inference import (
    _external_enabled_tools_after_cognix_web_search,
    _external_latest_user_text,
    _external_provider_needs_cognix_web_search,
    _local_request_needs_cognix_web_search,
    _with_cognix_web_search_context,
)


def test_cognix_web_search_needed_for_huggingface_and_ollama():
    assert _external_provider_needs_cognix_web_search(
        "huggingface",
        ["web_search"],
        None,
    )
    assert _external_provider_needs_cognix_web_search("ollama", ["web_search"], None)


def test_cognix_web_search_skips_native_providers_and_disabled_tool_choice():
    assert not _external_provider_needs_cognix_web_search(
        "openai",
        ["web_search"],
        None,
    )
    assert not _external_provider_needs_cognix_web_search(
        "huggingface",
        ["web_search"],
        "none",
    )
    assert not _external_provider_needs_cognix_web_search(
        "huggingface",
        ["web_search"],
        {"type": "function", "function": {"name": "python"}},
    )


def test_forwarded_enabled_tools_remove_cognix_web_search_only():
    assert _external_enabled_tools_after_cognix_web_search(
        "huggingface",
        ["web_search", "code_execution"],
    ) == ["code_execution"]
    assert (
        _external_enabled_tools_after_cognix_web_search(
            "huggingface",
            ["web_search"],
        )
        is None
    )
    assert _external_enabled_tools_after_cognix_web_search(
        "openai",
        ["web_search"],
    ) == ["web_search"]


def test_local_cognix_web_search_runs_when_tool_loop_is_unavailable():
    assert _local_request_needs_cognix_web_search(
        True,
        ["web_search"],
        None,
        tool_loop_active = False,
    )
    assert _local_request_needs_cognix_web_search(
        True,
        None,
        None,
        tool_loop_active = False,
    )
    assert not _local_request_needs_cognix_web_search(
        True,
        ["web_search"],
        None,
        tool_loop_active = True,
    )
    assert not _local_request_needs_cognix_web_search(
        False,
        ["web_search"],
        None,
        tool_loop_active = False,
    )
    assert not _local_request_needs_cognix_web_search(
        True,
        ["python"],
        None,
        tool_loop_active = False,
    )


def test_latest_user_text_extracts_plain_and_multimodal_messages():
    assert (
        _external_latest_user_text(
            [
                {"role": "user", "content": "old"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "latest"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    ],
                },
            ],
        )
        == "latest"
    )


def test_cognix_web_search_context_is_inserted_after_system_messages():
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "latest?"},
    ]
    output = _with_cognix_web_search_context(
        messages,
        query = "latest?",
        result = "Title: Result\nURL: https://example.com",
    )

    assert output[0] == messages[0]
    assert output[1]["role"] == "system"
    assert "CogniX web_search results" in output[1]["content"]
    assert "https://example.com" in output[1]["content"]
    assert output[2] == messages[1]
