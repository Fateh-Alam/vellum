"""Faceted Study Builder over safe, temporary Anki filtered decks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import logging
from typing import Any

from ..anki.hooks import HookRegistry
from ..anki.shortcuts import assign_shortcut
from ..anki.study_builder import (
    PreparedBuilderDeck,
    collect_builder_catalog,
    collect_builder_preview,
    collect_deck_tag_scope,
    collect_topic_deck_scope,
    collection_key,
    create_builder_deck,
    exact_selection_is_current,
    owned_builder_deck_is_empty,
    rollback_builder_start,
)
from ..builder.models import (
    BuildRequest,
    BuilderDefinition,
    BuilderPreview,
)
from ..builder.catalog import BuilderCatalog
from ..builder.scope import DeckTagScope, TopicDeckScope
from ..builder.repository import StudyRecipeRepository
from ..core.config import VellumConfig
from ..core.events import EventBus
from ..sessions.generated_decks import GeneratedDeckHistoryRepository
from ..sessions.manager import SessionManager
from ..sessions.models import Session, SessionOrigin, TERMINAL_STATUSES
from ..timing.model import TimingModel
from ..timing.models import TimingBucket
from .session_tracking import SessionTrackingModule


class StudyBuilderModule:
    name = "study_builder"

    def __init__(
        self,
        package_name: str,
        mw: Any,
        manager: SessionManager,
        tracking: SessionTrackingModule,
        timing: TimingModel,
        config: Callable[[], VellumConfig],
        save_config: Callable[[VellumConfig], None],
        events: EventBus,
        generated_decks: GeneratedDeckHistoryRepository,
        recipes: StudyRecipeRepository,
        logger: logging.Logger | None = None,
    ) -> None:
        self._package_name = package_name
        self._mw = mw
        self._manager = manager
        self._tracking = tracking
        self._timing = timing
        self._config = config
        self._save_config = save_config
        self._events = events
        self._generated_decks = generated_decks
        self._recipes = recipes
        self._logger = logger or logging.getLogger("vellum.features.study_builder")
        self._hooks = HookRegistry(self._logger)
        self._action: Any | None = None
        self._window: Any | None = None
        self._running = False
        self._collection_key = ""
        self._catalog_cache: BuilderCatalog | None = None
        self._catalog_collection_key = ""
        self._collection_revision = 0
        self._preview_cache: dict[tuple[str, int, int, str, bool], BuilderPreview] = {}
        self._topic_deck_cache: dict[
            tuple[int, tuple[str, ...], bool], TopicDeckScope
        ] = {}
        self._deck_tag_cache: dict[
            tuple[int, tuple[str, ...]], DeckTagScope
        ] = {}
        self._unsubscribe: list[Callable[[], None]] = []

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        from aqt import gui_hooks  # type: ignore[import-not-found]

        self._tracking.start()
        self._install_action()
        config = self._config()
        assign_shortcut(
            self._action,
            self._mw,
            config.study_builder.shortcut,
            enabled=config.general.keyboard_shortcuts
            and config.study_builder.shortcut_enabled,
            logger=self._logger,
            feature_name="Study Builder",
        )
        self._action.setEnabled(True)
        self._hooks.register(gui_hooks.reviewer_will_end, self._reviewer_ended)
        self._hooks.register(
            gui_hooks.overview_will_render_content, self._overview_content
        )
        self._hooks.register(gui_hooks.webview_will_set_content, self._inject_assets)
        self._hooks.register(
            gui_hooks.webview_did_receive_js_message, self._receive_message
        )
        self._hooks.register(
            getattr(gui_hooks, "top_toolbar_did_init_links", None),
            self._toolbar_links,
        )
        self._hooks.register(
            getattr(gui_hooks, "collection_did_load", None), self._invalidate_catalog
        )
        self._hooks.register(
            getattr(gui_hooks, "sync_did_finish", None), self._invalidate_catalog
        )
        self._hooks.register(
            getattr(gui_hooks, "operation_did_execute", None),
            self._operation_did_execute,
        )
        self._unsubscribe.append(
            self._events.subscribe("study_builder_open_requested", self.open)
        )
        self._running = True
        self._refresh_toolbar()

    def stop(self) -> None:
        if not self._running:
            return
        self._tracking.stop()
        self._hooks.clear()
        self._refresh_toolbar()
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        if self._action is not None:
            self._action.setEnabled(False)
            self._action.setShortcut("")
        if self._window is not None:
            self._window.close()
            self._window = None
        self._invalidate_catalog()
        self._running = False

    def _toolbar_links(self, links: list[str], toolbar: Any) -> None:
        """Put the common path in Anki's native top navigation bar."""

        link = toolbar.create_link(
            "vellum-study-builder",
            "Builder",
            self.open,
            tip="Open Vellum Study Builder",
            id="vellum-study-builder",
        )
        # Anki supplies Sync as the final item. Keep that familiar endpoint and
        # place Builder directly before it.
        links.insert(max(0, len(links) - 1), link)

    def _refresh_toolbar(self) -> None:
        toolbar = getattr(self._mw, "toolbar", None)
        draw = getattr(toolbar, "draw", None)
        if callable(draw):
            try:
                draw()
            except Exception:
                # Startup/profile teardown can briefly leave the WebView
                # unavailable. The next normal Anki redraw will apply the hook.
                self._logger.debug(
                    "Study Builder toolbar redraw deferred", exc_info=True
                )

    def _invalidate_catalog(self, *_args: Any) -> None:
        # Keep the immutable catalog already owned by an open builder. This
        # avoids a costly rebuild on every preview if a sync/tag operation
        # lands while the dialog is open. The next open gets a fresh catalog.
        if self._window is None:
            self._catalog_cache = None
        self._catalog_collection_key = ""
        self._collection_revision += 1
        self._preview_cache.clear()
        self._topic_deck_cache.clear()
        self._deck_tag_cache.clear()

    def _operation_did_execute(self, changes: Any, _handler: Any) -> None:
        # Preview counts depend on scheduling, suspension, tags, and deck
        # ownership. Never reuse a preview across a collection mutation.
        self._collection_revision += 1
        self._preview_cache.clear()
        self._topic_deck_cache.clear()
        self._deck_tag_cache.clear()
        if any(
            bool(getattr(changes, name, False))
            for name in ("tag", "deck", "notetype")
        ):
            self._invalidate_catalog()

    def _install_action(self) -> None:
        if self._action is not None:
            return
        from aqt.qt import QAction, qconnect  # type: ignore[import-not-found]

        self._action = QAction("Build Vellum Study Deck…", self._mw)
        qconnect(self._action.triggered, self.open)
        self._mw.addAction(self._action)

    def _inject_assets(self, web_content: Any, context: object | None) -> None:
        if context is None or context.__class__.__name__ != "Overview":
            return
        package = self._mw.addonManager.addonFromModule(self._package_name)
        path = f"/_addons/{package}/ui/assets/vellum.css"
        if path not in web_content.css:
            web_content.css.append(path)

    def _overview_content(self, _overview: Any, content: Any) -> None:
        config = self._config()
        content.table += (
            '<section class="vellum-overview" data-theme="'
            + config.general.theme
            + '" aria-label="Vellum Study Builder">'
            '<div class="vellum-overview__copy"><strong>Study Builder</strong>'
            '<span>Filter this collection by deck, topic, tag, state, or card text.</span>'
            '</div><div class="vellum-overview__presets">'
            '<button type="button" onclick="pycmd(\'vellum:overview:builder\')">'
            'Build Study Deck…</button></div></section>'
        )

    def _receive_message(
        self, handled: tuple[bool, Any], message: str, context: Any
    ) -> tuple[bool, Any]:
        if context.__class__.__name__ == "Overview" and message == "vellum:overview:builder":
            self.open()
            return (True, None)
        return handled

    def open(self) -> None:
        if not self._running:
            return
        saved = self._manager.repository.latest_generated_resumable()
        if saved is not None and saved.status not in TERMINAL_STATUSES:
            self._show_session_blocker(saved)
            return
        if self._window is not None and self._window.isVisible():
            self._window.raise_()
            self._window.activateWindow()
            return

        config = self._config()
        from ..ui.study_builder import show_study_builder

        cached_catalog = (
            self._catalog_cache
            if self._catalog_cache is not None
            and self._catalog_collection_key == self._collection_key
            else None
        )
        recipes = (
            self._recipes.list(self._collection_key)
            if cached_catalog is not None and self._collection_key
            else ()
        )
        recent = (
            self._recipes.recent(self._collection_key)
            if cached_catalog is not None and self._collection_key
            else ()
        )
        window = show_study_builder(
            self._mw,
            catalog=cached_catalog,
            recipes=recipes,
            recent_runs=recent,
            config=config.study_builder,
            on_topic_decks=self.topic_decks,
            on_deck_tags=self.deck_tags,
            on_preview=self.preview,
            on_build=self.build,
            on_save_recipe=self.save_recipe,
            on_delete_recipe=self.delete_recipe,
            on_open_browser=self.open_browser,
            on_tutorial_complete=self._tutorial_completed,
            on_closed=lambda: setattr(self, "_window", None),
        )
        self._window = window
        if cached_catalog is not None:
            return

        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def gather(collection: Any) -> tuple[str, BuilderCatalog]:
            key = collection_key(collection)
            if (
                self._catalog_cache is not None
                and self._catalog_collection_key == key
            ):
                return (key, self._catalog_cache)
            return (key, collect_builder_catalog(collection, config.topic_parsing))

        def ready(result: tuple[str, BuilderCatalog]) -> None:
            self._collection_key, catalog = result
            self._catalog_cache = catalog
            self._catalog_collection_key = self._collection_key
            if self._window is not window:
                return
            window.set_catalog(
                catalog=catalog,
                recipes=self._recipes.list(self._collection_key),
                recent_runs=self._recipes.recent(self._collection_key),
            )

        def failed(error: Exception) -> None:
            if self._window is window:
                setter = getattr(window, "set_loading_error", None)
                if callable(setter):
                    setter(str(error))
            self._query_failed(error)

        QueryOp(parent=self._mw, op=gather, success=ready).failure(failed).run_in_background()

    def _show_session_blocker(self, session: Session) -> None:
        from aqt.qt import QMessageBox  # type: ignore[import-not-found]

        box = QMessageBox(self._mw)
        box.setWindowTitle("Unfinished Vellum session")
        box.setText(
            f'“{session.deck_name or "Previous session"}” must be resolved before '
            "Study Builder can create another temporary deck."
        )
        box.setInformativeText(
            "Resume continues it. Finish returns remaining cards home and records "
            "completion. Abandon returns them home and records that it was abandoned."
        )
        resume = box.addButton("Resume", QMessageBox.ButtonRole.AcceptRole)
        finish = box.addButton("Finish", QMessageBox.ButtonRole.ActionRole)
        abandon = box.addButton("Abandon", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is resume:
            self._events.emit("resume_requested")
        elif clicked is finish:
            self._events.emit("generated_session_finish_requested")
        elif clicked is abandon:
            self._events.emit("generated_session_abandon_requested")

    def preview(
        self,
        definition: BuilderDefinition,
        generation: int,
        success: Callable[[BuilderPreview], None],
        failure: Callable[[Exception], None],
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        config = self._config()
        catalog = self._catalog_cache

        def gather(collection: Any) -> BuilderPreview:
            current_catalog = catalog or collect_builder_catalog(
                collection, config.topic_parsing
            )
            cache_key = (
                collection_key(collection),
                self._collection_revision,
                int(getattr(getattr(collection, "sched", None), "today", 0)),
                definition.to_json(),
                bool(config.study_builder.show_snippets),
            )
            cached = self._preview_cache.get(cache_key)
            if cached is not None:
                return replace(cached, generation=generation)
            value = collect_builder_preview(
                collection,
                definition,
                generation=generation,
                show_snippets=config.study_builder.show_snippets,
                catalog=current_catalog,
            )
            if len(self._preview_cache) >= 32:
                self._preview_cache.pop(next(iter(self._preview_cache)))
            self._preview_cache[cache_key] = value
            return value

        QueryOp(parent=self._mw, op=gather, success=success).failure(
            failure
        ).run_in_background()

    def topic_decks(
        self,
        topics: tuple[str, ...],
        generation: int,
        include_empty: bool,
        success: Callable[[TopicDeckScope], None],
        failure: Callable[[Exception], None],
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        normalized = tuple(sorted(dict.fromkeys(topics), key=str.casefold))
        cache_key = (self._collection_revision, normalized, bool(include_empty))

        def gather(collection: Any) -> TopicDeckScope:
            cached = self._topic_deck_cache.get(cache_key)
            if cached is not None:
                return replace(cached, generation=generation)
            result = collect_topic_deck_scope(
                collection,
                normalized,
                generation=generation,
                include_empty=include_empty,
            )
            if len(self._topic_deck_cache) >= 24:
                self._topic_deck_cache.pop(next(iter(self._topic_deck_cache)))
            self._topic_deck_cache[cache_key] = result
            return result

        QueryOp(parent=self._mw, op=gather, success=success).failure(
            failure
        ).run_in_background()

    def deck_tags(
        self,
        decks: tuple[str, ...],
        generation: int,
        success: Callable[[DeckTagScope], None],
        failure: Callable[[Exception], None],
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        normalized = tuple(sorted(dict.fromkeys(decks), key=str.casefold))
        cache_key = (self._collection_revision, normalized)
        catalog = self._catalog_cache

        def gather(collection: Any) -> DeckTagScope:
            cached = self._deck_tag_cache.get(cache_key)
            if cached is not None:
                return replace(cached, generation=generation)
            current_catalog = catalog or collect_builder_catalog(
                collection, self._config().topic_parsing
            )
            result = collect_deck_tag_scope(
                collection,
                normalized,
                current_catalog,
                generation=generation,
            )
            if len(self._deck_tag_cache) >= 24:
                self._deck_tag_cache.pop(next(iter(self._deck_tag_cache)))
            self._deck_tag_cache[cache_key] = result
            return result

        QueryOp(parent=self._mw, op=gather, success=success).failure(
            failure
        ).run_in_background()

    def _tutorial_completed(self) -> None:
        config = self._config()
        if config.study_builder.tutorial_version >= 1:
            return
        self._save_config(
            replace(
                config,
                study_builder=replace(config.study_builder, tutorial_version=1),
            )
        )

    def save_recipe(
        self,
        name: str,
        definition: BuilderDefinition,
        recipe_id: str | None = None,
    ) -> Any:
        return self._recipes.save(
            self._collection_key, name, definition, recipe_id=recipe_id
        )

    def delete_recipe(self, recipe_id: str) -> bool:
        return self._recipes.delete(self._collection_key, recipe_id)

    def open_browser(self, definition: BuilderDefinition) -> None:
        from aqt import dialogs  # type: ignore[import-not-found]
        from ..builder.query import compile_builder_query

        dialogs.open(
            "Browser", self._mw, search=(compile_builder_query(definition),)
        )

    def build(self, request: BuildRequest) -> None:
        """Re-evaluate immediately, then explicitly activate and build exact IDs."""

        if self._manager.repository.latest_generated_resumable() is not None:
            self._warn(
                "A generated session became active. Finish or abandon it before "
                "building this deck."
            )
            return
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        config = self._config()
        catalog = self._catalog_cache

        def gather(collection: Any) -> tuple[BuilderPreview, bool]:
            current_catalog = catalog or collect_builder_catalog(
                collection, config.topic_parsing
            )
            preview = collect_builder_preview(
                collection,
                request.definition,
                generation=request.generation,
                show_snippets=False,
                snippet_limit=0,
                catalog=current_catalog,
            )
            selected = request.selected_card_ids or preview.selected_card_ids
            return (
                preview,
                selected == preview.selected_card_ids
                and exact_selection_is_current(
                    collection, request.definition, selected
                ),
            )

        QueryOp(parent=self._mw, op=gather, success=lambda result: self._confirmed_build(request, *result)).failure(
            self._query_failed
        ).run_in_background()

    def _confirmed_build(
        self,
        request: BuildRequest,
        preview: BuilderPreview,
        selection_is_current: bool,
    ) -> None:
        if preview.unresolved_filters:
            self._warn(
                "One or more selected decks or tags disappeared after preview. "
                "Study Builder stopped instead of broadening the selection."
            )
            return
        selected = request.selected_card_ids or preview.selected_card_ids
        if not selection_is_current:
            self._warn(
                "The inspected selection changed before building. No cards were "
                "changed; review the refreshed preview and build again."
            )
            refresh = getattr(self._window, "refresh_preview", None)
            if callable(refresh):
                refresh()
            return
        if request.activate_suspended != request.definition.include_suspended:
            self._warn("The activation choice changed. Review the preview again.")
            return
        if not selected:
            self._warn("No eligible cards remain for this Study Builder run.")
            return
        suspended = set(preview.suspended_card_ids)
        activated = tuple(card_id for card_id in selected if card_id in suspended)
        preview = replace(
            preview,
            selected_card_ids=selected,
            selected_suspended_ids=activated,
        )
        if activated:
            from aqt.utils import askUser  # type: ignore[import-not-found]

            if not askUser(
                f"Permanently unsuspend {len(activated)} selected card(s)?\n\n"
                "They will remain active in their home decks after this session. "
                "Vellum will restore them only if deck creation fails before study begins.",
                parent=self._mw,
            ):
                return
            from aqt.operations.scheduling import unsuspend_cards  # type: ignore[import-not-found]

            unsuspend_cards(parent=self._mw, card_ids=list(activated)).success(
                lambda _changes: self._create(request, preview, activated)
            ).failure(self._query_failed).run_in_background()
            return
        self._create(request, preview, ())

    def _create(
        self,
        request: BuildRequest,
        preview: BuilderPreview,
        activated: tuple[int, ...],
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        def create(collection: Any) -> PreparedBuilderDeck:
            return create_builder_deck(collection, request, preview.selected_card_ids)

        QueryOp(parent=self._mw, op=create, success=lambda prepared: self._select_and_start(request, prepared, activated)).failure(
            lambda error: self._rollback_failure(error, None, None, activated)
        ).run_in_background()

    def _select_and_start(
        self,
        request: BuildRequest,
        prepared: PreparedBuilderDeck,
        activated: tuple[int, ...],
    ) -> None:
        from aqt.operations.deck import set_current_deck  # type: ignore[import-not-found]

        prepared = replace(
            prepared,
            result=replace(prepared.result, activated_card_ids=activated),
        )
        result = prepared.result
        set_current_deck(parent=self._mw, deck_id=result.deck_id).success(
            lambda _changes: self._start_session(request, prepared, activated)
        ).failure(
            lambda error: self._rollback_failure(
                error, result.deck_id, result.deck_name, activated
            )
        ).run_in_background()

    def _start_session(
        self,
        request: BuildRequest,
        prepared: PreparedBuilderDeck,
        activated: tuple[int, ...],
    ) -> None:
        result = prepared.result
        bucket_names = {
            "new": TimingBucket.NEW,
            "learning": TimingBucket.LEARNING,
            "review": TimingBucket.REVIEW,
            "relearning": TimingBucket.RELEARNING,
        }
        counts = {bucket: 0 for bucket in TimingBucket}
        for card in prepared.cards:
            counts[bucket_names.get(card.bucket or "review", TimingBucket.REVIEW)] += 1
        estimated_seconds = self._timing.estimate_counts_seconds(counts)
        query = "cid:" + ",".join(str(card.card_id) for card in prepared.cards)
        session = self._manager.start(
            deck_id=result.deck_id,
            deck_name=result.deck_name,
            query=query,
            origin=SessionOrigin.STUDY_BUILDER,
            starting_due_count=len(prepared.cards),
            estimated_total=len(prepared.cards),
            estimated_seconds=estimated_seconds,
        )
        try:
            self._generated_decks.create(
                session,
                feature="study_builder",
                cards=prepared.cards,
                scope="study-builder",
                metadata={
                    "recipe_id": request.recipe_id,
                    "state_preset": request.definition.state_preset.value,
                    "order": request.definition.order.value,
                    "activated_count": len(activated),
                    "debrief_topic_snapshots": True,
                },
            )
        except Exception as error:
            self._logger.exception("Unable to persist Study Builder manifest")
            self._manager.abandon_saved(session.id)
            self._rollback_failure(
                error, result.deck_id, result.deck_name, activated
            )
            return
        try:
            self._recipes.add_recent(
                self._collection_key,
                request.definition,
                recipe_id=request.recipe_id,
                metadata={"selected_count": len(prepared.cards)},
            )
            if request.recipe_id:
                self._recipes.mark_run(self._collection_key, request.recipe_id)
        except Exception:
            # The safety manifest and session already exist. Recent-history
            # convenience must never tear down an otherwise valid study run.
            self._logger.exception("Unable to update Study Builder recipe history")
        self._events.emit("study_builder_started", session)
        from aqt.utils import tooltip  # type: ignore[import-not-found]

        tooltip(
            f"Study Builder created · {len(prepared.cards)} cards",
            parent=self._mw,
        )
        if self._window is not None:
            self._window.close()
        self._mw.moveToState("review")

    def _rollback_failure(
        self,
        error: Exception,
        deck_id: int | None,
        deck_name: str | None,
        activated: tuple[int, ...],
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        QueryOp(
            parent=self._mw,
            op=lambda collection: rollback_builder_start(
                collection,
                deck_id=deck_id,
                deck_name=deck_name,
                activated_card_ids=activated,
            ),
            success=lambda _result: self._query_failed(error),
        ).failure(self._query_failed).run_in_background()

    def finish_current(self) -> None:
        session = self._manager.current
        if (
            session is None
            or session.origin is not SessionOrigin.STUDY_BUILDER
            or session.deck_id is None
            or not session.deck_name
        ):
            from aqt.utils import tooltip  # type: ignore[import-not-found]

            tooltip("No active Study Builder session", parent=self._mw)
            return
        from aqt.utils import askUser  # type: ignore[import-not-found]

        if not askUser(
            "Finish this Study Builder session? Remaining cards will return to "
            "their home decks, and answered-card scheduling will be preserved.",
            parent=self._mw,
        ):
            return
        self._remove_owned_deck(session, manual_finish=True)

    def _reviewer_ended(self) -> None:
        session = self._manager.current
        if (
            session is None
            or session.origin is not SessionOrigin.STUDY_BUILDER
            or session.deck_id is None
            or not session.deck_name
        ):
            return
        self._remove_owned_deck(session, manual_finish=False, only_if_empty=True)

    def _remove_owned_deck(
        self,
        session: Session,
        *,
        manual_finish: bool,
        only_if_empty: bool = False,
    ) -> None:
        from aqt.operations import QueryOp  # type: ignore[import-not-found]

        deck_id = int(session.deck_id or 0)
        deck_name = str(session.deck_name or "")
        session_id = session.id

        def inspect(collection: Any) -> bool:
            if not (
                bool(collection.decks.is_filtered(deck_id))
                and collection.decks.name_if_exists(deck_id) == deck_name
            ):
                return False
            return (
                owned_builder_deck_is_empty(collection, deck_id, deck_name)
                if only_if_empty
                else True
            )

        def checked(owned: bool) -> None:
            if not owned:
                if not only_if_empty:
                    self._warn(
                        "Vellum refused to remove this deck because its saved identity "
                        "no longer matches the Study Builder session."
                    )
                return
            from aqt.operations.deck import remove_decks  # type: ignore[import-not-found]

            def removed(_changes: Any) -> None:
                self._generated_decks.mark_removed(
                    session_id, reason="finished" if manual_finish else "exhausted"
                )
                current = self._manager.current
                if manual_finish:
                    finalized = self._manager.complete_saved(session_id)
                    self._mw.moveToState("deckBrowser")
                elif (
                    current is not None
                    and current.id == session_id
                    and current.status not in TERMINAL_STATUSES
                ):
                    finalized = self._manager.complete_saved(session_id)
                else:
                    finalized = self._manager.repository.get(session_id)
                self._events.emit(
                    "study_builder_completed",
                    finalized,
                )
                if finalized is not None:
                    self._events.emit("session_finalized", finalized)

            remove_decks(
                parent=self._mw,
                deck_ids=[deck_id],
                deck_name=deck_name,
            ).success(removed).run_in_background()

        QueryOp(parent=self._mw, op=inspect, success=checked).failure(
            self._query_failed
        ).run_in_background()

    def _query_failed(self, error: Exception) -> None:
        self._logger.error(
            "Study Builder operation failed",
            exc_info=(type(error), error, error.__traceback__),
        )
        self._warn(f"Study Builder could not complete this operation: {error}")

    def _warn(self, message: str) -> None:
        from aqt.utils import showWarning  # type: ignore[import-not-found]

        showWarning(message, parent=self._mw)
