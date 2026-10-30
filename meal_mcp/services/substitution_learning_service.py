from repo.substitution_feedback_repo import SubstitutionFeedbackRepo
from repo.substitution_repo import SubstitutionRepo
from repo.substitution_suggestion_repo import SubstitutionSuggestionRepo
from services.constraint_service import (
    constraint_violation,
    constraints_hash,
    excluded_terms,
    label_check_note,
    normalize_constraints,
    required_tags,
)
from services.measure_service import normalize_ingredient_name
from services.substitution_service import SubstitutionService

MAX_SUGGESTIONS_PER_INGREDIENT = 3
SAME_CONTEXT_REJECTION_PENALTY = 0.5
OTHER_CONTEXT_REJECTION_PENALTY = 0.75


class SubstitutionLearningService:
    """Learning workflow: suggest → record (pending) → approve / reject → reuse via find_substitutions."""

    def __init__(self, session):
        self.substitution_service = SubstitutionService(session)
        self.substitution_repo = SubstitutionRepo(session)
        self.feedback_repo = SubstitutionFeedbackRepo(session)
        self.suggestion_repo = SubstitutionSuggestionRepo(session)

    def suggest_substitutions(self, ingredients: list[str], constraints: dict | None = None) -> dict:
        constraints = normalize_constraints(constraints)
        digest = constraints_hash(constraints)
        sources = list(dict.fromkeys(normalize_ingredient_name(value) for value in ingredients if value.strip()))

        known = self.substitution_service.find_substitutions(sources, constraints)
        pending = self.suggestion_repo.list_pending(sources, constraints)
        rejections = self.feedback_repo.find_rejections(sources)
        missing = [source for source in sources if not known.get(source) and not pending.get(source)]

        avoid = {
            source: sorted(
                excluded_terms(constraints)
                | {entry["target_ingredient"] for entry in rejections[source] if entry["constraints_hash"] == digest}
            )
            for source in missing
        }

        if missing:
            status = "candidates_required"
        elif any(pending.values()):
            status = "pending_suggestions"
        else:
            status = "known"

        return {
            "status": status,
            "known_substitutions": {source: rows for source, rows in known.items() if rows},
            "pending_suggestions": {source: rows for source, rows in pending.items() if rows},
            "missing_ingredients": missing,
            "constraints": constraints,
            "suggestion_request": {
                "ingredients": missing,
                "constraints": constraints,
                "required_tags": sorted(required_tags(constraints)),
                "avoid_targets": avoid,
                "max_per_ingredient": MAX_SUGGESTIONS_PER_INGREDIENT,
                "candidate_fields": [
                    "source_ingredient", "target_ingredient", "reason", "confidence", "tags",
                    "quantity_ratio", "quantity_note",
                ],
                "quantity_hint": "quantity_ratio = grams of target per gram of source (1.0 if equal by weight); "
                                 "quantity_note for anything a ratio cannot express.",
                "next_tool": "record_substitution_suggestions",
            } if missing else None,
        }

    def record_suggestions(self, suggestions: list[dict], constraints: dict | None = None) -> dict:
        recorded: list[dict] = []
        excluded: list[dict] = []
        sources = sorted({
            normalize_ingredient_name(str(item.get("source_ingredient", "")))
            for item in suggestions
            if str(item.get("source_ingredient", "")).strip()
        })
        rejections = self.feedback_repo.find_rejections(sources)
        active = self.substitution_repo.find_bulk(sources)

        for item in suggestions:
            item_constraints = normalize_constraints(
                constraints if constraints is not None else item.get("constraints")
            )
            digest = constraints_hash(item_constraints)
            source = normalize_ingredient_name(str(item.get("source_ingredient", "")))
            target = normalize_ingredient_name(str(item.get("target_ingredient", "")))
            candidate = {**item, "source_ingredient": source, "target_ingredient": target}

            if not source:
                excluded.append({"target_ingredient": target, "reason": "Missing source ingredient"})
                continue
            violation = constraint_violation(candidate, item_constraints)
            if violation:
                excluded.append({"source_ingredient": source, "target_ingredient": target, "reason": violation})
                continue
            if any(row["target_ingredient"] == target for row in active.get(source, [])):
                excluded.append({
                    "source_ingredient": source,
                    "target_ingredient": target,
                    "reason": "Already an active substitution",
                })
                continue

            notes: list[str] = []
            confidence = float(candidate.get("confidence", 0.5))
            reopen = False
            previous = [entry for entry in rejections.get(source, []) if entry["target_ingredient"] == target]
            same_context = [entry for entry in previous if entry["constraints_hash"] == digest]
            new_reason = normalize_ingredient_name(str(candidate.get("reason") or ""))
            if same_context:
                old_reasons = {normalize_ingredient_name(str(entry.get("suggestion_reason") or "")) for entry in same_context}
                if not new_reason or new_reason in old_reasons:
                    excluded.append({
                        "source_ingredient": source,
                        "target_ingredient": target,
                        "reason": "Previously rejected under the same constraints",
                    })
                    continue
                confidence *= SAME_CONTEXT_REJECTION_PENALTY
                reopen = True
                notes.append("Previously rejected under the same constraints; re-suggested with a new reason.")
            elif previous:
                confidence *= OTHER_CONTEXT_REJECTION_PENALTY
                notes.append("Previously rejected under different constraints.")

            candidate["confidence"] = round(confidence, 3)
            suggestion, _ = self.suggestion_repo.add_pending(candidate, item_constraints, reopen_rejected=reopen)
            if notes:
                suggestion["notes"] = notes
            note = label_check_note(suggestion, item_constraints)
            if note:
                suggestion["label_check"] = note
            recorded.append(suggestion)

        recorded.sort(key=lambda row: (row["source_ingredient"], -row["confidence"]))
        known = self.substitution_service.find_substitutions(
            sources, normalize_constraints(constraints) if constraints is not None else {}
        )
        return {
            "status": "suggestions_created" if recorded else "no_valid_suggestions",
            "known_substitutions": {source: rows for source, rows in known.items() if rows},
            "suggestions": recorded,
            "excluded_candidates": excluded,
            "next_step": "Ask the user, then call approve_substitutions or reject_substitutions with the suggestion ids.",
        }

    def approve_substitutions(self, suggestions: list[dict], constraints: dict | None = None) -> dict:
        approved: list[dict] = []
        violations: list[dict] = []
        warnings: list[dict] = []
        decisions: list[dict] = []

        resolved, not_pending, decided = self._resolve_pending(suggestions, constraints)
        feedback_updated, already_decided = self._add_late_feedback(decided, accepted=True)
        for row, item, effective in resolved:
            candidate = self.suggestion_repo.serialize(row)
            violation = constraint_violation(candidate, effective)
            if violation:
                violations.append({**candidate, "reason": violation})
                continue

            tags = list(candidate["tags"])
            if "llm suggested" not in tags:
                tags.append("llm suggested")
            approved.append({**candidate, "tags": tags})
            decisions.append({**candidate, "constraints": effective, "feedback": self._user_feedback(item, candidate)})
            self.suggestion_repo.set_status(row, "approved")
            note = label_check_note(candidate, effective)
            if note:
                warnings.append({"target_ingredient": candidate["target_ingredient"], "label_check": note})

        persisted = self.substitution_repo.add_bulk(approved)
        feedback = self.feedback_repo.add_bulk(decisions, accepted=True)
        return {
            "status": "approved" if approved else "nothing_approved",
            "persisted": persisted,
            "feedback_created": feedback["created"],
            "feedback_existing": feedback["existing"],
            "feedback_updated": feedback_updated,
            "constraint_violations": violations,
            "already_decided": already_decided,
            "not_pending": not_pending,
            "warnings": warnings,
        }

    def reject_substitutions(self, suggestions: list[dict], constraints: dict | None = None) -> dict:
        decisions: list[dict] = []
        resolved, not_pending, decided = self._resolve_pending(suggestions, constraints)
        feedback_updated, already_decided = self._add_late_feedback(decided, accepted=False)
        for row, item, effective in resolved:
            candidate = self.suggestion_repo.set_status(row, "rejected")
            decisions.append({**candidate, "constraints": effective, "feedback": self._user_feedback(item, candidate)})

        feedback = self.feedback_repo.add_bulk(decisions, accepted=False)
        return {
            "status": "rejected" if decisions else "nothing_rejected",
            "rejected": feedback["created"],
            "feedback_existing": feedback["existing"],
            "feedback_updated": feedback_updated,
            "already_decided": already_decided,
            "not_pending": not_pending,
        }

    def list_feedback(self, accepted: bool | None = None) -> dict:
        return {
            "summary": self.feedback_repo.summary(),
            "entries": self.feedback_repo.list_all(accepted),
        }

    def list_suggestions(self, status: str | None = None) -> dict:
        return {"suggestions": self.suggestion_repo.list_all(status)}

    @staticmethod
    def _user_feedback(item: dict, candidate: dict) -> str | None:
        """The user's reason for a decision. Clients often send it as "reason" instead of "feedback"."""
        if item.get("feedback"):
            return str(item["feedback"])
        reason = item.get("reason")
        if reason and str(reason).strip() != (candidate.get("reason") or "").strip():
            return str(reason)
        return None

    def _add_late_feedback(self, decided: list, accepted: bool) -> tuple[list[dict], list[dict]]:
        """Attach the user's reason to a suggestion that was already decided the same way.

        Returns (updated feedback entries, suggestions that stay already decided).
        """
        status = "approved" if accepted else "rejected"
        updated: list[dict] = []
        already_decided: list[dict] = []
        for row, item in decided:
            candidate = self.suggestion_repo.serialize(row)
            text = self._user_feedback(item, candidate)
            entry = None
            if text and row.status == status:
                entry = self.feedback_repo.set_feedback(
                    row.source_ingredient, row.target_ingredient, accepted, row.constraints_hash, text
                )
            if entry:
                updated.append(entry)
            else:
                already_decided.append(candidate)
        return updated, already_decided

    def _resolve_pending(self, suggestions: list[dict], constraints: dict | None):
        """Split the requested items into pending rows, unknown items and already decided rows."""
        normalized = normalize_constraints(constraints) if constraints is not None else None
        resolved = []
        not_pending: list[dict] = []
        decided: list = []
        for item in suggestions:
            row = self.suggestion_repo.find_for_decision(item, normalized)
            if row is None:
                not_pending.append({
                    "source_ingredient": item.get("source_ingredient"),
                    "target_ingredient": item.get("target_ingredient"),
                    "id": item.get("id") or item.get("suggestion_id"),
                    "reason": "No recorded suggestion. Call record_substitution_suggestions first.",
                })
            elif row.status != "pending":
                decided.append((row, item))
            else:
                effective = normalized if normalized is not None else normalize_constraints(row.constraints)
                resolved.append((row, item, effective))
        return resolved, not_pending, decided
