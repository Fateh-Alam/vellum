"""Deterministic compilation of Study Builder facets into Anki search syntax."""

from __future__ import annotations

from .models import (
    BuilderDefinition,
    BuilderOrder,
    BuilderSelector,
    CardMaturity,
    FilterOperator,
    StatePreset,
)


def quote_search_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _or_group(prefix: str, values: tuple[str, ...]) -> str:
    terms = tuple(f"{prefix}:{quote_search_value(value)}" for value in values)
    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    return "(" + " or ".join(terms) + ")"


def _negated_group(prefix: str, values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"-{prefix}:{quote_search_value(value)}" for value in values)


def _state_term(preset: StatePreset) -> str:
    return {
        StatePreset.DUE_NEW: "(is:due or is:new)",
        StatePreset.DUE: "is:due",
        StatePreset.NEW: "is:new",
        StatePreset.RECENT_FAILURES: "rated:7:1",
        StatePreset.ALL: "",
    }[preset]


def selector_term(selector: BuilderSelector) -> str:
    if selector.kind == "state":
        return {
            "new": "is:new",
            "learn": "is:learn",
            "review": "is:review",
            "due": "is:due",
            "suspended": "is:suspended",
            "buried": "is:buried",
        }.get(selector.value, "")
    if selector.kind == "flag":
        try:
            value = int(selector.value)
        except ValueError:
            return ""
        return f"flag:{value}" if 0 <= value <= 7 else ""
    return f"{selector.kind}:{quote_search_value(selector.value)}"


def _compiled_filter_groups(definition: BuilderDefinition) -> tuple[str, ...]:
    compiled: list[str] = []
    for group in definition.filter_groups:
        selector_terms = tuple(
            term for selector in group.selectors if (term := selector_term(selector))
        )
        if not selector_terms:
            continue
        if group.operator is FilterOperator.ANY and len(selector_terms) > 1:
            compiled.append("(" + " or ".join(selector_terms) + ")")
        else:
            compiled.extend(selector_terms)
    return tuple(compiled)


def compile_builder_query(definition: BuilderDefinition) -> str:
    """Compile only the requested scope; availability is layered on separately."""

    terms: list[str] = []
    typed = definition.advanced_query.strip() or definition.text_query.strip()
    if typed:
        terms.append(f"({typed})")
    topic_scope = _or_group("tag", definition.topic_tags)
    if topic_scope:
        terms.append(topic_scope)
    deck_scope = _or_group("deck", definition.source_decks)
    if deck_scope:
        terms.append(deck_scope)
    terms.extend(_compiled_filter_groups(definition))
    for prefix, values in (
        ("deck", definition.decks),
        ("tag", definition.topics),
        ("tag", definition.tags),
        ("note", definition.note_types),
        ("card", definition.card_types),
    ):
        group = _or_group(prefix, values)
        if group:
            terms.append(group)
    for values in definition.topic_groups:
        group = _or_group("tag", values)
        if group:
            terms.append(group)
    if definition.states:
        state_terms = tuple(
            {
                "new": "is:new",
                "learn": "is:learn",
                "review": "is:review",
                "due": "is:due",
                "suspended": "is:suspended",
                "buried": "is:buried",
            }[state]
            for state in dict.fromkeys(definition.states)
            if state in {"new", "learn", "review", "due", "suspended", "buried"}
        )
        if state_terms:
            terms.append(
                state_terms[0]
                if len(state_terms) == 1
                else "(" + " or ".join(state_terms) + ")"
            )
    if definition.flags:
        flags = tuple(f"flag:{flag}" for flag in dict.fromkeys(definition.flags))
        terms.append(flags[0] if len(flags) == 1 else "(" + " or ".join(flags) + ")")
    terms.extend(_negated_group("deck", definition.excluded_decks))
    terms.extend(_negated_group("tag", definition.excluded_tags))
    state = _state_term(definition.state_preset)
    if state:
        terms.append(state)
    quick = definition.quick_filters
    if quick.recent_again_days is not None:
        terms.append(f"rated:{quick.recent_again_days}:1")
    if quick.added_days is not None:
        terms.append(f"added:{quick.added_days}")
    if quick.reviewed_days is not None:
        terms.append(f"rated:{quick.reviewed_days}")
    if quick.marked:
        terms.append("tag:marked")
    if quick.leech:
        terms.append("tag:leech")
    if quick.maturity is CardMaturity.YOUNG:
        terms.append("(is:review prop:ivl<21)")
    elif quick.maturity is CardMaturity.MATURE:
        terms.append("prop:ivl>=21")
    return " ".join(terms).strip()


def availability_query(base: str, bucket: str, include_suspended: bool = False) -> str:
    suffix = {
        "ready": "-is:suspended -is:buried -deck:filtered",
        "suspended": "is:suspended -is:buried -deck:filtered",
        "buried": "is:buried",
        "filtered": "deck:filtered",
        "selectable": (
            "-is:buried -deck:filtered"
            if include_suspended
            else "-is:suspended -is:buried -deck:filtered"
        ),
    }.get(bucket)
    if suffix is None:
        raise ValueError(f"Unknown Study Builder availability bucket: {bucket}")
    return f"{base} {suffix}".strip()


ORDER_SQL: dict[BuilderOrder, str | bool] = {
    BuilderOrder.DUE: "c.due asc, c.id asc",
    BuilderOrder.MOST_AT_RISK: "relative_overdueness",
    BuilderOrder.MOST_LAPSES: "c.lapses desc, c.due asc, c.id asc",
    BuilderOrder.OLDEST_SEEN: "oldest_seen",
    BuilderOrder.ADDED: "c.id asc",
    BuilderOrder.RANDOM: "random() asc",
}


FILTERED_DECK_ORDER: dict[BuilderOrder, int] = {
    BuilderOrder.OLDEST_SEEN: 0,
    BuilderOrder.RANDOM: 1,
    BuilderOrder.MOST_LAPSES: 4,
    BuilderOrder.ADDED: 5,
    BuilderOrder.DUE: 6,
    BuilderOrder.MOST_AT_RISK: 8,
}
