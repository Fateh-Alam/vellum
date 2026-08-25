"""Typed configuration, validation, and Anki configuration persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol


THEMES = frozenset({"auto", "light", "dark"})
SIDES = frozenset({"left", "right"})
SIDEBAR_STATES = frozenset({"collapsed", "expanded", "remember"})
RECOVERY_LEVELS = frozenset({"current", "remember_last"})
RECOVERY_MODES = frozenset({"quick", "standard", "full"})
BUILDER_STATES = frozenset({"due_new", "due", "new", "recent_failures", "all"})
BUILDER_ORDERS = frozenset(
    {"due", "most_at_risk", "most_lapses", "oldest_seen", "added", "random"}
)
MAX_ABSENCE_DAYS = 2_147_483_647


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(minimum, min(maximum, int(value)))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(minimum, min(maximum, float(value)))


def _choice(value: Any, default: str, choices: frozenset[str]) -> str:
    return value if isinstance(value, str) and value in choices else default


@dataclass(frozen=True)
class ModuleFlags:
    context: bool = True
    recovery: bool = True
    time_machine: bool = True
    hud: bool = True
    resume: bool = True
    return_ramp: bool = True
    backtrack: bool = True
    mind_notes: bool = True
    session_debrief: bool = True
    topic_health: bool = False
    home_panel: bool = True
    study_builder: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ModuleFlags":
        defaults = cls()
        return cls(**{
            name: _bool(raw.get(name), getattr(defaults, name))
            for name in cls.__dataclass_fields__
        })

    def enabled(self, name: str) -> bool:
        if name not in self.__dataclass_fields__:
            return False
        return bool(getattr(self, name))


@dataclass(frozen=True)
class GeneralConfig:
    show_menu: bool = True
    keyboard_shortcuts: bool = True
    animations: bool = True
    reduced_motion: bool = False
    debug_logging: bool = False
    theme: str = "auto"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GeneralConfig":
        defaults = cls()
        return cls(
            show_menu=_bool(raw.get("show_menu"), defaults.show_menu),
            keyboard_shortcuts=_bool(
                raw.get("keyboard_shortcuts"), defaults.keyboard_shortcuts
            ),
            animations=_bool(raw.get("animations"), defaults.animations),
            reduced_motion=_bool(raw.get("reduced_motion"), defaults.reduced_motion),
            debug_logging=_bool(raw.get("debug_logging"), defaults.debug_logging),
            theme=_choice(raw.get("theme"), defaults.theme, THEMES),
        )


@dataclass(frozen=True)
class ContextConfig:
    side: str = "right"
    default_state: str = "collapsed"
    width: int = 288
    auto_collapse_on_new_card: bool = False
    pinned: bool = False
    show_title: bool = True
    show_breadcrumbs: bool = True
    show_retention: bool = True
    show_recent_failures: bool = True
    show_source_badges: bool = True
    show_card_count: bool = True
    show_maturity_breakdown: bool = True
    show_health: bool = True
    show_recovery: bool = True
    shortcut_enabled: bool = True
    shortcut: str = "C"
    collapse_shortcut: str = "Escape"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ContextConfig":
        defaults = cls()
        return cls(
            side=_choice(raw.get("side"), defaults.side, SIDES),
            default_state=_choice(
                raw.get("default_state"), defaults.default_state, SIDEBAR_STATES
            ),
            width=_bounded_int(raw.get("width"), defaults.width, 220, 480),
            auto_collapse_on_new_card=_bool(
                raw.get("auto_collapse_on_new_card"), False
            ),
            pinned=_bool(raw.get("pinned"), False),
            show_title=_bool(raw.get("show_title"), True),
            show_breadcrumbs=_bool(raw.get("show_breadcrumbs"), True),
            show_retention=_bool(raw.get("show_retention"), True),
            show_recent_failures=_bool(raw.get("show_recent_failures"), True),
            show_source_badges=_bool(raw.get("show_source_badges"), True),
            show_card_count=_bool(raw.get("show_card_count"), True),
            show_maturity_breakdown=_bool(
                raw.get("show_maturity_breakdown"), True
            ),
            show_health=_bool(raw.get("show_health"), True),
            show_recovery=_bool(raw.get("show_recovery"), True),
            shortcut_enabled=_bool(raw.get("shortcut_enabled"), True),
            shortcut=(
                raw["shortcut"].strip()
                if isinstance(raw.get("shortcut"), str) and raw["shortcut"].strip()
                else "C"
            ),
            collapse_shortcut=(
                raw["collapse_shortcut"].strip()
                if isinstance(raw.get("collapse_shortcut"), str)
                and raw["collapse_shortcut"].strip()
                else "Escape"
            ),
        )


@dataclass(frozen=True)
class HudConfig:
    placement: str = "bottom_left"
    show_completed: bool = True
    show_estimated_total: bool = True
    show_elapsed: bool = True
    show_remaining_time: bool = True
    show_eta: bool = False
    show_cards_per_minute: bool = False
    show_session_target: bool = False
    show_progress_bar: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "HudConfig":
        return cls(
            placement=_choice(
                raw.get("placement"),
                "bottom_left",
                frozenset(
                    {"bottom_left", "bottom_center", "bottom_right", "top", "hidden"}
                ),
            ),
            show_completed=_bool(raw.get("show_completed"), True),
            show_estimated_total=_bool(raw.get("show_estimated_total"), True),
            show_elapsed=_bool(raw.get("show_elapsed"), True),
            show_remaining_time=_bool(raw.get("show_remaining_time"), True),
            show_eta=_bool(raw.get("show_eta"), False),
            show_cards_per_minute=_bool(
                raw.get("show_cards_per_minute"), False
            ),
            show_session_target=_bool(raw.get("show_session_target"), False),
            show_progress_bar=_bool(raw.get("show_progress_bar"), False),
        )


@dataclass(frozen=True)
class FallbackSeconds:
    new: float = 20.0
    learning: float = 12.0
    review: float = 7.0
    relearning: float = 10.0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FallbackSeconds":
        defaults = cls()
        return cls(**{
            name: _bounded_float(raw.get(name), getattr(defaults, name), 1.0, 300.0)
            for name in cls.__dataclass_fields__
        })


@dataclass(frozen=True)
class TimeMachineConfig:
    presets_minutes: tuple[int, ...] = (10, 20, 30, 45, 60)
    adaptive_timing: bool = True
    minimum_history: int = 20
    end_behavior: str = "no_stop"
    fallback_seconds: FallbackSeconds = field(default_factory=FallbackSeconds)
    shortcut_enabled: bool = True
    shortcut: str = "Ctrl+Shift+T"
    automatically_start_hud: bool = True
    show_estimates_on_deck: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TimeMachineConfig":
        presets_raw = raw.get("presets_minutes")
        presets: list[int] = []
        if isinstance(presets_raw, (list, tuple)):
            for value in presets_raw:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    value = int(value)
                    if 1 <= value <= 480 and value not in presets:
                        presets.append(value)
        return cls(
            presets_minutes=tuple(presets) or cls().presets_minutes,
            adaptive_timing=_bool(raw.get("adaptive_timing"), True),
            minimum_history=_bounded_int(raw.get("minimum_history"), 20, 3, 500),
            end_behavior=_choice(
                raw.get("end_behavior"),
                "no_stop",
                frozenset({"soft_stop", "alert", "no_stop"}),
            ),
            fallback_seconds=FallbackSeconds.from_mapping(
                _mapping(raw.get("fallback_seconds"))
            ),
            shortcut_enabled=_bool(raw.get("shortcut_enabled"), True),
            shortcut=(
                raw["shortcut"].strip()
                if isinstance(raw.get("shortcut"), str) and raw["shortcut"].strip()
                else "Ctrl+Shift+T"
            ),
            automatically_start_hud=_bool(raw.get("automatically_start_hud"), True),
            show_estimates_on_deck=_bool(raw.get("show_estimates_on_deck"), True),
        )


@dataclass(frozen=True)
class ResumeConfig:
    checkpoint_seconds: int = 30
    stale_after_days: int = 7
    show_on_launch: bool = True
    enable_checkpoints: bool = True
    detect_inactivity: bool = True
    inactivity_seconds: int = 1800
    show_on_home: bool = True
    history_days: int = 90
    maximum_sessions: int = 500

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ResumeConfig":
        defaults = cls()
        return cls(
            checkpoint_seconds=_bounded_int(
                raw.get("checkpoint_seconds"), defaults.checkpoint_seconds, 5, 3600
            ),
            stale_after_days=_bounded_int(
                raw.get("stale_after_days"), defaults.stale_after_days, 1, 365
            ),
            show_on_launch=_bool(raw.get("show_on_launch"), True),
            enable_checkpoints=_bool(raw.get("enable_checkpoints"), True),
            detect_inactivity=_bool(raw.get("detect_inactivity"), True),
            inactivity_seconds=_bounded_int(
                raw.get("inactivity_seconds"), defaults.inactivity_seconds, 60, 86400
            ),
            show_on_home=_bool(raw.get("show_on_home"), True),
            history_days=_bounded_int(raw.get("history_days"), 90, 0, 3650),
            maximum_sessions=_bounded_int(
                raw.get("maximum_sessions"), 500, 10, 10000
            ),
        )


@dataclass(frozen=True)
class ReturnRampConfig:
    absence_days: int = 3
    show_on_launch: bool = True
    suggestion_count: int = 3

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ReturnRampConfig":
        defaults = cls()
        return cls(
            absence_days=_bounded_int(
                raw.get("absence_days"), defaults.absence_days, 1, MAX_ABSENCE_DAYS
            ),
            show_on_launch=_bool(raw.get("show_on_launch"), True),
            suggestion_count=_bounded_int(
                raw.get("suggestion_count"), defaults.suggestion_count, 1, 5
            ),
        )


@dataclass(frozen=True)
class BacktrackConfig:
    shortcut_enabled: bool = True
    shortcut: str = "Alt+B"
    history_limit: int = 50

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "BacktrackConfig":
        defaults = cls()
        shortcut = raw.get("shortcut")
        return cls(
            shortcut_enabled=_bool(raw.get("shortcut_enabled"), True),
            shortcut=(
                shortcut.strip()
                if isinstance(shortcut, str) and shortcut.strip()
                else defaults.shortcut
            ),
            history_limit=_bounded_int(
                raw.get("history_limit"), defaults.history_limit, 2, 250
            ),
        )


@dataclass(frozen=True)
class MindNotesConfig:
    shortcut_enabled: bool = True
    shortcut: str = "Alt+M"
    resurface: bool = True
    maximum_active_per_topic: int = 3

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "MindNotesConfig":
        defaults = cls()
        shortcut = raw.get("shortcut")
        return cls(
            shortcut_enabled=_bool(raw.get("shortcut_enabled"), True),
            shortcut=(
                shortcut.strip()
                if isinstance(shortcut, str) and shortcut.strip()
                else defaults.shortcut
            ),
            resurface=_bool(raw.get("resurface"), True),
            maximum_active_per_topic=_bounded_int(
                raw.get("maximum_active_per_topic"),
                defaults.maximum_active_per_topic,
                1,
                10,
            ),
        )


@dataclass(frozen=True)
class DebriefConfig:
    show_completion_card: bool = True
    include_normal_sessions: bool = True
    handoff_enabled: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DebriefConfig":
        defaults = cls()
        return cls(
            **{
                name: _bool(raw.get(name), getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class RecoveryConfig:
    shortcut_enabled: bool = True
    shortcut: str = "Shift+C"
    default_level: str = "current"
    default_mode: str = "standard"
    include_new: bool = False
    include_current: bool = True
    recent_failure_days: int = 14
    max_quick: int = 8
    max_standard: int = 30
    ask_before_create: bool = True
    deck_name_pattern: str = "Vellum Recovery - {topic}"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RecoveryConfig":
        defaults = cls()
        shortcut = raw.get("shortcut")
        deck_pattern = raw.get("deck_name_pattern")
        return cls(
            shortcut_enabled=_bool(raw.get("shortcut_enabled"), True),
            shortcut=(
                shortcut.strip()
                if isinstance(shortcut, str) and shortcut.strip()
                else defaults.shortcut
            ),
            default_level=_choice(
                raw.get("default_level"), defaults.default_level, RECOVERY_LEVELS
            ),
            default_mode=_choice(
                raw.get("default_mode"), defaults.default_mode, RECOVERY_MODES
            ),
            include_new=_bool(raw.get("include_new"), defaults.include_new),
            include_current=_bool(
                raw.get("include_current"), defaults.include_current
            ),
            recent_failure_days=_bounded_int(
                raw.get("recent_failure_days"),
                defaults.recent_failure_days,
                1,
                365,
            ),
            max_quick=_bounded_int(raw.get("max_quick"), defaults.max_quick, 4, 8),
            max_standard=_bounded_int(
                raw.get("max_standard"), defaults.max_standard, 8, 500
            ),
            ask_before_create=_bool(
                raw.get("ask_before_create"), defaults.ask_before_create
            ),
            deck_name_pattern=(
                deck_pattern.strip()
                if isinstance(deck_pattern, str)
                and deck_pattern.strip()
                and "{topic}" in deck_pattern
                else defaults.deck_name_pattern
            ),
        )


@dataclass(frozen=True)
class StudyBuilderConfig:
    shortcut_enabled: bool = True
    shortcut: str = "Ctrl+Shift+B"
    default_limit: int = 100
    default_state_preset: str = "due_new"
    default_order: str = "due"
    show_snippets: bool = True
    show_anking_facets: bool = True
    tutorial_version: int = 0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "StudyBuilderConfig":
        defaults = cls()
        shortcut = raw.get("shortcut")
        return cls(
            shortcut_enabled=_bool(raw.get("shortcut_enabled"), True),
            shortcut=(
                shortcut.strip()
                if isinstance(shortcut, str) and shortcut.strip()
                else defaults.shortcut
            ),
            default_limit=_bounded_int(
                raw.get("default_limit"), defaults.default_limit, 1, MAX_ABSENCE_DAYS
            ),
            default_state_preset=_choice(
                raw.get("default_state_preset"),
                defaults.default_state_preset,
                BUILDER_STATES,
            ),
            default_order=_choice(
                raw.get("default_order"), defaults.default_order, BUILDER_ORDERS
            ),
            show_snippets=_bool(raw.get("show_snippets"), True),
            show_anking_facets=_bool(raw.get("show_anking_facets"), True),
            tutorial_version=_bounded_int(
                raw.get("tutorial_version"), defaults.tutorial_version, 0, 1
            ),
        )


@dataclass(frozen=True)
class HomeConfig:
    show_continue: bool = True
    show_time_machine: bool = True
    show_weak_topics: bool = True
    show_estimated_workload: bool = True
    show_greeting: bool = True
    show_study_builder: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "HomeConfig":
        defaults = cls()
        return cls(
            **{
                name: _bool(raw.get(name), getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True)
class TopicParsingConfig:
    preferred_roots: tuple[str, ...] = (
        "#FirstAid",
        "#Pathoma",
        "#B&B",
        "#Sketchy",
        "#Systems",
    )
    ignored_roots: tuple[str, ...] = (
        "#AK_Other",
        "#AK_Original_Decks",
        "AnkiHub_Deleted",
    )
    ignored_segments: tuple[str, ...] = ()
    renamed_segments: dict[str, str] = field(default_factory=dict)
    source_badges: dict[str, str] = field(
        default_factory=lambda: {
            "#FirstAid": "First Aid",
            "#Pathoma": "Pathoma",
            "#B&B": "Boards & Beyond",
            "#Sketchy": "Sketchy",
            "#Systems": "Systems",
        }
    )
    maximum_depth: int = 8
    anking_adapter: bool = True
    generic_fallback: bool = True

    @staticmethod
    def _strings(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            return default
        result: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip() and item.strip() not in result:
                result.append(item.strip())
        return tuple(result)

    @staticmethod
    def _string_map(value: Any, default: Mapping[str, str]) -> dict[str, str]:
        if not isinstance(value, Mapping):
            return dict(default)
        return {
            str(key).strip(): str(label).strip()
            for key, label in value.items()
            if isinstance(key, str)
            and isinstance(label, str)
            and key.strip()
            and label.strip()
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TopicParsingConfig":
        defaults = cls()
        return cls(
            preferred_roots=cls._strings(
                raw.get("preferred_roots"), defaults.preferred_roots
            ),
            ignored_roots=cls._strings(raw.get("ignored_roots"), defaults.ignored_roots),
            ignored_segments=cls._strings(raw.get("ignored_segments"), ()),
            renamed_segments=cls._string_map(raw.get("renamed_segments"), {}),
            source_badges=cls._string_map(
                raw.get("source_badges"), defaults.source_badges
            ),
            maximum_depth=_bounded_int(
                raw.get("maximum_depth"), defaults.maximum_depth, 1, 20
            ),
            anking_adapter=_bool(raw.get("anking_adapter"), True),
            generic_fallback=_bool(raw.get("generic_fallback"), True),
        )


@dataclass(frozen=True)
class VellumConfig:
    config_version: int = 3
    enabled: bool = True
    onboarding_completed: bool = False
    onboarding_version: int = 0
    onboarding_invitation_version: int = 0
    modules: ModuleFlags = field(default_factory=ModuleFlags)
    general: GeneralConfig = field(default_factory=GeneralConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    hud: HudConfig = field(default_factory=HudConfig)
    time_machine: TimeMachineConfig = field(default_factory=TimeMachineConfig)
    resume: ResumeConfig = field(default_factory=ResumeConfig)
    return_ramp: ReturnRampConfig = field(default_factory=ReturnRampConfig)
    backtrack: BacktrackConfig = field(default_factory=BacktrackConfig)
    mind_notes: MindNotesConfig = field(default_factory=MindNotesConfig)
    debrief: DebriefConfig = field(default_factory=DebriefConfig)
    recovery: RecoveryConfig = field(default_factory=RecoveryConfig)
    study_builder: StudyBuilderConfig = field(default_factory=StudyBuilderConfig)
    home: HomeConfig = field(default_factory=HomeConfig)
    topic_parsing: TopicParsingConfig = field(default_factory=TopicParsingConfig)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "VellumConfig":
        raw = raw or {}
        completed = _bool(raw.get("onboarding_completed"), False)
        inferred_onboarding_version = 1 if completed else 0
        return cls(
            config_version=3,
            enabled=_bool(raw.get("enabled"), True),
            onboarding_completed=completed,
            onboarding_version=_bounded_int(
                raw.get("onboarding_version"), inferred_onboarding_version, 0, 3
            ),
            onboarding_invitation_version=_bounded_int(
                raw.get("onboarding_invitation_version"), 0, 0, 3
            ),
            modules=ModuleFlags.from_mapping(_mapping(raw.get("modules"))),
            general=GeneralConfig.from_mapping(_mapping(raw.get("general"))),
            context=ContextConfig.from_mapping(_mapping(raw.get("context"))),
            hud=HudConfig.from_mapping(_mapping(raw.get("hud"))),
            time_machine=TimeMachineConfig.from_mapping(
                _mapping(raw.get("time_machine"))
            ),
            resume=ResumeConfig.from_mapping(_mapping(raw.get("resume"))),
            return_ramp=ReturnRampConfig.from_mapping(
                _mapping(raw.get("return_ramp"))
            ),
            backtrack=BacktrackConfig.from_mapping(_mapping(raw.get("backtrack"))),
            mind_notes=MindNotesConfig.from_mapping(
                _mapping(raw.get("mind_notes"))
            ),
            debrief=DebriefConfig.from_mapping(_mapping(raw.get("debrief"))),
            recovery=RecoveryConfig.from_mapping(_mapping(raw.get("recovery"))),
            study_builder=StudyBuilderConfig.from_mapping(
                _mapping(raw.get("study_builder"))
            ),
            home=HomeConfig.from_mapping(_mapping(raw.get("home"))),
            topic_parsing=TopicParsingConfig.from_mapping(
                _mapping(raw.get("topic_parsing"))
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        data = asdict(self)
        data["time_machine"]["presets_minutes"] = list(
            self.time_machine.presets_minutes
        )
        for key in ("preferred_roots", "ignored_roots", "ignored_segments"):
            data["topic_parsing"][key] = list(getattr(self.topic_parsing, key))
        return data


class AddonManager(Protocol):
    def getConfig(self, module: str) -> Mapping[str, Any] | None: ...
    def writeConfig(self, module: str, config: Mapping[str, Any]) -> None: ...


class AnkiConfigStore:
    """Adapter around Anki's supported add-on configuration API."""

    def __init__(self, addon_manager: AddonManager, package_name: str) -> None:
        self._addon_manager = addon_manager
        self._package_name = package_name

    def load(self) -> VellumConfig:
        return VellumConfig.from_mapping(
            self._addon_manager.getConfig(self._package_name)
        )

    def save(self, config: VellumConfig) -> None:
        self._addon_manager.writeConfig(self._package_name, config.to_mapping())
