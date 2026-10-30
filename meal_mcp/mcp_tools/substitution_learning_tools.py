from db.db import session_scope
from mcp_tools.server import mcp
from services.substitution_learning_service import SubstitutionLearningService


@mcp.tool()
def suggest_substitutions(
    ingredients: list[str],
    constraints: dict | None = None,
) -> dict:
    """Start the suggestion workflow for several ingredients.

    Returns active substitutions, still pending suggestions and, for ingredients without either,
    a structured suggestion_request (constraints, required tags, targets to avoid). Generate
    candidates for that request and store them with record_substitution_suggestions.
    Constraints example: {"diet": "vegan", "required_tags": ["nut free"], "excluded_ingredients": ["tofu"]}.
    """
    with session_scope() as session:
        return SubstitutionLearningService(session).suggest_substitutions(ingredients, constraints)


@mcp.tool()
def record_substitution_suggestions(
    suggestions: list[dict],
    constraints: dict | None = None,
) -> dict:
    """Validate and store candidate substitutions as pending suggestions.

    Each suggestion needs source_ingredient, target_ingredient, reason, confidence and tags.
    Candidates violating the constraints or previously rejected under the same constraints are
    returned in excluded_candidates. Pending suggestions are decided with approve_substitutions
    or reject_substitutions.
    """
    with session_scope() as session:
        return SubstitutionLearningService(session).record_suggestions(suggestions, constraints)


@mcp.tool()
def approve_substitutions(
    suggestions: list[dict],
    constraints: dict | None = None,
) -> dict:
    """Approve pending suggestions and activate them in the knowledge base.

    Each item: {"id": <suggestion id>} or source_ingredient/target_ingredient, plus an optional
    "feedback" with the user's own words. Calling it again for an already approved suggestion with
    "feedback" adds the comment later.
    """
    with session_scope() as session:
        return SubstitutionLearningService(session).approve_substitutions(suggestions, constraints)


@mcp.tool()
def reject_substitutions(
    suggestions: list[dict],
    constraints: dict | None = None,
) -> dict:
    """Reject pending suggestions and record the decision.

    Each item: {"id": <suggestion id>} or source_ingredient/target_ingredient, plus "feedback"
    with the user's reason for the rejection (e.g. "mag ich nicht"). Calling it again for an
    already rejected suggestion with "feedback" adds the reason later.
    """
    with session_scope() as session:
        return SubstitutionLearningService(session).reject_substitutions(suggestions, constraints)


@mcp.tool()
def list_substitution_suggestions(status: str | None = None) -> dict:
    """List recorded suggestions, optionally filtered by status: pending, approved or rejected."""
    with session_scope() as session:
        return SubstitutionLearningService(session).list_suggestions(status)


@mcp.tool()
def list_substitution_feedback(accepted: bool | None = None) -> dict:
    """List feedback for learned substitution suggestions."""
    with session_scope() as session:
        return SubstitutionLearningService(session).list_feedback(accepted)
