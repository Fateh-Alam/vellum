"""Pure typed contracts for Vellum Study Builder."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from typing import Any, Mapping


MAX_BUILDER_LIMIT = 2_147_483_647


class StatePreset(str, Enum):
    DUE_NEW = "due_new"
    DUE = "due"
    NEW = "new"
    RECENT_FAILURES = "recent_failures"
    ALL = "all"


class BuilderOrder(str, Enum):
    DUE = "due"
    MOST_AT_RISK = "most_at_risk"
    MOST_LAPSES = "most_lapses"
    OLDEST_SEEN = "oldest_seen"
    ADDED = "added"
    RANDOM = "random"


class FilterOperator(str, Enum):
    ALL = "all"
    ANY = "any"


class CardMaturity(str, Enum):
    ANY = "any"
    YOUNG = "young"
    MATURE = "mature"


class BuilderWorkflow(str, Enum):
    FIND_TOPICS = "find_topics"
    BROWSE_COLLECTION = "browse_collection"


VALID_SELECTOR_KINDS = {"deck", "tag", "note", "card", "state", "flag"}


@dataclass(frozen=True)
class BuilderSelector:
    """One unresolved-safe filter value inside a visible rule group."""

    kind: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in VALID_SELECTOR_KINDS:
            raise ValueError(f"Unsupported Study Builder selector: {self.kind}")
        if not self.value.strip():
            raise ValueError("Study Builder selectors cannot be empty")


@dataclass(frozen=True)
class BuilderFilterGroup:
    """Selectors evaluated together; groups are always ANDed at the top level."""

    group_id: str
    operator: FilterOperator = FilterOperator.ALL
    selectors: tuple[BuilderSelector, ...] = ()

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            raise ValueError("Study Builder filter groups require a stable ID")
        if not self.selectors:
            raise ValueError("Study Builder filter groups cannot be empty")
        if self.operator is FilterOperator.ANY and len(
            {selector.kind for selector in self.selectors}
        ) > 1:
            raise ValueError("Match any groups must contain compatible selectors")


@dataclass(frozen=True)
class BuilderQuickFilters:
    recent_again_days: int | None = None
    added_days: int | None = None
    reviewed_days: int | None = None
    marked: bool = False
    leech: bool = False
    maturity: CardMaturity = CardMaturity.ANY

    def __post_init__(self) -> None:
        for value in (
            self.recent_again_days,
            self.added_days,
            self.reviewed_days,
        ):
            if value is not None and not 1 <= value <= 3650:
                raise ValueError("Study Builder activity windows must be 1-3650 days")


@dataclass(frozen=True)
class BuilderSelectionPolicy:
    one_card_per_note: bool = False
    new_share_percent: int | None = None

    def __post_init__(self) -> None:
        if self.new_share_percent is not None and not 0 <= self.new_share_percent <= 100:
            raise ValueError("Study Builder new-card share must be 0-100 percent")


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    )


def _string_groups(value: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(group for item in value if (group := _strings(item)))


@dataclass(frozen=True)
class BuilderDefinition:
    """A dynamic, collection-independent set of Study Builder rules."""

    definition_version: int = 3
    workflow: BuilderWorkflow = BuilderWorkflow.FIND_TOPICS
    topic_tags: tuple[str, ...] = ()
    source_decks: tuple[str, ...] = ()
    include_entire_deck_scope: bool = False
    text_query: str = ""
    advanced_query: str = ""
    filter_groups: tuple[BuilderFilterGroup, ...] = ()
    quick_filters: BuilderQuickFilters = field(default_factory=BuilderQuickFilters)
    selection_policy: BuilderSelectionPolicy = field(
        default_factory=BuilderSelectionPolicy
    )
    decks: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    topic_groups: tuple[tuple[str, ...], ...] = ()
    tags: tuple[str, ...] = ()
    excluded_decks: tuple[str, ...] = ()
    excluded_tags: tuple[str, ...] = ()
    note_types: tuple[str, ...] = ()
    card_types: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    flags: tuple[int, ...] = ()
    state_preset: StatePreset = StatePreset.DUE_NEW
    order: BuilderOrder = BuilderOrder.DUE
    limit: int = 100
    include_suspended: bool = False

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > MAX_BUILDER_LIMIT:
            raise ValueError("Study Builder limit is outside Anki's supported range")
        if any(flag < 0 or flag > 7 for flag in self.flags):
            raise ValueError("Study Builder flags must be between 0 and 7")

    def to_mapping(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["workflow"] = self.workflow.value
        raw["state_preset"] = self.state_preset.value
        raw["order"] = self.order.value
        for key in (
            "topic_tags",
            "source_decks",
            "decks",
            "topics",
            "tags",
            "excluded_decks",
            "excluded_tags",
            "note_types",
            "card_types",
            "states",
            "flags",
        ):
            raw[key] = list(raw[key])
        raw["topic_groups"] = [list(group) for group in self.topic_groups]
        raw["filter_groups"] = [
            {
                "group_id": group.group_id,
                "operator": group.operator.value,
                "selectors": [asdict(selector) for selector in group.selectors],
            }
            for group in self.filter_groups
        ]
        raw["quick_filters"]["maturity"] = self.quick_filters.maturity.value
        return raw

    def to_json(self) -> str:
        return json.dumps(self.to_mapping(), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "BuilderDefinition":
        raw = raw or {}
        try:
            state = StatePreset(str(raw.get("state_preset") or StatePreset.DUE_NEW.value))
        except ValueError:
            state = StatePreset.DUE_NEW
        try:
            order = BuilderOrder(str(raw.get("order") or BuilderOrder.DUE.value))
        except ValueError:
            order = BuilderOrder.DUE
        try:
            workflow = BuilderWorkflow(
                str(raw.get("workflow") or BuilderWorkflow.FIND_TOPICS.value)
            )
        except ValueError:
            workflow = BuilderWorkflow.FIND_TOPICS
        limit = raw.get("limit", 100)
        if isinstance(limit, bool) or not isinstance(limit, (int, float)):
            limit = 100
        flags_raw = raw.get("flags")
        flags = tuple(
            int(flag)
            for flag in flags_raw
            if isinstance(flag, (int, float)) and not isinstance(flag, bool)
        ) if isinstance(flags_raw, (list, tuple)) else ()
        groups: list[BuilderFilterGroup] = []
        groups_raw = raw.get("filter_groups")
        if isinstance(groups_raw, (list, tuple)):
            for index, group_raw in enumerate(groups_raw):
                if not isinstance(group_raw, Mapping):
                    continue
                selectors: list[BuilderSelector] = []
                selector_rows = group_raw.get("selectors")
                if isinstance(selector_rows, (list, tuple)):
                    for selector_raw in selector_rows:
                        if not isinstance(selector_raw, Mapping):
                            continue
                        kind = str(selector_raw.get("kind") or "").strip()
                        value = str(selector_raw.get("value") or "").strip()
                        if kind in VALID_SELECTOR_KINDS and value:
                            selectors.append(BuilderSelector(kind, value))
                if not selectors:
                    continue
                try:
                    operator = FilterOperator(
                        str(group_raw.get("operator") or FilterOperator.ALL.value)
                    )
                except ValueError:
                    operator = FilterOperator.ALL
                group_id = str(group_raw.get("group_id") or f"group:{index}").strip()
                try:
                    groups.append(
                        BuilderFilterGroup(group_id, operator, tuple(selectors))
                    )
                except ValueError:
                    continue

        quick_raw = raw.get("quick_filters")
        quick_raw = quick_raw if isinstance(quick_raw, Mapping) else {}
        try:
            maturity = CardMaturity(
                str(quick_raw.get("maturity") or CardMaturity.ANY.value)
            )
        except ValueError:
            maturity = CardMaturity.ANY

        def activity_days(key: str) -> int | None:
            value = quick_raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            return max(1, min(3650, int(value)))

        quick_filters = BuilderQuickFilters(
            recent_again_days=activity_days("recent_again_days"),
            added_days=activity_days("added_days"),
            reviewed_days=activity_days("reviewed_days"),
            marked=bool(quick_raw.get("marked", False)),
            leech=bool(quick_raw.get("leech", False)),
            maturity=maturity,
        )
        selection_raw = raw.get("selection_policy")
        selection_raw = selection_raw if isinstance(selection_raw, Mapping) else {}
        share = selection_raw.get("new_share_percent")
        if isinstance(share, bool) or not isinstance(share, (int, float)):
            share = None
        else:
            share = max(0, min(100, int(share)))
        version = raw.get("definition_version", 1)
        if isinstance(version, bool) or not isinstance(version, (int, float)):
            version = 1
        if int(version) < 2 and state is StatePreset.RECENT_FAILURES:
            state = StatePreset.ALL
            if quick_filters.recent_again_days is None:
                quick_filters = BuilderQuickFilters(
                    recent_again_days=7,
                    added_days=quick_filters.added_days,
                    reviewed_days=quick_filters.reviewed_days,
                    marked=quick_filters.marked,
                    leech=quick_filters.leech,
                    maturity=quick_filters.maturity,
                )
        migrated = int(version) < 2 and not groups
        if migrated:
            legacy_rows: tuple[tuple[str, str, tuple[str, ...]], ...] = (
                ("legacy:decks", "deck", _strings(raw.get("decks"))),
                ("legacy:topics", "tag", _strings(raw.get("topics"))),
                ("legacy:tags", "tag", _strings(raw.get("tags"))),
                ("legacy:notes", "note", _strings(raw.get("note_types"))),
                ("legacy:cards", "card", _strings(raw.get("card_types"))),
                ("legacy:states", "state", _strings(raw.get("states"))),
                ("legacy:flags", "flag", tuple(str(flag) for flag in flags)),
            )
            for group_id, kind, values in legacy_rows:
                if values:
                    groups.append(
                        BuilderFilterGroup(
                            group_id,
                            FilterOperator.ANY,
                            tuple(BuilderSelector(kind, value) for value in values),
                        )
                    )
            for index, values in enumerate(_string_groups(raw.get("topic_groups"))):
                groups.append(
                    BuilderFilterGroup(
                        f"legacy:topic_group:{index}",
                        FilterOperator.ANY,
                        tuple(BuilderSelector("tag", value) for value in values),
                    )
                )
        parsed_version = 2 if migrated else max(1, int(version))
        topic_tags = _strings(raw.get("topic_tags")) if parsed_version >= 3 else ()
        source_decks = _strings(raw.get("source_decks")) if parsed_version >= 3 else ()
        include_entire_deck_scope = bool(
            raw.get("include_entire_deck_scope", False)
        ) if parsed_version >= 3 else False

        # Version 2 combinations with one OR tag group and one OR deck group
        # map losslessly to the guided two-path model. Any more expressive
        # legacy recipe keeps its exact groups and opens in the secondary
        # legacy editor instead of being silently regrouped.
        if parsed_version == 2 and groups and not any(
            (
                str(raw.get("text_query") or "").strip(),
                str(raw.get("advanced_query") or "").strip(),
                _strings(raw.get("decks")),
                _strings(raw.get("topics")),
                _string_groups(raw.get("topic_groups")),
                _strings(raw.get("tags")),
                _strings(raw.get("note_types")),
                _strings(raw.get("card_types")),
                _strings(raw.get("states")),
                flags,
            )
        ):
            tag_groups = tuple(
                group
                for group in groups
                if group.operator is FilterOperator.ANY
                and {selector.kind for selector in group.selectors} == {"tag"}
            )
            deck_groups = tuple(
                group
                for group in groups
                if group.operator is FilterOperator.ANY
                and {selector.kind for selector in group.selectors} == {"deck"}
            )
            recognized = (*tag_groups, *deck_groups)
            if (
                len(tag_groups) <= 1
                and len(deck_groups) == 1
                and len(recognized) == len(groups)
            ):
                topic_tags = tuple(
                    selector.value
                    for group in tag_groups
                    for selector in group.selectors
                )
                source_decks = tuple(
                    selector.value
                    for selector in deck_groups[0].selectors
                )
                workflow = (
                    BuilderWorkflow.FIND_TOPICS
                    if topic_tags
                    else BuilderWorkflow.BROWSE_COLLECTION
                )
                include_entire_deck_scope = not topic_tags
                groups = []
                parsed_version = 3

        return cls(
            definition_version=parsed_version,
            workflow=workflow,
            topic_tags=topic_tags,
            source_decks=source_decks,
            include_entire_deck_scope=include_entire_deck_scope,
            text_query=str(raw.get("text_query") or "").strip(),
            advanced_query=str(raw.get("advanced_query") or "").strip(),
            filter_groups=tuple(groups),
            quick_filters=quick_filters,
            selection_policy=BuilderSelectionPolicy(
                one_card_per_note=bool(selection_raw.get("one_card_per_note", False)),
                new_share_percent=share,
            ),
            decks=() if migrated else _strings(raw.get("decks")),
            topics=() if migrated else _strings(raw.get("topics")),
            topic_groups=() if migrated else _string_groups(raw.get("topic_groups")),
            tags=() if migrated else _strings(raw.get("tags")),
            excluded_decks=_strings(raw.get("excluded_decks")),
            excluded_tags=_strings(raw.get("excluded_tags")),
            note_types=() if migrated else _strings(raw.get("note_types")),
            card_types=() if migrated else _strings(raw.get("card_types")),
            states=() if migrated else _strings(raw.get("states")),
            flags=() if migrated else flags,
            state_preset=state,
            order=order,
            limit=max(1, min(MAX_BUILDER_LIMIT, int(limit))),
            include_suspended=bool(raw.get("include_suspended", False)),
        )

    @classmethod
    def from_json(cls, value: str) -> "BuilderDefinition":
        try:
            raw = json.loads(value)
        except (TypeError, ValueError):
            raw = {}
        return cls.from_mapping(raw if isinstance(raw, Mapping) else {})

    @property
    def empty_scope(self) -> bool:
        return not any(
            (
                self.text_query,
                self.advanced_query,
                self.topic_tags,
                self.source_decks,
                self.filter_groups,
                self.decks,
                self.topics,
                self.topic_groups,
                self.tags,
                self.excluded_decks,
                self.excluded_tags,
                self.note_types,
                self.card_types,
                self.states,
                self.flags,
                self.quick_filters != BuilderQuickFilters(),
            )
        )


@dataclass(frozen=True)
class BuilderDiagnostic:
    message: str
    action_label: str = ""
    remove_group_id: str | None = None
    merge_group_ids: tuple[str, ...] = ()
    clear_quick_filter: str | None = None
    clear_state_preset: bool = False


@dataclass(frozen=True)
class PreviewCard:
    card_id: int
    note_id: int
    snippet: str
    deck_name: str
    note_type: str
    card_type: str
    state: str
    tags: tuple[str, ...] = ()
    suspended: bool = False


@dataclass(frozen=True)
class BuilderPreview:
    generation: int
    compiled_query: str
    total_count: int
    ready_count: int
    suspended_count: int
    buried_count: int
    filtered_count: int
    selected_card_ids: tuple[int, ...]
    selected_suspended_ids: tuple[int, ...]
    suspended_card_ids: tuple[int, ...] = ()
    cards: tuple[PreviewCard, ...] = ()
    unresolved_filters: tuple[str, ...] = ()
    diagnostic: BuilderDiagnostic | None = None

    @property
    def selected_count(self) -> int:
        return len(self.selected_card_ids)


@dataclass(frozen=True)
class StudyRecipe:
    recipe_id: str
    collection_key: str
    name: str
    definition: BuilderDefinition
    created_at: int
    updated_at: int
    last_run_at: int | None = None


@dataclass(frozen=True)
class BuildRequest:
    definition: BuilderDefinition
    deck_name: str
    recipe_id: str | None = None
    generation: int = 0
    selected_card_ids: tuple[int, ...] = ()
    activate_suspended: bool = False


@dataclass(frozen=True)
class BuildResult:
    deck_id: int
    deck_name: str
    card_ids: tuple[int, ...]
    activated_card_ids: tuple[int, ...] = ()
    recipe_id: str | None = None
    cleanup_state: str = "owned"


@dataclass(frozen=True)
class RecentBuilderRun:
    run_id: str
    collection_key: str
    definition: BuilderDefinition
    recipe_id: str | None
    created_at: int
    metadata: Mapping[str, Any] = field(default_factory=dict)
