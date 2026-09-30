"""Generate LLM plain-English risk summaries (M6/FR9) for vendor_risk_profiles
that don't have one yet. Capped at settings.llm_max_calls_per_run, same as
M4's adjudication script.

Requires ANTHROPIC_API_KEY in your local .env.

Usage:
    uv run python scripts/run_risk_summarization.py
"""

from sqlalchemy import select

from concord.config import settings
from concord.db.models import VendorRiskProfile
from concord.db.session import get_session
from concord.observability.cost import estimate_cost_usd
from concord.observability.pipeline_run import track_pipeline_run
from concord.risk.scoring import RiskAssessment
from concord.risk.summarizer import summarize_risk

if __name__ == "__main__":
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — add it to your local .env first.")

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, base_url=settings.llm_base_url)

    session = next(get_session())
    try:
        with track_pipeline_run(session, "risk_summarization") as run:
            profiles = (
                session.execute(
                    select(VendorRiskProfile).where(VendorRiskProfile.llm_summary.is_(None))
                )
                .scalars()
                .all()
            )
            to_summarize = profiles[: settings.llm_max_calls_per_run]

            print(f"Risk profiles without a summary: {len(profiles)}")
            print(
                f"Summarizing now (capped at {settings.llm_max_calls_per_run}): {len(to_summarize)}"
            )

            total_input_tokens = 0
            total_output_tokens = 0
            fallback_count = 0

            for profile in to_summarize:
                assessment = RiskAssessment(
                    risk_score=profile.risk_score, risk_level=profile.risk_level
                )
                result = summarize_risk(client, assessment, profile.notes, model=settings.llm_model)
                profile.llm_summary = result.summary
                profile.llm_model = settings.llm_model
                total_input_tokens += result.input_tokens
                total_output_tokens += result.output_tokens
                if result.fallback_used:
                    fallback_count += 1
                fallback_note = (
                    " (fallback — LLM output failed validation)" if result.fallback_used else ""
                )
                line = f"{profile.legal_name!r} [{profile.risk_level}]: {result.summary}"
                print(f"  {line}{fallback_note}")

            session.commit()

            run.summary = {
                "profiles_without_summary": len(profiles),
                "summarized_this_run": len(to_summarize),
                "fallback_count": fallback_count,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "estimated_cost_usd": estimate_cost_usd(total_input_tokens, total_output_tokens),
            }
    finally:
        session.close()
