from app.fcm_catalog import parse_fcm_sources, reconcile_catalog


SAMPLE = """
export const groq = [
  ['openai/gpt-oss-120b', 'GPT OSS 120B', 'S', '62.4%', '131k'],
  // ignored comment
  ['qwen/qwen3.8-27b', 'Qwen 3.8 27B', 'A+', '-', '131k'],
]

export const qwen = [
  ['qwen3-coder-plus', 'Qwen Coder Plus', 'S+', '75.0%', '1M'],
]
"""


def test_safe_fcm_parser():
    parsed = parse_fcm_sources(SAMPLE)
    assert parsed["groq"][0]["id"] == "openai/gpt-oss-120b"
    assert parsed["groq"][0]["quality"] == 0.624
    assert parsed["groq"][0]["context"] == 131000
    assert parsed["dashscope"][0]["context"] == 1000000


def test_reconciliation_never_promotes():
    parsed = parse_fcm_sources(SAMPLE)
    report = reconcile_catalog(
        parsed,
        {
            "groq": {"openai/gpt-oss-120b"},
            "dashscope": {"old-model"},
        },
    )
    assert report["providers"]["groq"]["candidate_additions"] == ["qwen/qwen3.8-27b"]
    assert report["providers"]["dashscope"]["missing_upstream"] == ["old-model"]
    assert report["candidate_additions"] == 2
