"""Classification + minimization unit tests (deterministic tiers only)."""

from app.core.enums import RiskCategory
from app.domain.classification.pipeline import classify_prompt
from app.domain.classification.registry import lexical_scores, reference_examples
from app.domain.capture.minimize import build_preview, redact_text, sha256_text, truncate


def test_reference_corpus_is_valid():
    corpus = reference_examples()
    assert set(corpus) == {"source_code", "financial", "confidential", "credentials"}
    for spec in corpus.values():
        assert spec["keywords"] and spec["examples"]


def test_credentials_detected_by_regex_tier():
    result = classify_prompt("AKIA1234567890ABCDEF is the key", quick=True)
    assert result.category == RiskCategory.credentials
    assert result.score >= 0.9
    assert result.flagged is True
    assert any(d.label == "AWS_ACCESS_KEY" for d in result.detections)


def test_private_key_block_scores_high():
    result = classify_prompt("attaching:\n-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n", quick=True)
    assert result.category == RiskCategory.credentials
    assert result.flagged is True


def test_email_is_pii():
    result = classify_prompt("ping dana@corp.example about the ticket", quick=True)
    assert result.category == RiskCategory.pii
    assert result.score >= 0.5


def test_credit_card_requires_luhn():
    valid = classify_prompt("card 4111 1111 1111 1111 for the invoice", quick=True)
    invalid_digits = classify_prompt("ref 4111111111111112 was rejected", quick=True)
    assert any(d.label == "CREDIT_CARD" for d in valid.detections)
    assert not any(d.label == "CREDIT_CARD" for d in invalid_digits.detections)


def test_benign_text_is_unflagged():
    result = classify_prompt("Write a haiku about autumn rain", quick=True)
    assert result.flagged is False
    assert result.score < 0.5


def test_lexical_scores_favor_matching_categories():
    code = lexical_scores("def parse(path):\n    import yaml\n    return yaml.load(path)")
    confidential = lexical_scores(
        "CONFIDENTIAL internal only: do not share the roadmap or the acquisition plan"
    )
    financial = lexical_scores("Q3 revenue forecast and EBITDA margin on the invoice budget")

    assert code[RiskCategory.source_code] > code[RiskCategory.financial]
    assert confidential[RiskCategory.confidential] > confidential[RiskCategory.source_code]
    assert financial[RiskCategory.financial] > financial[RiskCategory.source_code]


def test_empty_prompt_returns_none_category():
    result = classify_prompt("", quick=True)
    assert result.category == RiskCategory.none
    assert result.score == 0.0
    assert result.flagged is False


def test_sha256_is_stable_and_hex():
    assert sha256_text("abc") == sha256_text("abc")
    assert len(sha256_text("abc")) == 64
    assert sha256_text(None) is None


def test_redaction_masks_sensitive_values():
    masked = redact_text("reach me at jane.doe@corp.example or 123-45-6789")
    assert "jane.doe@corp.example" not in masked
    assert "123-45-6789" not in masked
    assert "[REDACTED]" in masked


def test_preview_is_truncated_and_masked():
    long_text = ("contact jane.doe@corp.example " * 100).strip()
    preview = build_preview(long_text)
    assert preview is not None
    assert len(preview) <= 450  # redacted_preview_chars + truncation marker
    assert "jane.doe@corp.example" not in preview


def test_truncate_adds_marker():
    assert truncate("x" * 100, 10).endswith("…[truncated]") or \
           truncate("x" * 100, 10).endswith("...[truncated]") or \
           "[truncated]" in truncate("x" * 100, 10)
    assert truncate("short", 100) == "short"
