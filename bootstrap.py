"""Composition root for the Vellum Anki add-on."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .core.config import AnkiConfigStore, VellumConfig
from .core.db import Database
from .core.events import EventBus
from .core.logging import configure_logging
from .core.modules import ModuleRegistry
from .features.context import ContextModule
from .features.debrief import DebriefModule
from .features.backtrack import BacktrackModule
from .features.hud import HudModule
from .features.home import HomeModule
from .features.mind_notes import MindNotesModule
from .features.resume import ResumeModule
from .features.recovery import RecoveryModule
from .features.return_ramp import ReturnRampModule
from .features.session_tracking import SessionTrackingModule
from .features.study_builder import StudyBuilderModule
from .features.time_machine import TimeMachineModule
from .features.topic_health import TopicHealthModule
from .sessions.manager import SessionManager
from .sessions.generated_decks import GeneratedDeckHistoryRepository
from .sessions.debrief import DebriefRepository
from .sessions.repository import SessionRepository
from .builder.repository import StudyRecipeRepository
from .continuity.activity import ActivityRepository
from .notes.repository import MindNoteRepository
from .topics.cache import TopicPathCache
from .topics.parser import TopicParser
from .topics.service import TopicService
from .timing.model import TimingModel
from .timing.models import TimingBucket
from .timing.repository import TimingRepository


FEATURE_NAMES = (
    "context",
    "recovery",
    "study_builder",
    "time_machine",
    "hud",
    "return_ramp",
    "resume",
    "backtrack",
    "mind_notes",
    "session_debrief",
    "topic_health",
    "home_panel",
)


@dataclass
class VellumServices:
    """Shared services supplied explicitly to independent feature modules."""

    config_store: AnkiConfigStore
    database: Database
    events: EventBus
    modules: ModuleRegistry
    topics: TopicService
    sessions: SessionManager
    generated_decks: GeneratedDeckHistoryRepository
    study_recipes: StudyRecipeRepository
    activity: ActivityRepository
    mind_notes: MindNoteRepository
    debriefs: DebriefRepository
    timing: TimingModel
    persistence_available: bool = True
    data_dir: Path = Path(".")


@dataclass
class VellumApplication:
    """Owns the process-level Vellum services and their lifecycle."""

    package_name: str
    services: VellumServices
    settings_action: Any | None = None
    menu: Any | None = None

    @property
    def config(self) -> VellumConfig:
        return self.services.config_store.load()

    def effective_modules(self, config: VellumConfig) -> Any:
        """Disable only persistence-dependent surfaces after a DB failure."""

        if self.services.persistence_available:
            return config.modules
        return replace(
            config.modules,
            recovery=False,
            study_builder=False,
            time_machine=False,
            hud=False,
            resume=False,
            return_ramp=False,
            mind_notes=False,
            session_debrief=False,
            topic_health=False,
            home_panel=False,
        )

    def start(self) -> None:
        config = self.config
        try:
            self.services.database.migrate()
            self.services.activity.begin_open()
            self.services.sessions.repository.interrupt_open_sessions()
            self.services.generated_decks.interrupt_open()
        except Exception:
            import logging

            logging.getLogger("vellum").exception(
                "Vellum persistence failed during profile start; using "
                "Context-only in-memory fallback"
            )
            self.services.database.fallback_to_memory()
            self.services.database.migrate()
            self.services.activity.begin_open()
            self.services.persistence_available = False
        if config.enabled:
            self.services.modules.reconcile(self.effective_modules(config))

    def stop(self) -> None:
        try:
            self.services.modules.stop_all()
            self.services.activity.finish_open()
        finally:
            self.services.database.close()

    def apply_config(self, config: VellumConfig) -> None:
        self.services.config_store.save(config)
        configure_logging(
            self.services.data_dir,
            debug=config.general.debug_logging,
        )
        self.services.topics.reconfigure(TopicParser(config.topic_parsing))
        fallback = config.time_machine.fallback_seconds
        self.services.timing.reconfigure(
            {
                TimingBucket.NEW: fallback.new,
                TimingBucket.LEARNING: fallback.learning,
                TimingBucket.REVIEW: fallback.review,
                TimingBucket.RELEARNING: fallback.relearning,
            },
            (
                config.time_machine.minimum_history
                if config.time_machine.adaptive_timing
                else 1_000_000_000
            ),
        )
        self.services.sessions.inactivity_seconds = (
            config.resume.inactivity_seconds
            if config.resume.detect_inactivity
            else 365 * 86400
        )
        if config.enabled:
            self.services.modules.restart_enabled(self.effective_modules(config))
        else:
            self.services.modules.stop_all()
        if self.menu is not None:
            self.menu.menuAction().setVisible(config.general.show_menu)
        self.services.events.emit("config_changed", config)


def bootstrap(package_name: str, addon_root: Path) -> VellumApplication | None:
    """Start Vellum when imported by Anki; return ``None`` in plain Python.

    The broad import guard is deliberate: importing this repository for tests,
    tooling, or packaging must not require Anki's bundled Python environment.
    Runtime failures after Anki is detected are logged and isolated so a broken
    optional add-on cannot prevent Anki from opening.
    """

    try:
        from aqt import gui_hooks, mw  # type: ignore[import-not-found]
    except ImportError:
        return None

    user_data = addon_root / "user_files"
    logger = configure_logging(user_data, debug=False)

    try:
        config_store = AnkiConfigStore(mw.addonManager, package_name)
        config = config_store.load()
        configure_logging(user_data, debug=config.general.debug_logging)

        persistence_available = True
        database = Database(user_data / "vellum.sqlite3")
        try:
            database.migrate()
        except Exception:
            logger.exception(
                "Vellum persistence is unavailable; starting Context-only fallback"
            )
            database.fallback_to_memory()
            database.migrate()
            persistence_available = False
        events = EventBus(logger=logger)
        modules = ModuleRegistry(logger=logger)
        topics = TopicService(
            parser=TopicParser(config.topic_parsing),
            cache=TopicPathCache(database),
            events=events,
        )
        sessions = SessionManager(
            SessionRepository(database),
            events=events,
            inactivity_seconds=(
                config.resume.inactivity_seconds
                if config.resume.detect_inactivity
                else 365 * 86400
            ),
        )
        generated_decks = GeneratedDeckHistoryRepository(database)
        study_recipes = StudyRecipeRepository(database)
        activity = ActivityRepository(database)
        mind_notes = MindNoteRepository(database)
        debriefs = DebriefRepository(database)
        fallback = config.time_machine.fallback_seconds
        timing = TimingModel(
            TimingRepository(database),
            {
                TimingBucket.NEW: fallback.new,
                TimingBucket.LEARNING: fallback.learning,
                TimingBucket.REVIEW: fallback.review,
                TimingBucket.RELEARNING: fallback.relearning,
            },
            (
                config.time_machine.minimum_history
                if config.time_machine.adaptive_timing
                else 1_000_000_000
            ),
        )
        tracking = SessionTrackingModule(
            manager=sessions,
            topics=topics,
            timing=timing,
            mw=mw,
            config=config_store.load,
            generated_decks=generated_decks,
            logger=logger,
        )
        for feature_name in FEATURE_NAMES:
            if feature_name == "context":
                modules.register(
                    ContextModule(
                        package_name=package_name,
                        mw=mw,
                        topics=topics,
                        config=config_store.load,
                        events=events,
                        logger=logger,
                    )
                )
            elif feature_name == "resume":
                modules.register(
                    ResumeModule(
                        mw=mw,
                        manager=sessions,
                        topics=topics,
                        config=config_store.load,
                        timing=timing,
                        tracking=tracking,
                        events=events,
                        generated_decks=generated_decks,
                        activity=activity,
                        logger=logger,
                    )
                )
            elif feature_name == "return_ramp":
                modules.register(
                    ReturnRampModule(
                        mw=mw,
                        activity=activity,
                        sessions=sessions,
                        timing=timing,
                        config=config_store.load,
                        events=events,
                        logger=logger,
                    )
                )
            elif feature_name == "backtrack":
                modules.register(
                    BacktrackModule(
                        mw=mw,
                        topics=topics,
                        config=config_store.load,
                        logger=logger,
                    )
                )
            elif feature_name == "mind_notes":
                modules.register(
                    MindNotesModule(
                        package_name=package_name,
                        mw=mw,
                        topics=topics,
                        repository=mind_notes,
                        config=config_store.load,
                        events=events,
                        logger=logger,
                    )
                )
            elif feature_name == "session_debrief":
                modules.register(
                    DebriefModule(
                        package_name=package_name,
                        mw=mw,
                        manager=sessions,
                        tracking=tracking,
                        repository=debriefs,
                        generated_decks=generated_decks,
                        config=config_store.load,
                        events=events,
                        logger=logger,
                    )
                )
            elif feature_name == "recovery":
                modules.register(
                    RecoveryModule(
                        mw=mw,
                        topics=topics,
                        manager=sessions,
                        tracking=tracking,
                        config=config_store.load,
                        events=events,
                        generated_decks=generated_decks,
                        timing=timing,
                        logger=logger,
                    )
                )
            elif feature_name == "time_machine":
                modules.register(
                    TimeMachineModule(
                        package_name=package_name,
                        mw=mw,
                        manager=sessions,
                        timing=timing,
                        tracking=tracking,
                        config=config_store.load,
                        events=events,
                        generated_decks=generated_decks,
                        logger=logger,
                    )
                )
            elif feature_name == "study_builder":
                modules.register(
                    StudyBuilderModule(
                        package_name=package_name,
                        mw=mw,
                        manager=sessions,
                        tracking=tracking,
                        timing=timing,
                        config=config_store.load,
                        save_config=config_store.save,
                        events=events,
                        generated_decks=generated_decks,
                        recipes=study_recipes,
                        logger=logger,
                    )
                )
            elif feature_name == "hud":
                modules.register(
                    HudModule(
                        package_name=package_name,
                        mw=mw,
                        manager=sessions,
                        tracking=tracking,
                        config=config_store.load,
                        events=events,
                        logger=logger,
                    )
                )
            elif feature_name == "home_panel":
                modules.register(
                    HomeModule(
                        package_name=package_name,
                        mw=mw,
                        topics=topics,
                        sessions=sessions,
                        timing=timing,
                        config=config_store.load,
                        events=events,
                        logger=logger,
                    )
                )
            elif feature_name == "topic_health":
                modules.register(TopicHealthModule(logger=logger))
            else:
                raise RuntimeError(f"Unregistered Vellum feature: {feature_name}")

        app = VellumApplication(
            package_name=package_name,
            services=VellumServices(
                config_store=config_store,
                database=database,
                events=events,
                modules=modules,
                topics=topics,
                sessions=sessions,
                generated_decks=generated_decks,
                study_recipes=study_recipes,
                activity=activity,
                mind_notes=mind_notes,
                debriefs=debriefs,
                timing=timing,
                persistence_available=persistence_available,
                data_dir=user_data,
            ),
        )
        setattr(mw, "_vellum_application", app)

        for event_name in (
            "session_interrupted",
            "session_resumed",
            "session_completed",
            "session_abandoned",
        ):
            events.subscribe(
                event_name,
                lambda session, repository=generated_decks: repository.mark_status(
                    session
                ),
            )

        from .ui.settings import install_settings_action, show_settings

        app.settings_action = install_settings_action(mw, app)
        events.subscribe(
            "settings_requested",
            lambda tab="General": show_settings(mw, app, initial_tab=str(tab)),
        )

        from .ui.menu import install_vellum_menu

        app.menu = install_vellum_menu(mw, app)
        app.menu.menuAction().setVisible(config.general.show_menu)

        profile_ready = False
        profile_will_close = getattr(gui_hooks, "profile_will_close", None)

        def profile_closed() -> None:
            nonlocal profile_ready
            app.stop()
            profile_ready = False

        if profile_will_close is not None:
            profile_will_close.append(profile_closed)
        profile_did_open = getattr(gui_hooks, "profile_did_open", None)
        from .ui.onboarding import schedule_onboarding

        def profile_opened() -> None:
            nonlocal profile_ready
            if profile_ready:
                return
            profile_ready = True
            app.start()
            legacy_generated = sessions.repository.generated_sessions()
            def prune_sessions() -> None:
                current_config = app.config
                sessions.repository.prune(
                    history_days=current_config.resume.history_days,
                    maximum_sessions=current_config.resume.maximum_sessions,
                )
                debriefs.prune_normal(
                    history_days=current_config.resume.history_days,
                    maximum_sessions=current_config.resume.maximum_sessions,
                )

            def repair_debriefs() -> None:
                module = modules.get("session_debrief")
                repair = getattr(module, "repair_terminal", None)
                if callable(repair) and getattr(module, "running", False):
                    repaired = int(repair())
                    if repaired:
                        logger.info("Repaired %d missing Session Debrief(s)", repaired)

            if legacy_generated:
                from aqt.operations import QueryOp  # type: ignore[import-not-found]

                def backfilled(count: int) -> None:
                    logger.info(
                        "Backfilled %d generated deck history record(s)", count
                    )
                    repair_debriefs()
                    prune_sessions()

                def backfill_failed(error: Exception) -> None:
                    logger.warning(
                        "Generated deck history backfill failed: %s", error
                    )
                    repair_debriefs()
                    prune_sessions()

                QueryOp(
                    parent=mw,
                    op=lambda collection: generated_decks.backfill_sessions(
                        collection, legacy_generated
                    ),
                    success=backfilled,
                ).failure(backfill_failed).run_in_background()
            else:
                repair_debriefs()
                prune_sessions()
            mw.progress.single_shot(
                800, lambda: schedule_onboarding(mw, app), False
            )

        if profile_did_open is not None:
            profile_did_open.append(profile_opened)

        if getattr(mw, "col", None) is not None:
            profile_opened()
        logger.info("Vellum foundation initialized; awaiting profile when necessary")
        return app
    except Exception:
        logger.exception("Vellum failed to initialize; add-on features are disabled")
        return None
