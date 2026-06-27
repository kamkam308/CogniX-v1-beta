from utils.utils import safe_curated_detail


def test_safe_curated_detail_redacts_common_secret_shapes():
    detail = safe_curated_detail(
        RuntimeError(
            "failed with Authorization: Bearer abcdefghijklmnop "
            "api_key=sk-testabcdefghijkl hf_1234567890 password=plain"
        )
    )

    assert "Bearer abcdefghijklmnop" not in detail
    assert "sk-testabcdefghijkl" not in detail
    assert "hf_1234567890" not in detail
    assert "password=plain" not in detail
    assert "<redacted" in detail
