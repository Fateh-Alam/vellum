"""Read/query and scheduler-safe collection adapter for Study Builder."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
from typing import Any, Iterable

from ..builder.catalog import BuilderCatalog, build_catalog
from ..builder.models import (
    BuildRequest,
    BuildResult,
    BuilderDefinition,
    BuilderDiagnostic,
    BuilderFilterGroup,
    BuilderPreview,
    CardMaturity,
    FilterOperator,
    PreviewCard,
    StatePreset,
)
from ..builder.scope import DeckScopeNode, DeckTagScope, ScopedTagNode, TopicDeckScope
from ..builder.query import (
    FILTERED_DECK_ORDER,
    ORDER_SQL,
    availability_query,
    compile_builder_query,
)
from ..core.config import TopicParsingConfig
from ..sessions.generated_decks import GeneratedDeckCard, collect_generated_deck_cards


STATE_BY_QUEUE = {
    -3: "User buried",
    -2: "Sibling buried",
    -1: "Suspended",
    0: "New",
    1: "Learning",
    2: "Review",
    3: "Relearning",
    4: "Preview",
}
HTML = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")


def _quoted_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _or_search(prefix: str, values: tuple[str, ...]) -> str:
    terms = tuple(f"{prefix}:{_quoted_value(value)}" for value in values)
    if not terms:
        return ""
    return terms[0] if len(terms) == 1 else "(" + " or ".join(terms) + ")"


def _normal_decks(collection: Any) -> tuple[tuple[int, str], ...]:
    result: list[tuple[int, str]] = []
    for deck in collection.decks.all_names_and_ids(
        skip_empty_default=False, include_filtered=False
    ):
        try:
            deck_id = int(deck.id)
        except (AttributeError, TypeError, ValueError):
            continue
        name = str(deck.name).strip()
        if name:
            result.append((deck_id, name))
    return tuple(result)


def _card_home_decks(
    collection: Any, card_ids: tuple[int, ...]
) -> dict[int, int]:
    result: dict[int, int] = {}
    for start in range(0, len(card_ids), 500):
        chunk = card_ids[start : start + 500]
        placeholders = ",".join("?" for _value in chunk)
        for card_id, deck_id, original_deck_id in collection.db.all(
            f"select id, did, odid from cards where id in ({placeholders})",
            *chunk,
        ):
            result[int(card_id)] = int(original_deck_id or deck_id)
    return result


def collect_topic_deck_scope(
    collection: Any,
    topic_tags: tuple[str, ...],
    *,
    generation: int = 0,
    include_empty: bool = False,
) -> TopicDeckScope:
    """Return decks that actually contain the selected alternative topics."""

    topics = tuple(dict.fromkeys(value.strip() for value in topic_tags if value.strip()))
    if not topics:
        return TopicDeckScope(generation, (), (), 0)
    card_ids = tuple(int(card_id) for card_id in collection.find_cards(_or_search("tag", topics)))
    home_by_card = _card_home_decks(collection, card_ids)
    decks = _normal_decks(collection)
    name_by_id = dict(decks)
    exact_counts: dict[str, int] = {}
    for card_id in card_ids:
        name = name_by_id.get(home_by_card.get(card_id, 0))
        if name:
            exact_counts[name] = exact_counts.get(name, 0) + 1
    nodes: list[DeckScopeNode] = []
    for _deck_id, name in decks:
        prefix = name + "::"
        total = sum(
            count
            for candidate, count in exact_counts.items()
            if candidate == name or candidate.startswith(prefix)
        )
        if include_empty or total:
            path = tuple(name.split("::"))
            nodes.append(DeckScopeNode(name, path[-1], path, total))
    return TopicDeckScope(
        generation,
        topics,
        tuple(sorted(nodes, key=lambda node: tuple(part.casefold() for part in node.path))),
        len(card_ids),
    )


def collect_deck_tag_scope(
    collection: Any,
    source_decks: tuple[str, ...],
    catalog: BuilderCatalog,
    *,
    generation: int = 0,
) -> DeckTagScope:
    """Return the human-facing tag tree used by cards in selected home decks."""

    selected = tuple(dict.fromkeys(value.strip() for value in source_decks if value.strip()))
    if not selected:
        return DeckTagScope(generation, (), (), 0)
    deck_ids = tuple(
        deck_id
        for deck_id, name in _normal_decks(collection)
        if any(name == root or name.startswith(root + "::") for root in selected)
    )
    if not deck_ids:
        return DeckTagScope(generation, selected, (), 0)
    placeholders = ",".join("?" for _value in deck_ids)
    rows = collection.db.all(
        "select c.id, n.tags from cards c join notes n on n.id = c.nid "
        f"where (case when c.odid != 0 then c.odid else c.did end) in ({placeholders})",
        *deck_ids,
    )
    metadata: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]],
        tuple[tuple[str, ...], str, tuple[str, ...], str, bool, tuple[str, ...]],
    ] = {}
    counts: dict[tuple[str, tuple[str, ...], tuple[str, ...]], int] = {}
    for _card_id, raw_tags in rows:
        per_card: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
        for raw_tag in str(raw_tags or "").split():
            segments = tuple(part for part in raw_tag.split("::") if part)
            for depth in range(1, len(segments) + 1):
                value = "::".join(segments[:depth])
                facet = catalog.find("topic", value) or catalog.find("tag", value)
                if facet is None:
                    path = segments[:depth]
                    values = (value,)
                    label = path[-1]
                    section = "All tags"
                    hidden = False
                    badges: tuple[str, ...] = ()
                else:
                    path = facet.path or segments[:depth]
                    values = facet.values
                    label = facet.label
                    section = facet.group or "All tags"
                    hidden = facet.hidden
                    badges = facet.scope_badges
                identity = (
                    section.casefold(),
                    tuple(part.casefold() for part in path),
                    tuple(item.casefold() for item in values),
                )
                per_card.add(identity)
                metadata.setdefault(
                    identity,
                    (values, label, path, section, hidden, badges),
                )
        for identity in per_card:
            counts[identity] = counts.get(identity, 0) + 1
    nodes = tuple(
        ScopedTagNode(values, label, path, section, counts[identity], hidden, badges)
        for identity, (values, label, path, section, hidden, badges) in sorted(
            metadata.items(),
            key=lambda item: (
                item[1][3].casefold(),
                tuple(part.casefold() for part in item[1][2]),
                item[1][0],
            ),
        )
    )
    return DeckTagScope(generation, selected, nodes, len(rows))


@dataclass(frozen=True)
class PreparedBuilderDeck:
    result: BuildResult
    cards: tuple[GeneratedDeckCard, ...]


def collection_key(collection: Any) -> str:
    """Return a non-reversible local namespace without exposing a profile name."""

    created = getattr(collection, "crt", None)
    if callable(created):
        created = created()
    path = getattr(collection, "path", "")
    if callable(path):
        path = path()
    raw = f"{created or 0}:{path or ''}".encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:24]


def collect_builder_catalog(
    collection: Any, topic_config: TopicParsingConfig
) -> BuilderCatalog:
    decks = tuple(
        str(deck.name)
        for deck in collection.decks.all_names_and_ids(
            skip_empty_default=False, include_filtered=False
        )
    )
    tags = tuple(str(tag) for tag in collection.tags.all())
    note_types = tuple(str(item.name) for item in collection.models.all_names_and_ids())
    card_types: set[str] = set()
    for notetype in collection.models.all():
        if not isinstance(notetype, dict):
            continue
        for template in notetype.get("tmpls", ()):
            if isinstance(template, dict) and str(template.get("name") or "").strip():
                card_types.add(str(template["name"]).strip())
    return build_catalog(
        deck_names=decks,
        tags=tags,
        note_types=note_types,
        card_types=card_types,
        topic_config=topic_config,
    )


def unresolved_filters(
    definition: BuilderDefinition, catalog: BuilderCatalog
) -> tuple[str, ...]:
    available = {
        "deck": {facet.value for facet in catalog.decks},
        "tag": {
            value
            for facet in (*catalog.tags, *catalog.topics, *catalog.anking)
            for value in facet.values
        },
        "note": {facet.value for facet in catalog.note_types},
        "card": {facet.value for facet in catalog.card_types},
        "state": {facet.value for facet in catalog.states},
    }
    missing: list[str] = []
    for value in definition.source_decks:
        if value not in available["deck"]:
            missing.append(f"deck: {value}")
    for value in definition.topic_tags:
        if value not in available["tag"]:
            missing.append(f"tag: {value}")
    for group in definition.filter_groups:
        for selector in group.selectors:
            if selector.kind == "flag":
                continue
            if selector.value not in available.get(selector.kind, set()):
                missing.append(f"{selector.kind}: {selector.value}")
    for kind, values in (
        ("deck", (*definition.decks, *definition.excluded_decks)),
        (
            "tag",
            (
                *definition.topics,
                *(value for group in definition.topic_groups for value in group),
                *definition.tags,
                *definition.excluded_tags,
            ),
        ),
        ("note", definition.note_types),
        ("card", definition.card_types),
        ("state", definition.states),
    ):
        for value in values:
            if value not in available[kind]:
                missing.append(f"{kind}: {value}")
    return tuple(missing)


def _ordered_find(collection: Any, query: str, definition: BuilderDefinition) -> tuple[int, ...]:
    order = ORDER_SQL[definition.order]
    if definition.order.value == "most_at_risk":
        today = int(collection.sched.today)
        order = (
            "case when c.type = 2 then "
            f"cast({today} - c.due as real) / max(c.ivl, 1) "
            "else 0 end desc, c.due asc, c.id asc"
        )
    elif definition.order.value == "oldest_seen":
        order = (
            "coalesce((select max(r.id) from revlog r where r.cid = c.id), 0) "
            "asc, c.id asc"
        )
    try:
        found = collection.find_cards(query, order=order)
    except Exception:
        if definition.order.value == "random":
            found = collection.find_cards(query)
        else:
            raise
    return tuple(int(card_id) for card_id in found)


def _clean_snippet(value: str, limit: int = 180) -> str:
    text = WHITESPACE.sub(" ", HTML.sub(" ", value)).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _preview_card(collection: Any, card_id: int, show_snippets: bool) -> PreviewCard:
    card = collection.get_card(card_id)
    note = card.note()
    notetype = note.note_type() if hasattr(note, "note_type") else None
    if not isinstance(notetype, dict):
        notetype = {}
    sort_index = int(notetype.get("sortf", 0) or 0)
    fields = tuple(str(value) for value in getattr(note, "fields", ()))
    raw_snippet = fields[sort_index] if fields and sort_index < len(fields) else ""
    template = card.template() if hasattr(card, "template") else None
    card_type = str(template.get("name") or "") if isinstance(template, dict) else ""
    deck_id_getter = getattr(card, "current_deck_id", None)
    deck_id = int(deck_id_getter() if callable(deck_id_getter) else getattr(card, "did", 0))
    try:
        deck_name = str(collection.decks.name(deck_id))
    except Exception:
        deck_name = ""
    queue = int(getattr(card, "queue", getattr(card, "type", 0)))
    return PreviewCard(
        card_id=int(card_id),
        note_id=int(getattr(card, "nid", getattr(note, "id", 0)) or 0),
        snippet=_clean_snippet(raw_snippet) if show_snippets else "",
        deck_name=deck_name,
        note_type=str(notetype.get("name") or ""),
        card_type=card_type,
        state=STATE_BY_QUEUE.get(queue, "Other"),
        tags=tuple(str(tag) for tag in getattr(note, "tags", ()) if str(tag).strip()),
        suspended=queue == -1,
    )


def _unique_note_candidates(
    collection: Any, card_ids: tuple[int, ...]
) -> tuple[int, ...]:
    if not card_ids:
        return ()
    note_by_card: dict[int, int] = {}
    for start in range(0, len(card_ids), 500):
        chunk = card_ids[start : start + 500]
        placeholders = ",".join("?" for _value in chunk)
        for card_id, note_id in collection.db.all(
            f"select id, nid from cards where id in ({placeholders})", *chunk
        ):
            note_by_card[int(card_id)] = int(note_id)
    seen_notes: set[int] = set()
    selected: list[int] = []
    for card_id in card_ids:
        note_id = note_by_card.get(card_id, card_id)
        if note_id in seen_notes:
            continue
        seen_notes.add(note_id)
        selected.append(card_id)
    return tuple(selected)


def _apply_selection_policy(
    collection: Any,
    definition: BuilderDefinition,
    query: str,
    selectable: tuple[int, ...],
) -> tuple[int, ...]:
    candidates = selectable
    if definition.selection_policy.one_card_per_note:
        candidates = _unique_note_candidates(collection, candidates)
    share = definition.selection_policy.new_share_percent
    if share is None or definition.state_preset is not StatePreset.DUE_NEW:
        return candidates[: definition.limit]
    new_ids = {
        int(card_id)
        for card_id in collection.find_cards(f"({query}) is:new" if query else "is:new")
    }
    new_candidates = tuple(card_id for card_id in candidates if card_id in new_ids)
    due_candidates = tuple(card_id for card_id in candidates if card_id not in new_ids)
    new_target = (definition.limit * share + 50) // 100
    due_target = definition.limit - new_target
    chosen = set(new_candidates[:new_target])
    chosen.update(due_candidates[:due_target])
    for card_id in candidates:
        if len(chosen) >= definition.limit:
            break
        chosen.add(card_id)
    return tuple(card_id for card_id in candidates if card_id in chosen)[: definition.limit]


def _diagnose_builder(
    collection: Any,
    definition: BuilderDefinition,
    *,
    total_count: int,
    ready_count: int,
    suspended_count: int,
    buried_count: int,
    filtered_count: int,
    catalog: BuilderCatalog | None = None,
) -> BuilderDiagnostic | None:
    if total_count and not ready_count:
        if suspended_count:
            return BuilderDiagnostic(
                f"{total_count:,} cards match, but {suspended_count:,} are suspended. "
                "They remain excluded unless you explicitly include and activate them."
            )
        if buried_count:
            return BuilderDiagnostic(
                f"{total_count:,} cards match, but {buried_count:,} are buried and cannot enter a filtered deck."
            )
        if filtered_count:
            return BuilderDiagnostic(
                f"{total_count:,} cards match, but {filtered_count:,} are already in another filtered deck."
            )
    if total_count:
        return None

    def ready_after(draft: BuilderDefinition) -> int:
        query = compile_builder_query(draft)
        return len(collection.find_cards(availability_query(query, "ready")))

    # Older definitions and the original Builder UI could store alternative
    # resource choices as separate singleton AND groups. Diagnose that exact
    # shape before suggesting destructive rule removal. The query is only
    # changed after the user accepts the offered repair.
    if catalog is not None:
        resource_groups: list[BuilderFilterGroup] = []
        for group in definition.filter_groups:
            if len(group.selectors) != 1 or group.selectors[0].kind != "tag":
                continue
            selector = group.selectors[0]
            facet = catalog.find("topic", selector.value) or catalog.find(
                "tag", selector.value
            )
            if facet is not None and facet.group == "Resources":
                resource_groups.append(group)
        if len(resource_groups) >= 2:
            merge_ids = tuple(group.group_id for group in resource_groups)
            merged_selectors = tuple(
                dict.fromkeys(group.selectors[0] for group in resource_groups)
            )
            merged = BuilderFilterGroup(
                group_id="diagnostic:resources",
                operator=FilterOperator.ANY,
                selectors=merged_selectors,
            )
            draft = replace(
                definition,
                filter_groups=(
                    *(
                        group
                        for group in definition.filter_groups
                        if group.group_id not in merge_ids
                    ),
                    merged,
                ),
            )
            count = ready_after(draft)
            if count:
                return BuilderDiagnostic(
                    "No card has all of these resource tags. Match them as "
                    f"alternatives instead to show {count:,} ready cards.",
                    action_label="Match as alternatives",
                    merge_group_ids=merge_ids,
                )

    for group in reversed(definition.filter_groups):
        draft = replace(
            definition,
            filter_groups=tuple(
                candidate
                for candidate in definition.filter_groups
                if candidate.group_id != group.group_id
            ),
        )
        count = ready_after(draft)
        if count:
            label = " OR ".join(
                selector.value.split("::")[-1] for selector in group.selectors
            )
            return BuilderDiagnostic(
                f"No cards match every rule. Removing {label} would show {count:,} ready cards.",
                action_label=f"Remove {label}",
                remove_group_id=group.group_id,
            )

    quick = definition.quick_filters
    for key, value in (
        ("recent_again_days", quick.recent_again_days),
        ("added_days", quick.added_days),
        ("reviewed_days", quick.reviewed_days),
        ("marked", quick.marked),
        ("leech", quick.leech),
        ("maturity", quick.maturity.value != "any"),
    ):
        if not value:
            continue
        replacement = None if key.endswith("_days") else False
        if key == "maturity":
            replacement = CardMaturity.ANY
        draft = replace(definition, quick_filters=replace(quick, **{key: replacement}))
        count = ready_after(draft)
        if count:
            label = key.replace("_days", "").replace("_", " ").title()
            return BuilderDiagnostic(
                f"No cards match every rule. Clearing {label} would show {count:,} ready cards.",
                action_label=f"Clear {label}",
                clear_quick_filter=key,
            )
    if definition.state_preset is not StatePreset.ALL:
        count = ready_after(replace(definition, state_preset=StatePreset.ALL))
        if count:
            return BuilderDiagnostic(
                f"No cards match this card-state choice. Using All would show {count:,} ready cards.",
                action_label="Use All cards",
                clear_state_preset=True,
            )
    return BuilderDiagnostic("No cards currently match this combination.")


def collect_builder_preview(
    collection: Any,
    definition: BuilderDefinition,
    *,
    generation: int = 0,
    show_snippets: bool = True,
    snippet_limit: int = 40,
    catalog: BuilderCatalog | None = None,
) -> BuilderPreview:
    """Evaluate one immutable definition entirely on Anki's collection worker."""

    query = compile_builder_query(definition)
    total_ids = _ordered_find(collection, query, definition)
    ready_ids = tuple(
        int(card_id)
        for card_id in collection.find_cards(availability_query(query, "ready"))
    )
    suspended_ids = tuple(
        int(card_id)
        for card_id in collection.find_cards(availability_query(query, "suspended"))
    )
    buried_ids = tuple(
        int(card_id)
        for card_id in collection.find_cards(availability_query(query, "buried"))
    )
    filtered_ids = tuple(
        int(card_id)
        for card_id in collection.find_cards(availability_query(query, "filtered"))
    )
    # Ready and suspended are already mutually exclusive, unburied, and outside
    # filtered decks. Reuse those results instead of asking Anki to execute the
    # same base query a sixth time merely to form the selectable set.
    selectable_set = set(ready_ids)
    if definition.include_suspended:
        selectable_set.update(suspended_ids)
    selectable = tuple(card_id for card_id in total_ids if card_id in selectable_set)
    selected = _apply_selection_policy(collection, definition, query, selectable)
    suspended_set = set(suspended_ids)
    selected_suspended = tuple(card_id for card_id in selected if card_id in suspended_set)
    cards = tuple(
        _preview_card(collection, card_id, show_snippets)
        for card_id in total_ids[: max(0, int(snippet_limit))]
    )
    diagnostic = _diagnose_builder(
        collection,
        definition,
        total_count=len(total_ids),
        ready_count=len(ready_ids),
        suspended_count=len(suspended_ids),
        buried_count=len(buried_ids),
        filtered_count=len(filtered_ids),
        catalog=catalog,
    )
    return BuilderPreview(
        generation=generation,
        compiled_query=query,
        total_count=len(total_ids),
        ready_count=len(ready_ids),
        suspended_count=len(suspended_ids),
        buried_count=len(buried_ids),
        filtered_count=len(filtered_ids),
        selected_card_ids=selected,
        selected_suspended_ids=selected_suspended,
        suspended_card_ids=suspended_ids,
        cards=cards,
        unresolved_filters=(unresolved_filters(definition, catalog) if catalog else ()),
        diagnostic=diagnostic,
    )


