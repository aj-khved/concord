from dataclasses import dataclass

from concord.risk.scoring import RiskAssessment
from concord.risk.summarizer import build_user_message, summarize_risk


def test_build_user_message_includes_score_level_and_notes():
    assessment = RiskAssessment(risk_score=72, risk_level="High")
    message = build_user_message(assessment, "Flagged during a screening cycle.")
    assert "risk_level: High" in message
    assert "risk_score: 72/100" in message
    assert "Flagged during a screening cycle." in message


# --- Fake Anthropic client for testing summarize_risk without network ---


@dataclass
class _FakeTextBlock:
    type: str
    text: str


@dataclass
class _FakeResponse:
    content: list


class _FakeMessages:
    def __init__(self, text: str):
        self._text = text
        self.last_call_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        return _FakeResponse(content=[_FakeTextBlock(type="text", text=self._text)])


class _FakeClient:
    def __init__(self, text: str):
        self.messages = _FakeMessages(text)


def test_summarize_risk_returns_model_text_on_success():
    client = _FakeClient("This vendor has a clean payment history and low overall risk.")
    result = summarize_risk(
        client, RiskAssessment(risk_score=10, risk_level="Low"), "No adverse findings.", model="m"
    )
    assert result.summary == "This vendor has a clean payment history and low overall risk."
    assert result.fallback_used is False


def test_summarize_risk_falls_back_on_empty_response():
    client = _FakeClient("")
    result = summarize_risk(
        client, RiskAssessment(risk_score=90, risk_level="Critical"), "Sanctioned.", model="m"
    )
    assert result.fallback_used is True
    assert "Critical" in result.summary


def test_summarize_risk_falls_back_on_overly_long_response():
    client = _FakeClient("x" * 1000)
    result = summarize_risk(
        client, RiskAssessment(risk_score=50, risk_level="Medium"), "Some note.", model="m"
    )
    assert result.fallback_used is True


def test_summarize_risk_does_not_force_a_tool_call():
    # Unlike M4's adjudicator, this is a generation task, not a classification
    # decision -- free text is the right output shape, so no tool/tool_choice
    # should be sent.
    client = _FakeClient("Low risk vendor.")
    summarize_risk(client, RiskAssessment(risk_score=10, risk_level="Low"), "Clean.", model="m")
    assert "tools" not in client.messages.last_call_kwargs
    assert "tool_choice" not in client.messages.last_call_kwargs
