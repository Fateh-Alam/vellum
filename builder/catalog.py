"""Collection catalog and version-tolerant AnKing facet discovery."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import difflib
import heapq
import re
from typing import Iterable, Mapping

from ..core.config import TopicParsingConfig
from ..topics.normalization import display_segment, split_hierarchical_tag
from ..topics.normalization import canonical_segment, source_key
from ..topics.parser import TopicParser


ANKING_CONTAINER = re.compile(
    r"^#?AK_(?P<exam>Step[123]|MCAT|PANCE|Other).*?(?:_v(?P<version>\d+))?$",
    re.IGNORECASE,
)
UTILITY = re.compile(
    r"^(?:!DELETE|!FLAG|\$AnKing|\$AnkiHub|AnkiHub_Deleted|Potential_duplicates)",
    re.IGNORECASE,
)

SEARCH_ALIASES: Mapping[str, tuple[str, ...]] = {
    "fa": ("first", "aid"),
    "firstaid": ("first", "aid"),
    "bnb": ("b", "b"),
    "boards beyond": ("b", "b"),
    "boards and beyond": ("b", "b"),
}


@dataclass(frozen=True)
class CatalogFacet:
    kind: str
    value: str
    label: str
    path: tuple[str, ...] = ()
    group: str = ""
    hidden: bool = False
    selector_values: tuple[str, ...] = ()
    selector_badges: tuple[str, ...] = ()

    @property
    def values(self) -> tuple[str, ...]:
        """Exact collection selectors represented by this visible choice."""

        return self.selector_values or (self.value,)

    @property
    def scope_badges(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(badge for badge in self.selector_badges if badge))

    def badge_for(self, value: str) -> str:
        try:
            index = self.values.index(value)
        except ValueError:
            return ""
        return self.selector_badges[index] if index < len(self.selector_badges) else ""


def _search_words(value: str) -> tuple[str, ...]:
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    normalized = "".join(
        character.casefold() if character.isalnum() else " "
        for character in spaced
    )
    return tuple(part for part in normalized.split() if part)


def _single_edit_typo(left: str, right: str) -> bool:
    """Cheap bounded typo check used only after exact/prefix lookup misses."""

    if left == right:
        return True
    if len(left) == len(right):
        differences = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]]
        if len(differences) == 1:
            return True
        return (
            len(differences) == 2
            and differences[1] == differences[0] + 1
            and left[differences[0]] == right[differences[1]]
            and left[differences[1]] == right[differences[0]]
        )
    if abs(len(left) - len(right)) != 1:
        return False
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    index = 0
    while index < len(shorter) and shorter[index] == longer[index]:
        index += 1
    return shorter[index:] == longer[index + 1 :]


@dataclass(frozen=True)
class _IndexedFacet:
    facet: CatalogFacet
    label: str
    last: str
    path: str
    words: tuple[str, ...]
    value_words: tuple[str, ...]


class CatalogSearchIndex:
    """Precomputed prefix index; keystrokes never scan the full tag catalog."""

    def __init__(
        self,
        searchable: Iterable[CatalogFacet],
        all_facets: Iterable[CatalogFacet],
    ) -> None:
        lookup: dict[tuple[str, str], CatalogFacet] = {}
        for facet in all_facets:
            for value in facet.values:
                # Structured/composite facets are ordered before raw tags. Keep
                # the human-facing representation for every exact backing value.
                lookup.setdefault((facet.kind, value), facet)
        self.lookup = lookup
        entries: list[_IndexedFacet] = []
        postings: dict[str, list[int]] = {}
        strong_postings: dict[str, list[int]] = {}
        exact_phrases: dict[str, list[int]] = {}
        word_cache: dict[str, tuple[str, ...]] = {}

        def words_for(value: str) -> tuple[str, ...]:
            cached = word_cache.get(value)
            if cached is None:
                cached = _search_words(value)
                word_cache[value] = cached
            return cached

        for facet in searchable:
            label_words = words_for(facet.label)
            path_words = words_for(" ".join(facet.path))
            group_words = words_for(facet.group)
            value_words = words_for(" ".join(facet.values))
            words = tuple(dict.fromkeys((*label_words, *path_words, *group_words, *value_words)))
            last_words = words_for(facet.path[-1] if facet.path else facet.label)
            entry_id = len(entries)
            entries.append(
                _IndexedFacet(
                    facet=facet,
                    label=" ".join(label_words),
                    last=" ".join(last_words),
                    path=" ".join(path_words),
                    words=words,
                    value_words=value_words,
                )
            )
            for phrase in {
                " ".join(label_words),
                " ".join(path_words),
                " ".join(last_words),
            }:
                if phrase:
                    exact_phrases.setdefault(phrase, []).append(entry_id)
            prefixes: set[str] = set()
            for word in words:
                for length in range(1, min(len(word), 24) + 1):
                    prefixes.add(word[:length])
            for prefix in prefixes:
                postings.setdefault(prefix, []).append(entry_id)
            strong_prefixes: set[str] = set()
            for word in dict.fromkeys((*label_words, *last_words)):
                for length in range(1, min(len(word), 24) + 1):
                    strong_prefixes.add(word[:length])
            for prefix in strong_prefixes:
                strong_postings.setdefault(prefix, []).append(entry_id)
        self._entries = tuple(entries)
        self._postings = {key: tuple(values) for key, values in postings.items()}
        self._strong_postings = {
            key: tuple(values) for key, values in strong_postings.items()
        }
        self._exact_phrases = {
            key: tuple(values) for key, values in exact_phrases.items()
        }
        vocabulary = tuple(postings)
        buckets: dict[str, list[str]] = {}
        for word in vocabulary:
            if len(word) >= 4:
                buckets.setdefault(word[:2], []).append(word)
        self._fuzzy_buckets = {key: tuple(values) for key, values in buckets.items()}

    @staticmethod
    def _group_rank(facet: CatalogFacet) -> int:
        return {
            "Resources": 0,
            "Systems": 1,
            "Yield": 2,
            "Step relevance": 3,
            "Topics": 4,
            "Decks": 5,
            "Note types": 6,
            "Card types": 7,
            "Card states": 8,
            "Flags": 9,
            "All tags": 10,
        }.get(facet.group, 5)

    def search(
        self,
        text: str,
        *,
        limit: int = 8,
        exclude_only: bool = False,
        allowed_kinds: frozenset[str] | None = None,
    ) -> tuple[CatalogFacet, ...]:
        raw_words = _search_words(text)
        phrase_key = " ".join(raw_words)
        phrase_alias = SEARCH_ALIASES.get(phrase_key)
        if phrase_alias is not None:
            query_words = phrase_alias
        else:
            expanded: list[str] = []
            for word in raw_words:
                expanded.extend(SEARCH_ALIASES.get(word, (word,)))
            query_words = tuple(expanded)
        if not query_words:
            return ()
        corrected: list[str] = []
        for word in query_words:
            if word in self._postings:
                corrected.append(word)
                continue
            if len(word) < 4:
                return ()
            candidates = self._fuzzy_buckets.get(word[:2], ())
            direct = next((candidate for candidate in candidates if _single_edit_typo(word, candidate)), None)
            close = (
                [direct]
                if direct is not None
                else difflib.get_close_matches(word, candidates, n=1, cutoff=0.84)
            )
            if not close:
                return ()
            corrected.append(close[0])
        query_words = tuple(corrected)
        phrase = " ".join(query_words)
        exact = self._exact_phrases.get(phrase)
        candidates = set(exact or ())
        strong_lists = [
            self._strong_postings[word]
            for word in dict.fromkeys(query_words)
            if word in self._strong_postings
        ]
        if len(strong_lists) == len(set(query_words)):
            strong_lists.sort(key=len)
            strong_candidates = set(strong_lists[0])
            for values in strong_lists[1:]:
                strong_candidates.intersection_update(values)
            # Exact matches rank first, but must not hide equally useful prefix
            # matches such as "Cardiovascular Pharm".
            candidates.update(strong_candidates)
        if candidates:
            posting_lists: list[tuple[int, ...]] = []
        else:
            posting_lists = []
            for word in dict.fromkeys(query_words):
                values = self._postings.get(word)
                if not values:
                    return ()
                posting_lists.append(values)
            posting_lists.sort(key=len)
            candidates = set(posting_lists[0])
            for values in posting_lists[1:]:
                candidates.intersection_update(values)
                if not candidates:
                    return ()
        scored: list[tuple[tuple[int, int, int, str, str], CatalogFacet]] = []
        strongest = 99
        for entry_id in candidates:
            entry = self._entries[entry_id]
            facet = entry.facet
            if allowed_kinds is not None and facet.kind not in allowed_kinds:
                continue
            if exclude_only and facet.kind not in {"topic", "tag", "deck"}:
                continue
            if facet.hidden and not all(word in entry.value_words for word in query_words):
                continue
            if entry.label == phrase or entry.last == phrase:
                # A deeply nested exact leaf is less likely to be the user's
                # intended broad topic than a concise resource prefix match.
                primary = 0 if len(facet.path) <= 5 else 1
            elif (
                entry.label.startswith(phrase)
                or entry.last.startswith(phrase)
                or entry.path.endswith(phrase)
            ):
                primary = 1
            elif all(any(candidate.startswith(word) for candidate in entry.words) for word in query_words):
                primary = 2 if all(word in entry.last.split() for word in query_words) else 3
            else:
                primary = 4
            strongest = min(strongest, primary)
            score = (
                primary,
                self._group_rank(facet),
                len(facet.path),
                " ".join(facet.path).casefold(),
                facet.value.casefold(),
            )
            scored.append((score, facet))
        if strongest <= 2:
            scored = [item for item in scored if item[0][0] <= 2]
        return tuple(
            facet
            for _score, facet in heapq.nsmallest(
                max(1, min(50, int(limit))), scored, key=lambda item: item[0]
            )
        )


@dataclass(frozen=True)
class BuilderCatalog:
    decks: tuple[CatalogFacet, ...] = ()
    topics: tuple[CatalogFacet, ...] = ()
    tags: tuple[CatalogFacet, ...] = ()
    anking: tuple[CatalogFacet, ...] = ()
    note_types: tuple[CatalogFacet, ...] = ()
    card_types: tuple[CatalogFacet, ...] = ()
    states: tuple[CatalogFacet, ...] = ()
    flags: tuple[CatalogFacet, ...] = ()
    search_index: CatalogSearchIndex | None = field(
        default=None, compare=False, repr=False
    )

    @property
    def has_anking(self) -> bool:
        return bool(self.anking)

    def search(
        self, text: str, *, limit: int = 8, exclude_only: bool = False
    ) -> tuple[CatalogFacet, ...]:
        if self.search_index is None:
            return ()
        return self.search_index.search(text, limit=limit, exclude_only=exclude_only)

    def search_topics(self, text: str, *, limit: int = 12) -> tuple[CatalogFacet, ...]:
        """Search only human-facing topic/tag choices for the guided flow."""

        if self.search_index is None:
            return ()
        return self.search_index.search(
            text,
            limit=limit,
            allowed_kinds=frozenset({"topic", "tag"}),
        )

    def find(self, kind: str, value: str) -> CatalogFacet | None:
        if self.search_index is None:
            return None
        return self.search_index.lookup.get((kind, value))

    @property
    def browse_groups(self) -> tuple[str, ...]:
        preferred = ("Exam", "Systems", "Resources", "Yield", "Step relevance")
        present = {facet.group for facet in self.anking if not facet.hidden}
        return tuple(group for group in preferred if group in present)

    def browse_children(
        self, group: str, parent: CatalogFacet | None = None
    ) -> tuple[CatalogFacet, ...]:
        """Return one deterministic level of the detected AnKing hierarchy."""

        values = tuple(
            facet
            for facet in self.anking
            if facet.group == group and not facet.hidden
        )
        if parent is not None:
            candidates = tuple(
                facet
                for facet in values
                if any(
                    child.startswith(root + "::")
                    for child in facet.values
                    for root in parent.values
                )
                and len(facet.path) > len(parent.path)
            )
            if not candidates:
                return ()
            depth = min(len(facet.path) for facet in candidates)
            return _unique_facets(
                facet for facet in candidates if len(facet.path) == depth
            )
        if not values:
            return ()
        depth = min(len(facet.path) for facet in values)
        roots = tuple(facet for facet in values if len(facet.path) == depth)
        if (
            len(roots) == 1
            and roots[0].label.casefold() == group.casefold()
            and self.browse_children(group, roots[0])
        ):
            return self.browse_children(group, roots[0])
        return _unique_facets(roots)

    def has_browse_children(self, facet: CatalogFacet) -> bool:
        return bool(self.browse_children(facet.group, facet))


def _unique_facets(values: Iterable[CatalogFacet]) -> tuple[CatalogFacet, ...]:
    found: dict[tuple[str, str, str], CatalogFacet] = {}
    for value in values:
        found[(value.kind, value.value.casefold(), value.group)] = value
    return tuple(
        sorted(
            found.values(),
            key=lambda item: (item.group.casefold(), item.path, item.label.casefold()),
        )
    )


def _anking_scope(value: str) -> tuple[str, str]:
    """Return a stable exam badge and version for an AnKing selector."""

    container = value.split("::", 1)[0]
    match = ANKING_CONTAINER.fullmatch(container)
    if match is None:
        return ("", "")
    badge = (match.group("exam") or "AnKing").replace("Step", "Step ")
    return (badge, match.group("version") or "")


def _collapse_anking_facets(values: Iterable[CatalogFacet]) -> tuple[CatalogFacet, ...]:
    """Collapse only exact semantic twins across exam containers.

    Version remains part of the identity, so old/new snapshots and lifecycle
    variants are never merged merely because their leaf labels resemble one
    another.
    """

    grouped: dict[tuple[str, str, tuple[str, ...], str], list[CatalogFacet]] = {}
    for facet in values:
        _badge, version = _anking_scope(facet.value)
        identity = (
            facet.kind,
            facet.group.casefold(),
            tuple(part.casefold() for part in facet.path),
            version.casefold(),
        )
        grouped.setdefault(identity, []).append(facet)

    collapsed: list[CatalogFacet] = []
    for facets in grouped.values():
        ordered = sorted(facets, key=lambda item: item.value.casefold())
        pairs = tuple(
            (facet.value, _anking_scope(facet.value)[0]) for facet in ordered
        )
        first = ordered[0]
        collapsed.append(
            replace(
                first,
                value=pairs[0][0],
                selector_values=tuple(value for value, _badge in pairs),
                selector_badges=tuple(badge for _value, badge in pairs),
                hidden=all(facet.hidden for facet in ordered),
            )
        )
    return _unique_facets(collapsed)


def _display_path(
    segments: tuple[str, ...],
    config: TopicParsingConfig,
    *,
    ignored: set[str] | None = None,
    renames: Mapping[str, str] | None = None,
    badges: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    ignored = ignored if ignored is not None else {
        canonical_segment(segment) for segment in config.ignored_segments
    }
    renames = renames if renames is not None else {
        canonical_segment(segment): label
        for segment, label in config.renamed_segments.items()
    }
    badges = badges if badges is not None else {
        source_key(root): label for root, label in config.source_badges.items()
    }
    result: list[str] = []
    for index, segment in enumerate(segments):
        stable = canonical_segment(segment)
        if not stable or stable in ignored:
            continue
        fallback = re.sub(
            r"(?<=[a-z])(?=[A-Z])", " ", display_segment(segment)
        )
        if stable in {"low/highyield", "lowhighyield"}:
            fallback = "Yield"
        elif "yield" in fallback.casefold():
            fallback = re.sub(r"^\d+[\s_-]*", "", fallback)
        result.append(
            badges.get(source_key(segment), renames.get(stable, fallback))
            if index == 0
            else renames.get(stable, fallback)
        )
    return tuple(result)


def _anking_facets(
    tag: str,
    segments: tuple[str, ...],
    config: TopicParsingConfig,
    *,
    ignored: set[str] | None = None,
    renames: Mapping[str, str] | None = None,
    badges: Mapping[str, str] | None = None,
    seen_values: set[str] | None = None,
) -> tuple[CatalogFacet, ...]:
    if len(segments) < 2:
        return ()
    match = ANKING_CONTAINER.fullmatch(segments[0])
    if not match:
        return ()
    exam = (match.group("exam") or "AnKing").replace("Step", "Step ")
    facets: list[CatalogFacet] = []
    exam_key = segments[0].casefold()
    if seen_values is None or exam_key not in seen_values:
        facets.append(CatalogFacet("topic", segments[0], exam, (exam,), "Exam"))
        if seen_values is not None:
            seen_values.add(exam_key)
    root = segments[1]
    lower = root.casefold()
    if lower in {"^systems", "#subjects"}:
        group = "Systems"
    elif "low/highyield" in lower or "yield" in lower:
        group = "Yield"
    elif "only_step" in tag.casefold() or lower == "#ak_other":
        group = "Step relevance"
    elif root.startswith("#"):
        group = "Resources"
    else:
        group = "AnKing topics"
    hidden = any(bool(UTILITY.match(segment)) for segment in segments[1:])
    for depth in range(1, len(segments)):
        value = "::".join(segments[: depth + 1])
        value_key = value.casefold()
        if seen_values is not None and value_key in seen_values:
            continue
        path = _display_path(
            segments[1 : depth + 1],
            config,
            ignored=ignored,
            renames=renames,
            badges=badges,
        )
        if not path:
            continue
        facets.append(
            CatalogFacet(
                "topic",
                value,
                path[-1],
                path,
                group,
                hidden,
            )
        )
        if seen_values is not None:
            seen_values.add(value_key)
    return tuple(facets)


def build_catalog(
    *,
    deck_names: Iterable[str],
    tags: Iterable[str],
    note_types: Iterable[str] = (),
    card_types: Iterable[str] = (),
    topic_config: TopicParsingConfig | None = None,
) -> BuilderCatalog:
    config = topic_config or TopicParsingConfig()
    # Context intentionally limits breadcrumb depth. Builder search must retain
    # the full selector path so similarly named chapters remain distinguishable.
    parser = TopicParser(replace(config, maximum_depth=10_000))
    deck_facets = tuple(
        CatalogFacet("deck", name, name.split("::")[-1], tuple(name.split("::")), "Decks")
        for name in deck_names
        if isinstance(name, str) and name.strip()
    )
    raw_tags: dict[tuple[str, str, str], CatalogFacet] = {}
    topics: dict[tuple[str, str, str], CatalogFacet] = {}
    anking: dict[tuple[str, str, str], CatalogFacet] = {}
    anking_values: set[str] = set()
    display_ignored = {
        canonical_segment(segment) for segment in config.ignored_segments
    }
    display_renames = {
        canonical_segment(segment): label
        for segment, label in config.renamed_segments.items()
    }
    display_badges = {
        source_key(root): label for root, label in config.source_badges.items()
    }

    def remember(
        destination: dict[tuple[str, str, str], CatalogFacet], facet: CatalogFacet
    ) -> None:
        destination.setdefault(
            (facet.kind, facet.value.casefold(), facet.group), facet
        )

    for raw in tags:
        if not isinstance(raw, str) or not raw.strip():
            continue
        tag = raw.strip()
        segments = split_hierarchical_tag(tag)
        if not segments:
            continue
        display_path = tuple(display_segment(segment) for segment in segments)
        hidden = any(bool(UTILITY.match(segment)) for segment in segments)
        for depth_index in range(1, len(segments) + 1):
            prefix_path = display_path[:depth_index]
            prefix_value = "::".join(segments[:depth_index])
            prefix_key = ("tag", prefix_value.casefold(), "All tags")
            if prefix_key not in raw_tags:
                raw_tags[prefix_key] = CatalogFacet(
                    "tag",
                    prefix_value,
                    prefix_path[-1],
                    prefix_path,
                    "All tags",
                    hidden,
                )
        special = _anking_facets(
            tag,
            segments,
            config,
            ignored=display_ignored,
            renames=display_renames,
            badges=display_badges,
            seen_values=anking_values,
        )
        if ANKING_CONTAINER.fullmatch(segments[0]):
            for facet in special:
                remember(anking, facet)
            continue
        parsed = parser.parse((tag,))
        if parsed.found:
            for path, prefix in zip(
                (parsed.path[:index] for index in range(1, len(parsed.path) + 1)),
                parsed.raw_prefixes,
            ):
                remember(
                    topics,
                    CatalogFacet("topic", prefix, path[-1], path, "Topics"),
                )
    notes = tuple(
        CatalogFacet("note", name, name, (name,), "Note types")
        for name in note_types
        if isinstance(name, str) and name.strip()
    )
    cards = tuple(
        CatalogFacet("card", name, name, (name,), "Card types")
        for name in card_types
        if isinstance(name, str) and name.strip()
    )
    states = tuple(
        CatalogFacet("state", value, label, (label,), "Card states")
        for value, label in (
            ("new", "New"),
            ("learn", "Learning"),
            ("review", "Review"),
            ("due", "Due now"),
            ("suspended", "Suspended"),
            ("buried", "Buried"),
        )
    )
    flags = tuple(
        CatalogFacet("flag", str(value), "No flag" if value == 0 else f"Flag {value}", ("No flag" if value == 0 else f"Flag {value}",), "Flags")
        for value in range(8)
    )
    decks_result = _unique_facets(deck_facets)
    topics_result = _unique_facets(topics.values())
    tags_result = _unique_facets(raw_tags.values())
    anking_result = _collapse_anking_facets(anking.values())
    notes_result = _unique_facets(notes)
    cards_result = _unique_facets(cards)
    structured_values = {
        value
        for facet in (*anking_result, *topics_result)
        for value in facet.values
    }
    searchable = (
        *anking_result,
        *topics_result,
        *decks_result,
        *(facet for facet in tags_result if facet.value not in structured_values),
        *notes_result,
        *cards_result,
        *states,
        *flags,
    )
    all_results = (
        *decks_result,
        *anking_result,
        *topics_result,
        *tags_result,
        *notes_result,
        *cards_result,
        *states,
        *flags,
    )
    return BuilderCatalog(
        decks=decks_result,
        topics=topics_result,
        tags=tags_result,
        anking=anking_result,
        note_types=notes_result,
        card_types=cards_result,
        states=states,
        flags=flags,
        search_index=CatalogSearchIndex(searchable, all_results),
    )