def exact_selection_is_current(
    collection: Any,
    definition: BuilderDefinition,
    card_ids: Iterable[int],
) -> bool:
    """Confirm every inspected ID still matches and is eligible for this run."""

    selected = tuple(dict.fromkeys(int(card_id) for card_id in card_ids))
    if not selected:
        return False
    base = compile_builder_query(definition)
    exact = "cid:" + ",".join(str(card_id) for card_id in selected)
    query = f"({base}) {exact}" if base else exact
    current = collection.find_cards(
        availability_query(
            query,
            "selectable",
            include_suspended=definition.include_suspended,
        )
    )
    return set(int(card_id) for card_id in current) == set(selected)


def unique_builder_deck_name(collection: Any, requested: str) -> str:
    candidate = requested.strip() or "Vellum Study Builder"
    if collection.decks.id_for_name(candidate) is None:
        return candidate
    suffix = 2
    while collection.decks.id_for_name(f"{candidate} ({suffix})") is not None:
        suffix += 1
    return f"{candidate} ({suffix})"


def create_builder_deck(
    collection: Any,
    request: BuildRequest,
    card_ids: Iterable[int],
) -> PreparedBuilderDeck:
    selected = tuple(dict.fromkeys(int(card_id) for card_id in card_ids))
    if not selected:
        raise ValueError("No eligible cards remain for this Study Builder run")

    from anki.decks import FilteredDeckConfig  # type: ignore[import-not-found]

    name = unique_builder_deck_name(collection, request.deck_name)
    deck = collection.sched.get_or_create_filtered_deck(0)
    deck.name = name
    deck.config.reschedule = True
    del deck.config.search_terms[:]
    deck.config.search_terms.append(
        FilteredDeckConfig.SearchTerm(
            search="cid:" + ",".join(str(card_id) for card_id in selected),
            limit=len(selected),
            order=FILTERED_DECK_ORDER[request.definition.order],
        )
    )
    deck_id = 0
    try:
        operation = collection.sched.add_or_update_filtered_deck(deck)
        deck_id = int(operation.id)
        rebuilt = collection.sched.rebuild_filtered_deck(deck_id)
        if int(rebuilt.count) != len(selected):
            raise RuntimeError(
                "Card availability changed while the Study Builder deck was created"
            )
        actual_ids = tuple(
            int(row[0])
            for row in collection.db.all(
                "select id from cards where did = ? order by due, id", deck_id
            )
        )
        if set(actual_ids) != set(selected):
            raise RuntimeError("The Study Builder deck did not contain the exact selection")
        cards = collect_generated_deck_cards(collection, deck_id, actual_ids)
        if len(cards) != len(selected):
            raise RuntimeError("Unable to capture the complete Study Builder manifest")
    except Exception:
        if (
            deck_id
            and bool(collection.decks.is_filtered(deck_id))
            and collection.decks.name_if_exists(deck_id) == name
        ):
            collection.decks.remove([deck_id])
        raise
    return PreparedBuilderDeck(
        result=BuildResult(
            deck_id=deck_id,
            deck_name=name,
            card_ids=actual_ids,
            recipe_id=request.recipe_id,
        ),
        cards=cards,
    )


def rollback_builder_start(
    collection: Any,
    *,
    deck_id: int | None,
    deck_name: str | None,
    activated_card_ids: Iterable[int],
) -> None:
    if (
        deck_id
        and deck_name
        and bool(collection.decks.is_filtered(deck_id))
        and collection.decks.name_if_exists(deck_id) == deck_name
    ):
        collection.decks.remove([deck_id])
    activated = tuple(dict.fromkeys(int(card_id) for card_id in activated_card_ids))
    if activated:
        collection.sched.suspend_cards(activated)


def owned_builder_deck_is_empty(
    collection: Any, deck_id: int, deck_name: str
) -> bool:
    return bool(collection.decks.is_filtered(deck_id)) and (
        collection.decks.name_if_exists(deck_id) == deck_name
        and not bool(
            collection.find_cards('deck:"' + deck_name.replace('"', '\\"') + '"')
        )
    )
