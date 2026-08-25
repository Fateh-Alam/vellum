"""Guided, two-path native Study Builder window."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from ..builder.catalog import BuilderCatalog, CatalogFacet
from ..builder.models import (
    BuildRequest,
    BuilderDefinition,
    BuilderOrder,
    BuilderPreview,
    BuilderQuickFilters,
    BuilderSelectionPolicy,
    BuilderWorkflow,
    FilterOperator,
    RecentBuilderRun,
    StatePreset,
    StudyRecipe,
)
from ..builder.scope import DeckScopeNode, DeckTagScope, ScopedTagNode, TopicDeckScope
from ..core.config import StudyBuilderConfig
from .theme import apply_secondary_text


TUTORIAL_VERSION = 1
VALUE_ROLE = 256
PATH_ROLE = 257


def _natural_join(values: tuple[str, ...], word: str = "or") -> str:
    clean = tuple(dict.fromkeys(value for value in values if value))
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]} {word} {clean[1]}"
    return ", ".join(clean[:-1]) + f", {word} {clean[-1]}"


def _pruned_hierarchy(current: set[str], values: tuple[str, ...]) -> set[str]:
    """A newly selected child replaces its ancestor, and vice versa."""

    result = set(current)
    for value in values:
        result = {
            candidate
            for candidate in result
            if not (
                candidate == value
                or candidate.startswith(value + "::")
                or value.startswith(candidate + "::")
            )
        }
    result.update(values)
    return result


def show_study_builder(
    parent: Any,
    *,
    catalog: BuilderCatalog | None,
    recipes: tuple[StudyRecipe, ...],
    recent_runs: tuple[RecentBuilderRun, ...],
    config: StudyBuilderConfig,
    on_topic_decks: Callable[
        [tuple[str, ...], int, bool, Callable[..., None], Callable[..., None]], None
    ],
    on_deck_tags: Callable[
        [tuple[str, ...], int, Callable[..., None], Callable[..., None]], None
    ],
    on_preview: Callable[
        [BuilderDefinition, int, Callable[..., None], Callable[..., None]], None
    ],
    on_build: Callable[[BuildRequest], None],
    on_save_recipe: Callable[[str, BuilderDefinition, str | None], StudyRecipe],
    on_delete_recipe: Callable[[str], bool],
    on_open_browser: Callable[[BuilderDefinition], None],
    on_tutorial_complete: Callable[[], None],
    on_closed: Callable[[], None],
) -> Any:
    from aqt.qt import (  # type: ignore[import-not-found]
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QDialog,
        QFrame,
        QHeaderView,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QPalette,
        QPushButton,
        QSpinBox,
        QStackedWidget,
        QTimer,
        QToolButton,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
        Qt,
        qconnect,
    )
    from aqt.utils import askUser, showWarning, tooltip  # type: ignore[import-not-found]

    active_catalog = [catalog or BuilderCatalog()]
    recipe_items: list[StudyRecipe] = list(recipes)
    loaded_recipe: list[StudyRecipe | None] = [None]
    current_preview: list[BuilderPreview | None] = [None]
    current_workflow = [BuilderWorkflow.FIND_TOPICS]
    legacy_definition: list[BuilderDefinition | None] = [None]

    selected_find_topics: set[str] = set()
    selected_find_decks: set[str] = set()
    selected_browse_decks: set[str] = set()
    selected_browse_tags: set[str] = set()
    topic_choices: dict[tuple[str, ...], CatalogFacet] = {}
    browse_tag_nodes: list[tuple[ScopedTagNode, ...]] = [()]
    pending_recipe_decks: list[tuple[str, ...]] = [()]
    pending_recipe_tags: list[tuple[str, ...]] = [()]

    topic_generation = [0]
    tag_generation = [0]
    preview_generation = [0]
    tree_guard = [False]
    include_entire_deck = [False]
    include_empty_decks = [False]
    include_suspended = [False]
    one_card_per_note = [False]
    new_share_percent: list[int | None] = [None]
    selected_order = [
        BuilderOrder(config.default_order)
        if config.default_order in {item.value for item in BuilderOrder}
        else BuilderOrder.DUE
    ]
    quick_filters = [BuilderQuickFilters()]

    class StudyBuilderWindow(QMainWindow):
        def closeEvent(self, event: Any) -> None:
            on_closed()
            super().closeEvent(event)

        def set_catalog(
            self,
            *,
            catalog: BuilderCatalog,
            recipes: tuple[StudyRecipe, ...],
            recent_runs: tuple[RecentBuilderRun, ...],
        ) -> None:
            active_catalog[0] = catalog
            recipe_items[:] = list(recipes)
            recent_items[:] = list(recent_runs)
            loading_label.setText("Choose how you want to build this study deck.")
            find_mode.setEnabled(True)
            browse_mode.setEnabled(True)
            populate_recipe_combo()

        def set_loading_error(self, message: str) -> None:
            loading_label.setText("Vellum could not read this collection’s topics.")
            loading_label.setToolTip(message)

        def refresh_preview(self) -> None:
            schedule_preview()

    recent_items: list[RecentBuilderRun] = list(recent_runs)
    window = StudyBuilderWindow(parent)
    window.setWindowTitle("Vellum Study Builder")
    window.setMinimumSize(1024, 680)
    window.setAccessibleName("Vellum Study Builder")

    central = QWidget(window)
    central.setObjectName("builderRoot")
    window.setCentralWidget(central)
    is_dark = (
        window.palette().color(QPalette.ColorRole.Window).lightness() < 128
    )
    colors = (
        {
            "background": "#181817",
            "surface": "#232321",
            "surface_alt": "#2c2a27",
            "border": "#3b3935",
            "text": "#f3f1ed",
            "muted": "#aaa69f",
            "accent": "#b7ad9d",
            "accent_text": "#211f1c",
            "accent_soft": "#36322c",
        }
        if is_dark
        else {
            "background": "#f6f5f1",
            "surface": "#ffffff",
            "surface_alt": "#eeece6",
            "border": "#d8d4cb",
            "text": "#211f1c",
            "muted": "#6f6a62",
            "accent": "#6f6658",
            "accent_text": "#ffffff",
            "accent_soft": "#e9e5de",
        }
    )
    window.setStyleSheet(
        f"""
        QWidget#builderRoot {{ background: {colors['background']}; color: {colors['text']}; }}
        QFrame#modeCard, QFrame#focusPanel {{
            background: {colors['surface']}; border: 1px solid {colors['border']};
            border-radius: 16px;
        }}
        QFrame#pathRail {{
            background: {colors['surface_alt']}; border: 0; border-radius: 14px;
        }}
        QFrame#scopeCard {{
            background: {colors['accent_soft']}; border: 0; border-radius: 11px;
        }}
        QFrame#builderFooter {{
            background: {colors['surface']}; border: 1px solid {colors['border']};
            border-radius: 12px;
        }}
        QPushButton {{
            min-height: 30px; padding: 5px 12px; border: 1px solid {colors['border']};
            border-radius: 8px; background: {colors['surface']}; color: {colors['text']};
        }}
        QPushButton:hover {{ background: {colors['accent_soft']}; }}
        QPushButton#primaryButton {{
            min-height: 36px; background: {colors['accent']}; color: {colors['accent_text']};
            border-color: {colors['accent']}; font-weight: 700; padding: 7px 16px;
        }}
        QPushButton#primaryButton:hover {{ background: {colors['accent']}; }}
        QPushButton#ghostButton {{ border: 0; background: transparent; padding-left: 0; }}
        QLineEdit, QComboBox, QSpinBox {{
            min-height: 30px; padding: 3px 8px; border: 1px solid {colors['border']};
            border-radius: 7px; background: {colors['surface']}; color: {colors['text']};
        }}
        QLineEdit#builderSearch {{ min-height: 38px; font-size: 15px; padding: 4px 12px; }}
        QListWidget#builderList, QTreeWidget#builderTree {{
            background: {colors['surface']}; color: {colors['text']};
            border: 1px solid {colors['border']}; border-radius: 10px;
            alternate-background-color: {colors['background']}; outline: 0;
        }}
        QListWidget#builderList::item {{ padding: 9px 8px; border-bottom: 1px solid {colors['border']}; }}
        QListWidget#builderList::item:hover, QTreeWidget#builderTree::item:hover {{
            background: {colors['accent_soft']};
        }}
        QTreeWidget#builderTree::item {{ min-height: 32px; padding: 2px 5px; }}
        QHeaderView::section {{
            background: {colors['surface_alt']}; color: {colors['muted']};
            border: 0; border-bottom: 1px solid {colors['border']};
            padding: 7px 9px; font-weight: 700;
        }}
        QToolButton#helpButton {{
            border: 1px solid {colors['border']}; border-radius: 11px;
            background: {colors['surface']}; color: {colors['muted']}; font-weight: 700;
        }}
        """
    )
    outer = QVBoxLayout(central)
    outer.setContentsMargins(26, 20, 26, 18)
    outer.setSpacing(14)

    def question_help(text: str, name: str) -> Any:
        button = QToolButton()
        button.setObjectName("helpButton")
        button.setText("?")
        button.setAutoRaise(True)
        button.setFixedSize(22, 22)
        button.setToolTip(text)
        button.setAccessibleName(name)
        return button

    header = QHBoxLayout()
    title_widget = QWidget()
    title_widget.setMinimumWidth(300)
    title_widget.setMinimumHeight(52)
    title_box = QVBoxLayout(title_widget)
    title_box.setContentsMargins(0, 0, 0, 0)
    title = QLabel("Study Builder")
    title.setStyleSheet("font-size: 25px; font-weight: 750;")
    subtitle = QLabel("Choose what the cards are about, where they come from, then study.")
    subtitle.setWordWrap(True)
    apply_secondary_text(subtitle)
    title_box.addWidget(title)
    title_box.addWidget(subtitle)
    header.addWidget(title_widget, 1)

    recipes_combo = QComboBox()
    recipes_combo.setMinimumWidth(210)
    recipes_combo.setAccessibleName("Saved Study Builder decks")
    recipes_combo.setToolTip("Open a saved Study Builder recipe")
    header.addWidget(recipes_combo)
    save_recipe_button = QPushButton("Save")
    save_recipe_button.setToolTip("Save this scope so it can be rebuilt later")
    save_recipe_button.setVisible(False)
    header.addWidget(save_recipe_button)
    tutorial_button = question_help(
        "Open the guided tour for Find Topics and Browse Collection.",
        "How Study Builder works",
    )
    header.addWidget(tutorial_button)
    outer.addLayout(header)

    pages = QStackedWidget()
    outer.addWidget(pages, 1)

    welcome = QWidget()
    welcome_layout = QVBoxLayout(welcome)
    welcome_layout.setContentsMargins(70, 34, 70, 70)
    welcome_layout.addStretch(1)
    welcome_title = QLabel("How do you want to find your cards?")
    welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    welcome_title.setStyleSheet("font-size: 26px; font-weight: 750;")
    welcome_layout.addWidget(welcome_title)
    loading_label = QLabel(
        "Preparing your local topic index…"
        if catalog is None
        else "Choose how you want to build this study deck."
    )
    loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    apply_secondary_text(loading_label)
    welcome_layout.addWidget(loading_label)
    welcome_layout.addSpacing(24)
    mode_row = QHBoxLayout()
    mode_row.setSpacing(20)

    def mode_card(title_text: str, body: str, action: str) -> tuple[Any, Any]:
        frame = QFrame()
        frame.setObjectName("modeCard")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setMinimumSize(300, 210)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(26, 24, 26, 24)
        heading = QLabel(title_text)
        heading.setStyleSheet("font-size: 20px; font-weight: 750;")
        description = QLabel(body)
        description.setWordWrap(True)
        apply_secondary_text(description)
        button = QPushButton(action)
        button.setObjectName("primaryButton")
        button.setMinimumHeight(38)
        button.setStyleSheet("font-size: 15px;")
        layout.addWidget(heading)
        layout.addWidget(description)
        layout.addStretch(1)
        layout.addWidget(button)
        return frame, button

    find_card, find_mode = mode_card(
        "Find Topics",
        "Search one or more topics, then choose the decks they should come from.",
        "Start with topics →",
    )
    find_mode.setAccessibleName("Find Topics workflow")
    browse_card, browse_mode = mode_card(
        "Browse Collection",
        "Choose decks first, then explore only the tags that exist inside them.",
        "Start with decks →",
    )
    browse_mode.setAccessibleName("Browse Collection workflow")
    find_mode.setEnabled(catalog is not None)
    browse_mode.setEnabled(catalog is not None)
    mode_row.addWidget(find_card)
    mode_row.addWidget(browse_card)
    welcome_layout.addLayout(mode_row)
    welcome_layout.addStretch(2)
    pages.addWidget(welcome)

    workspace = QWidget()
    workspace_layout = QVBoxLayout(workspace)
    workspace_layout.setContentsMargins(0, 0, 0, 0)
    workspace_layout.setSpacing(12)

    workspace_header = QHBoxLayout()
    back_to_modes = QPushButton("‹ Choose another path")
    back_to_modes.setObjectName("ghostButton")
    back_to_modes.setToolTip("Return to the two Study Builder workflows")
    workspace_header.addWidget(back_to_modes)
    mode_title = QLabel("")
    mode_title.setStyleSheet("font-size: 19px; font-weight: 700;")
    workspace_header.addWidget(mode_title)
    workspace_header.addStretch(1)
    open_browser = QPushButton("Open in Browser")
    open_browser.setToolTip("Open the exact current scope in Anki’s Browser")
    open_browser.setVisible(False)
    workspace_header.addWidget(open_browser)
    workspace_layout.addLayout(workspace_header)

    scope_card = QFrame()
    scope_card.setObjectName("scopeCard")
    scope_card.setFrameShape(QFrame.Shape.StyledPanel)
    scope_layout = QHBoxLayout(scope_card)
    scope_layout.setContentsMargins(14, 10, 14, 10)
    scope_caption = QLabel("CURRENT SCOPE")
    scope_caption.setStyleSheet("font-size: 11px; font-weight: 700;")
    scope_label = QLabel("Start with step 1")
    scope_label.setWordWrap(True)
    scope_label.setStyleSheet("font-size: 15px; font-weight: 650;")
    scope_layout.addWidget(scope_caption)
    scope_layout.addWidget(scope_label, 1)
    workspace_layout.addWidget(scope_card)

    body = QHBoxLayout()
    body.setSpacing(16)
    workspace_layout.addLayout(body, 1)

    rail = QFrame()
    rail.setObjectName("pathRail")
    rail.setFrameShape(QFrame.Shape.StyledPanel)
    rail.setFixedWidth(230)
    rail_layout = QVBoxLayout(rail)
    rail_layout.setContentsMargins(14, 16, 14, 16)
    rail_layout.setSpacing(8)
    rail_caption = QLabel("YOUR PATH")
    rail_caption.setStyleSheet("font-size: 11px; font-weight: 750;")
    rail_layout.addWidget(rail_caption)
    rail_mode = QLabel("")
    rail_mode.setStyleSheet("font-size: 17px; font-weight: 750;")
    rail_mode.setWordWrap(True)
    rail_layout.addWidget(rail_mode)
    rail_layout.addSpacing(12)

    def rail_button(text: str) -> Any:
        button = QPushButton(text)
        button.setMinimumHeight(54)
        button.setStyleSheet(
            "QPushButton { text-align: left; padding: 10px 12px; "
            f"border: none; border-radius: 9px; font-weight: 650; background: transparent; color: {colors['text']}; }}"
            f"QPushButton:hover {{ background: {colors['accent_soft']}; }}"
        )
        return button

    def polish_tree(tree: Any, *, count_width: int = 76) -> None:
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(1, count_width)
        tree.setIndentation(17)

    step_one = rail_button("1   Choose")
    step_two = rail_button("2   Refine")
    step_three = rail_button("3   Inspect cards")
    step_two.setEnabled(False)
    step_three.setEnabled(False)
    rail_layout.addWidget(step_one)
    rail_layout.addWidget(step_two)
    rail_layout.addWidget(step_three)
    rail_layout.addStretch(1)
    rail_note = QLabel(
        "One step at a time. Vellum keeps the Anki query out of your way."
    )
    rail_note.setWordWrap(True)
    apply_secondary_text(rail_note)
    rail_layout.addWidget(rail_note)
    body.addWidget(rail)

    focus_panel = QFrame()
    focus_panel.setObjectName("focusPanel")
    focus_panel.setFrameShape(QFrame.Shape.StyledPanel)
    focus_layout = QVBoxLayout(focus_panel)
    focus_layout.setContentsMargins(28, 24, 28, 24)
    focus_layout.setSpacing(12)
    focus_step = QLabel("STEP 1")
    focus_step.setStyleSheet("font-size: 11px; font-weight: 750;")
    focus_title = QLabel("Choose topics")
    focus_title.setStyleSheet("font-size: 24px; font-weight: 750;")
    focus_description = QLabel("")
    focus_description.setWordWrap(True)
    apply_secondary_text(focus_description)
    focus_layout.addWidget(focus_step)
    focus_layout.addWidget(focus_title)
    focus_layout.addWidget(focus_description)
    focus_stack = QStackedWidget()
    focus_layout.addWidget(focus_stack, 1)
    body.addWidget(focus_panel, 1)

    preview_page = QWidget()
    preview_layout = QVBoxLayout(preview_page)
    preview_layout.setContentsMargins(0, 0, 0, 0)
    preview_layout.setSpacing(10)

    def show_stage(index: int, number: int, title_text: str, description: str) -> None:
        focus_stack.setCurrentIndex(index)
        focus_step.setText(f"STEP {number}")
        focus_title.setText(title_text)
        focus_description.setText(description)
        for position, button in enumerate((step_one, step_two, step_three), 1):
            button.setStyleSheet(
                "QPushButton { text-align: left; padding: 10px 12px; border: none; "
                "border-radius: 9px; font-weight: 700; "
                + (
                    f"background: {colors['accent']}; color: {colors['accent_text']}; }}"
                    if position == number
                    else f"background: transparent; color: {colors['text']}; }} "
                    f"QPushButton:hover {{ background: {colors['accent_soft']}; }}"
                )
            )

    find_topics_page = QWidget()
    find_topics_layout = QVBoxLayout(find_topics_page)
    find_topics_layout.setContentsMargins(0, 0, 0, 0)
    topic_help_row = QHBoxLayout()
    topic_intro = QLabel("Search topic and tag names—not card text.")
    topic_intro.setWordWrap(True)
    apply_secondary_text(topic_intro)
    topic_help_row.addWidget(topic_intro, 1)
    topic_help_row.addWidget(
        question_help(
            "You can select several topic paths. They are treated as alternatives.",
            "Explain topic selection",
        )
    )
    find_topics_layout.addLayout(topic_help_row)
    topic_search = QLineEdit()
    topic_search.setObjectName("builderSearch")
    topic_search.setPlaceholderText("Try renal, Pathoma, First Aid, high yield…")
    topic_search.setClearButtonEnabled(True)
    topic_search.setAccessibleName("Find topics and tags")
    find_topics_layout.addWidget(topic_search)
    topic_results = QListWidget()
    topic_results.setObjectName("builderList")
    topic_results.setAccessibleName("Matching topics and tag paths")
    topic_results.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    topic_results.setWordWrap(True)
    topic_results.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    find_topics_layout.addWidget(topic_results, 1)
    selected_topics_label = QLabel("No topics selected yet")
    selected_topics_label.setWordWrap(True)
    selected_topics_label.setStyleSheet("font-weight: 650;")
    find_topics_layout.addWidget(selected_topics_label)
    clear_topics = QPushButton("Clear topics")
    clear_topics.setVisible(False)
    find_topics_layout.addWidget(clear_topics)
    find_topics_continue = QPushButton("Continue to source decks →")
    find_topics_continue.setObjectName("primaryButton")
    find_topics_continue.setEnabled(False)
    find_topics_continue.setMinimumHeight(40)
    find_topics_continue.setStyleSheet("font-weight: 700;")
    find_topics_layout.addWidget(find_topics_continue)
    focus_stack.addWidget(find_topics_page)

    browse_decks_page = QWidget()
    browse_decks_layout = QVBoxLayout(browse_decks_page)
    browse_decks_layout.setContentsMargins(0, 0, 0, 0)
    browse_deck_intro = QLabel(
        "Check a parent deck to include its subdecks. Use the arrow only to look inside."
    )
    browse_deck_intro.setWordWrap(True)
    apply_secondary_text(browse_deck_intro)
    browse_decks_layout.addWidget(browse_deck_intro)
    browse_deck_tree = QTreeWidget()
    browse_deck_tree.setObjectName("builderTree")
    browse_deck_tree.setHeaderLabels(("Deck", "Cards"))
    browse_deck_tree.setAccessibleName("Source deck tree")
    browse_deck_tree.setAlternatingRowColors(True)
    browse_deck_tree.setStyleSheet("QTreeView::item { min-height: 30px; }")
    polish_tree(browse_deck_tree)
    browse_decks_layout.addWidget(browse_deck_tree, 1)
    browse_decks_continue = QPushButton("Continue to tags →")
    browse_decks_continue.setObjectName("primaryButton")
    browse_decks_continue.setEnabled(False)
    browse_decks_continue.setMinimumHeight(40)
    browse_decks_continue.setStyleSheet("font-weight: 700;")
    browse_decks_layout.addWidget(browse_decks_continue)
    focus_stack.addWidget(browse_decks_page)

    find_decks_page = QWidget()
    find_decks_layout = QVBoxLayout(find_decks_page)
    find_decks_layout.setContentsMargins(0, 0, 0, 0)
    find_deck_status = QLabel("Choose a topic first")
    find_deck_status.setWordWrap(True)
    apply_secondary_text(find_deck_status)
    find_decks_layout.addWidget(find_deck_status)
    show_empty_decks = QCheckBox("Show empty decks")
    show_empty_decks.setToolTip("Also show decks containing none of the selected topics")
    show_empty_decks.setVisible(False)
    find_decks_layout.addWidget(show_empty_decks)
    find_deck_tree = QTreeWidget()
    find_deck_tree.setObjectName("builderTree")
    find_deck_tree.setHeaderLabels(("Deck", "Matches"))
    find_deck_tree.setAccessibleName("Decks containing selected topics")
    find_deck_tree.setAlternatingRowColors(True)
    find_deck_tree.setStyleSheet("QTreeView::item { min-height: 30px; }")
    polish_tree(find_deck_tree, count_width=84)
    find_decks_layout.addWidget(find_deck_tree, 1)
    find_decks_continue = QPushButton("Inspect matching cards →")
    find_decks_continue.setObjectName("primaryButton")
    find_decks_continue.setAccessibleName("Inspect Find Topics cards")
    find_decks_continue.setEnabled(False)
    find_decks_continue.setMinimumHeight(40)
    find_decks_continue.setStyleSheet("font-weight: 700;")
    find_decks_layout.addWidget(find_decks_continue)
    focus_stack.addWidget(find_decks_page)

    browse_tags_page = QWidget()
    browse_tags_layout = QVBoxLayout(browse_tags_page)
    browse_tags_layout.setContentsMargins(0, 0, 0, 0)
    browse_tag_status = QLabel("Choose at least one source deck first")
    browse_tag_status.setWordWrap(True)
    apply_secondary_text(browse_tag_status)
    browse_tags_layout.addWidget(browse_tag_status)
    tag_controls = QHBoxLayout()
    tag_search = QLineEdit()
    tag_search.setObjectName("builderSearch")
    tag_search.setPlaceholderText("Filter tags in this deck scope…")
    tag_search.setClearButtonEnabled(True)
    tag_search.setAccessibleName("Filter scoped tags")
    tag_search.setEnabled(False)
    show_all_tags = QCheckBox("All tags")
    show_all_tags.setToolTip("Reveal maintenance and update tags hidden from the normal tree")
    show_all_tags.setEnabled(False)
    tag_controls.addWidget(tag_search, 1)
    tag_controls.addWidget(show_all_tags)
    browse_tags_layout.addLayout(tag_controls)
    browse_tag_tree = QTreeWidget()
    browse_tag_tree.setObjectName("builderTree")
    browse_tag_tree.setHeaderLabels(("Tag path", "Cards"))
    browse_tag_tree.setAccessibleName("Tags found in selected decks")
    browse_tag_tree.setAlternatingRowColors(True)
    browse_tag_tree.setStyleSheet("QTreeView::item { min-height: 30px; }")
    polish_tree(browse_tag_tree)
    browse_tags_layout.addWidget(browse_tag_tree, 1)
    entire_deck_button = QPushButton("Study entire selected deck scope")
    entire_deck_button.setCheckable(True)
    entire_deck_button.setToolTip(
        "Skip tag selection and build from all cards in the selected decks"
    )
    entire_deck_button.setEnabled(False)
    browse_tags_layout.addWidget(entire_deck_button)
    browse_tags_continue = QPushButton("Inspect matching cards →")
    browse_tags_continue.setObjectName("primaryButton")
    browse_tags_continue.setAccessibleName("Inspect Browse Collection cards")
    browse_tags_continue.setEnabled(False)
    browse_tags_continue.setMinimumHeight(40)
    browse_tags_continue.setStyleSheet("font-weight: 700;")
    browse_tags_layout.addWidget(browse_tags_continue)
    focus_stack.addWidget(browse_tags_page)

    legacy_first = QWidget()
    legacy_first_layout = QVBoxLayout(legacy_first)
    legacy_first_layout.setContentsMargins(0, 0, 0, 0)
    legacy_title = QLabel("Legacy combination")
    legacy_title.setStyleSheet("font-size: 17px; font-weight: 700;")
    legacy_text = QLabel(
        "This saved recipe used the previous advanced grouping model. Vellum keeps its exact meaning and will not regroup it automatically."
    )
    legacy_text.setWordWrap(True)
    legacy_first_layout.addWidget(legacy_title)
    legacy_first_layout.addWidget(legacy_text)
    legacy_rules = QListWidget()
    legacy_rules.setAccessibleName("Legacy Study Builder rules")
    legacy_first_layout.addWidget(legacy_rules, 1)
    focus_stack.addWidget(legacy_first)
    legacy_second_text = QLabel(
        "Use Open in Browser for deep editing. Building here preserves the saved query exactly."
    )
    legacy_second_text.setWordWrap(True)
    apply_secondary_text(legacy_second_text)
    legacy_first_layout.addWidget(legacy_second_text)

    preview_summary = QLabel("Finish steps 1 and 2 to inspect matching cards")
    preview_summary.setWordWrap(True)
    preview_summary.setStyleSheet("font-weight: 650;")
    preview_layout.addWidget(preview_summary)
    preview_hint = QLabel(
        "Card previews are inspect-only. Scheduling remains controlled by Anki and FSRS."
    )
    preview_hint.setWordWrap(True)
    apply_secondary_text(preview_hint)
    preview_layout.addWidget(preview_hint)
    preview_list = QListWidget()
    preview_list.setObjectName("builderList")
    preview_list.setAccessibleName("Matching card previews")
    preview_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    preview_list.setSpacing(5)
    preview_list.setWordWrap(True)
    preview_list.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    preview_layout.addWidget(preview_list, 1)
    preview_diagnostic = QLabel("")
    preview_diagnostic.setWordWrap(True)
    preview_diagnostic.setVisible(False)
    preview_layout.addWidget(preview_diagnostic)
    focus_stack.addWidget(preview_page)

    pages.addWidget(workspace)

    footer = QFrame()
    footer.setObjectName("builderFooter")
    footer.setFrameShape(QFrame.Shape.StyledPanel)
    footer_layout = QHBoxLayout(footer)
    footer_layout.setContentsMargins(14, 10, 14, 10)
    footer_layout.addWidget(QLabel("Cards"))
    state_combo = QComboBox()
    for label, state in (
        ("Due + new", StatePreset.DUE_NEW),
        ("Due only", StatePreset.DUE),
        ("New only", StatePreset.NEW),
        ("All matching", StatePreset.ALL),
    ):
        state_combo.addItem(label, state)
    state_combo.setAccessibleName("Cards to include")
    default_state = next(
        (
            index
            for index in range(state_combo.count())
            if state_combo.itemData(index).value == config.default_state_preset
        ),
        0,
    )
    state_combo.setCurrentIndex(default_state)
    footer_layout.addWidget(state_combo)
    footer_layout.addWidget(
        question_help(
            "Due + new follows normal scheduling. All matching can bring cards forward, but answers still reschedule normally.",
            "Explain included card states",
        )
    )
    more_options = QPushButton("More options…")
    more_options.setToolTip("Ordering, sibling handling, new-card share, and suspended cards")
    footer_layout.addWidget(more_options)
    footer_layout.addStretch(1)
    footer_layout.addWidget(QLabel("Limit"))
    limit = QSpinBox()
    limit.setRange(1, 2_147_483_647)
    limit.setValue(config.default_limit)
    limit.setSuffix(" cards")
    limit.setAccessibleName("Maximum cards to build")
    footer_layout.addWidget(limit)
    build_button = QPushButton("Choose a scope")
    build_button.setObjectName("primaryButton")
    build_button.setEnabled(False)
    build_button.setMinimumWidth(180)
    build_button.setStyleSheet("font-weight: 750; padding: 8px 18px;")
    footer_layout.addWidget(build_button)
    workspace_layout.addWidget(footer)

    topic_timer = QTimer(window)
    topic_timer.setSingleShot(True)
    topic_timer.setInterval(180)
    tag_timer = QTimer(window)
    tag_timer.setSingleShot(True)
    tag_timer.setInterval(180)
    preview_timer = QTimer(window)
    preview_timer.setSingleShot(True)
    preview_timer.setInterval(220)

    def topic_label(facet: CatalogFacet) -> str:
        path = " › ".join(facet.path) or facet.label
        badges = " + ".join(facet.scope_badges)
        suffix = f"  [{badges}]" if badges else ""
        return f"{path}{suffix}  —  {facet.group}"

    def find_topic_names() -> tuple[str, ...]:
        labels: list[str] = []
        for facet in topic_choices.values():
            label = " › ".join(facet.path) or facet.label
            if label not in labels:
                labels.append(label)
        return tuple(labels)

    def selected_decks() -> tuple[str, ...]:
        values = (
            selected_find_decks
            if current_workflow[0] is BuilderWorkflow.FIND_TOPICS
            else selected_browse_decks
        )
        return tuple(sorted(values, key=str.casefold))

    def selected_tags() -> tuple[str, ...]:
        values = (
            selected_find_topics
            if current_workflow[0] is BuilderWorkflow.FIND_TOPICS
            else selected_browse_tags
        )
        return tuple(sorted(values, key=str.casefold))

    def definition() -> BuilderDefinition:
        if legacy_definition[0] is not None:
            value = legacy_definition[0]
            return replace(
                value,
                state_preset=state_combo.currentData(),
                order=selected_order[0],
                limit=limit.value(),
                include_suspended=include_suspended[0],
                selection_policy=BuilderSelectionPolicy(
                    one_card_per_note[0], new_share_percent[0]
                ),
            )
        return BuilderDefinition(
            definition_version=3,
            workflow=current_workflow[0],
            topic_tags=selected_tags(),
            source_decks=selected_decks(),
            include_entire_deck_scope=(
                current_workflow[0] is BuilderWorkflow.BROWSE_COLLECTION
                and include_entire_deck[0]
            ),
            state_preset=state_combo.currentData(),
            order=selected_order[0],
            limit=limit.value(),
            include_suspended=include_suspended[0],
            quick_filters=quick_filters[0],
            selection_policy=BuilderSelectionPolicy(
                one_card_per_note[0], new_share_percent[0]
            ),
        )

    def valid_scope() -> bool:
        if legacy_definition[0] is not None:
            return not legacy_definition[0].empty_scope
        if not selected_decks():
            return False
        if current_workflow[0] is BuilderWorkflow.FIND_TOPICS:
            return bool(selected_find_topics)
        return bool(selected_browse_tags) or include_entire_deck[0]

    def update_scope_label() -> None:
        if legacy_definition[0] is not None:
            scope_label.setText("Saved legacy combination — exact rules preserved")
            return
        decks = tuple(value.split("::")[-1] for value in selected_decks())
        if current_workflow[0] is BuilderWorkflow.FIND_TOPICS:
            topics = find_topic_names()
            if not topics:
                scope_label.setText("Choose one or more topics")
            elif not decks:
                scope_label.setText(f"{_natural_join(topics)} — now choose source decks")
            else:
                scope_label.setText(
                    f"{_natural_join(topics)} from {_natural_join(decks)}"
                )
        else:
            if not decks:
                scope_label.setText("Choose parent decks or subdecks")
            elif include_entire_deck[0]:
                scope_label.setText(f"All cards from {_natural_join(decks)}")
            elif not selected_browse_tags:
                scope_label.setText(
                    f"{_natural_join(decks)} — now choose tags inside this scope"
                )
            else:
                tag_names = tuple(
                    node.label
                    for node in browse_tag_nodes[0]
                    if any(value in selected_browse_tags for value in node.values)
                )
                scope_label.setText(
                    f"{_natural_join(tag_names or ('Selected tags',))} from {_natural_join(decks)}"
                )

    def set_item_checked(item: Any, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        try:
            item.setCheckState(state)
        except TypeError:
            item.setCheckState(0, state)

    def populate_deck_tree(
        tree: Any,
        nodes: tuple[DeckScopeNode, ...],
        selected: set[str],
    ) -> None:
        tree_guard[0] = True
        tree.clear()
        items: dict[tuple[str, ...], Any] = {}
        by_path = {node.path: node for node in nodes}
        for node in nodes:
            parent_item = None
            for depth in range(1, len(node.path) + 1):
                path = node.path[:depth]
                item = items.get(path)
                if item is None:
                    source = by_path.get(path)
                    value = "::".join(path)
                    count = source.total_count if source is not None else 0
                    item = QTreeWidgetItem((path[-1], f"{count:,}" if count else ""))
                    item.setData(0, VALUE_ROLE, (value,))
                    item.setData(0, PATH_ROLE, path)
                    item.setToolTip(0, " › ".join(path))
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    set_item_checked(item, value in selected)
                    if parent_item is None:
                        tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    items[path] = item
                parent_item = item
        tree_guard[0] = False
        tree.expandToDepth(0)
        tree.setColumnWidth(1, 72)

    def refresh_deck_checks(tree: Any, selected: set[str]) -> None:
        tree_guard[0] = True
        stack = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            values = tuple(item.data(0, VALUE_ROLE) or ())
            set_item_checked(item, bool(values) and all(value in selected for value in values))
            stack.extend(item.child(index) for index in range(item.childCount()))
        tree_guard[0] = False

    def populate_topic_results() -> None:
        topic_results.clear()
        text = topic_search.text().strip()
        if not text:
            item = QListWidgetItem("Search a topic or resource name to begin")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            topic_results.addItem(item)
            return
        facets = active_catalog[0].search_topics(text, limit=16)
        if not facets:
            item = QListWidgetItem("No topic or tag name matches this search")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            topic_results.addItem(item)
            return
        for facet in facets:
            item = QListWidgetItem(topic_label(facet))
            item.setData(VALUE_ROLE, facet.values)
            item.setData(PATH_ROLE, facet)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            set_item_checked(item, all(value in selected_find_topics for value in facet.values))
            topic_results.addItem(item)

    def update_selected_topics() -> None:
        names = find_topic_names()
        selected_topics_label.setText(
            "Selected: " + _natural_join(names) if names else "No topics selected yet"
        )
        clear_topics.setVisible(bool(names))
        find_topics_continue.setEnabled(bool(names))
        if current_workflow[0] is BuilderWorkflow.FIND_TOPICS:
            step_two.setEnabled(bool(names))
        update_scope_label()

    def topic_selection_changed(item: Any) -> None:
        facet = item.data(PATH_ROLE)
        if not isinstance(facet, CatalogFacet):
            return
        values = facet.values
        checked = all(value in selected_find_topics for value in values)
        if checked:
            selected_find_topics.difference_update(values)
            topic_choices.pop(values, None)
        else:
            before = set(selected_find_topics)
            replacement = _pruned_hierarchy(selected_find_topics, values)
            removed = before - replacement
            selected_find_topics.clear()
            selected_find_topics.update(replacement)
            for key in tuple(topic_choices):
                if any(value in removed for value in key):
                    topic_choices.pop(key, None)
            topic_choices[values] = facet
        selected_find_decks.clear()
        current_preview[0] = None
        populate_topic_results()
        update_selected_topics()
        find_deck_tree.clear()
        if selected_find_topics:
            find_deck_status.setText("Finding decks that contain these topics…")
            show_empty_decks.setVisible(False)
            topic_timer.start()
        else:
            find_deck_status.setText("Choose a topic first")
            show_empty_decks.setVisible(False)
        clear_preview()

    def request_topic_decks() -> None:
        if not selected_find_topics:
            return
        topic_generation[0] += 1
        generation = topic_generation[0]
        on_topic_decks(
            tuple(sorted(selected_find_topics, key=str.casefold)),
            generation,
            include_empty_decks[0],
            receive_topic_decks,
            lambda error: scope_failed(error, find_deck_status),
        )

    def receive_topic_decks(result: TopicDeckScope) -> None:
        if result.generation != topic_generation[0]:
            return
        valid_values = {node.value for node in result.decks}
        selected_find_decks.intersection_update(valid_values)
        selected_find_decks.update(
            value for value in pending_recipe_decks[0] if value in valid_values
        )
        pending_recipe_decks[0] = ()
        populate_deck_tree(find_deck_tree, result.decks, selected_find_decks)
        find_deck_status.setText(
            f"{len(result.decks):,} relevant decks · {result.total_count:,} matching cards"
            if result.decks
            else "No deck contains the selected topics"
        )
        show_empty_decks.setVisible(True)
        update_scope_label()
        schedule_preview()

    def all_deck_nodes() -> tuple[DeckScopeNode, ...]:
        return tuple(
            DeckScopeNode(facet.value, facet.label, facet.path, 0)
            for facet in active_catalog[0].decks
        )

    def deck_item_changed(item: Any, _column: int, selected: set[str], tree: Any) -> None:
        if tree_guard[0]:
            return
        values = tuple(item.data(0, VALUE_ROLE) or ())
        if not values:
            return
        checked = item.checkState(0) is Qt.CheckState.Checked
        if checked:
            updated = _pruned_hierarchy(selected, values)
            selected.clear()
            selected.update(updated)
        else:
            selected.difference_update(values)
        refresh_deck_checks(tree, selected)
        if tree is browse_deck_tree:
            browse_decks_changed()
        else:
            find_decks_continue.setEnabled(bool(selected_find_decks))
            step_three.setEnabled(valid_scope())
            update_scope_label()
            schedule_preview()

    def browse_decks_changed() -> None:
        selected_browse_tags.clear()
        include_entire_deck[0] = False
        entire_deck_button.setChecked(False)
        browse_tag_tree.clear()
        current_preview[0] = None
        update_scope_label()
        clear_preview()
        enabled = bool(selected_browse_decks)
        tag_search.setEnabled(enabled)
        show_all_tags.setEnabled(enabled)
        entire_deck_button.setEnabled(enabled)
        browse_decks_continue.setEnabled(enabled)
        if current_workflow[0] is BuilderWorkflow.BROWSE_COLLECTION:
            step_two.setEnabled(enabled)
            step_three.setEnabled(False)
        if enabled:
            browse_tag_status.setText("Reading the tags used in this deck scope…")
            tag_timer.start()
        else:
            browse_tag_status.setText("Choose at least one source deck first")

    def request_deck_tags() -> None:
        if not selected_browse_decks:
            return
        tag_generation[0] += 1
        generation = tag_generation[0]
        on_deck_tags(
            tuple(sorted(selected_browse_decks, key=str.casefold)),
            generation,
            receive_deck_tags,
            lambda error: scope_failed(error, browse_tag_status),
        )

    def receive_deck_tags(result: DeckTagScope) -> None:
        if result.generation != tag_generation[0]:
            return
        browse_tag_nodes[0] = result.tags
        available = {value for node in result.tags for value in node.values}
        selected_browse_tags.intersection_update(available)
        selected_browse_tags.update(
            value for value in pending_recipe_tags[0] if value in available
        )
        pending_recipe_tags[0] = ()
        browse_tag_status.setText(
            f"{len(result.tags):,} tag paths found · {result.total_count:,} cards in scope"
            if result.tags
            else f"No tags found · {result.total_count:,} cards can still be studied as an entire deck scope"
        )
        populate_tag_tree()
        browse_tags_continue.setEnabled(valid_scope())
        step_three.setEnabled(valid_scope())
        update_scope_label()
        schedule_preview()

    def populate_tag_tree() -> None:
        tree_guard[0] = True
        browse_tag_tree.clear()
        query_words = tuple(part.casefold() for part in tag_search.text().split() if part)
        show_hidden = show_all_tags.isChecked()
        section_items: dict[str, Any] = {}
        path_items: dict[tuple[str, tuple[str, ...]], Any] = {}
        for node in browse_tag_nodes[0]:
            if node.hidden and not show_hidden:
                continue
            searchable = " ".join((*node.path, node.label, node.section)).casefold()
            if query_words and not all(word in searchable for word in query_words):
                continue
            section = node.section or "All tags"
            visible_path = (
                node.path[1:]
                if len(node.path) > 1
                and node.path[0].casefold() == section.casefold()
                else node.path
            )
            section_item = section_items.get(section)
            if section_item is None:
                section_item = QTreeWidgetItem((section, ""))
                section_item.setFlags(
                    section_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable
                )
                browse_tag_tree.addTopLevelItem(section_item)
                section_items[section] = section_item
            parent = section_item
            for depth in range(1, len(visible_path) + 1):
                path = visible_path[:depth]
                key = (section, path)
                item = path_items.get(key)
                if item is None:
                    terminal = depth == len(visible_path)
                    item = QTreeWidgetItem(
                        (path[-1], f"{node.total_count:,}" if terminal else "")
                    )
                    if terminal:
                        item.setData(0, VALUE_ROLE, node.values)
                        item.setData(0, PATH_ROLE, node.path)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        set_item_checked(
                            item,
                            all(value in selected_browse_tags for value in node.values),
                        )
                        badges = " + ".join(node.badges)
                        path_tooltip = " › ".join((section, *node.path))
                        item.setToolTip(
                            0,
                            path_tooltip
                            + (f" · Available in {badges}" if badges else ""),
                        )
                    parent.addChild(item)
                    path_items[key] = item
                parent = item
        tree_guard[0] = False
        browse_tag_tree.expandToDepth(1)
        browse_tag_tree.setColumnWidth(1, 64)

    def tag_item_changed(item: Any, _column: int) -> None:
        if tree_guard[0]:
            return
        values = tuple(item.data(0, VALUE_ROLE) or ())
        if not values:
            return
        if item.checkState(0) is Qt.CheckState.Checked:
            updated = _pruned_hierarchy(selected_browse_tags, values)
            selected_browse_tags.clear()
            selected_browse_tags.update(updated)
            include_entire_deck[0] = False
            entire_deck_button.setChecked(False)
        else:
            selected_browse_tags.difference_update(values)
        populate_tag_tree()
        browse_tags_continue.setEnabled(valid_scope())
        step_three.setEnabled(valid_scope())
        update_scope_label()
        schedule_preview()

    def scope_failed(error: Exception, label: Any) -> None:
        label.setText("Vellum could not read this scope")
        label.setToolTip(str(error))

    def clear_preview() -> None:
        current_preview[0] = None
        preview_list.clear()
        preview_summary.setText("Finish steps 1 and 2 to inspect matching cards")
        preview_diagnostic.setVisible(False)
        build_button.setText("Choose a scope")
        build_button.setEnabled(False)
        open_browser.setVisible(valid_scope())
        step_three.setEnabled(valid_scope())

    def schedule_preview() -> None:
        update_scope_label()
        if not valid_scope():
            clear_preview()
            return
        preview_summary.setText("Checking availability…")
        preview_list.clear()
        build_button.setText("Checking…")
        build_button.setEnabled(False)
        open_browser.setVisible(True)
        preview_timer.start()

    def request_preview() -> None:
        if not valid_scope():
            return
        preview_generation[0] += 1
        generation = preview_generation[0]
        on_preview(
            definition(),
            generation,
            receive_preview,
            lambda error: preview_failed(error, generation),
        )

    def receive_preview(result: BuilderPreview) -> None:
        if result.generation != preview_generation[0]:
            return
        current_preview[0] = result
        preview_summary.setText(
            f"{result.total_count:,} matches · {result.ready_count:,} ready · "
            f"{result.suspended_count:,} suspended · {result.buried_count:,} buried · "
            f"{result.filtered_count:,} elsewhere"
        )
        preview_list.clear()
        for card in result.cards:
            snippet = card.snippet or "Card preview hidden"
            tags = " · ".join(tag.split("::")[-1] for tag in card.tags[:3])
            metadata = " · ".join(
                value for value in (card.deck_name, card.state, tags) if value
            )
            item = QListWidgetItem(f"{snippet}\n{metadata}")
            if card.suspended:
                item.setToolTip("Suspended — included only after explicit activation")
            preview_list.addItem(item)
        diagnostic = result.diagnostic
        preview_diagnostic.setVisible(diagnostic is not None)
        preview_diagnostic.setText(diagnostic.message if diagnostic else "")
        can_build = bool(result.selected_card_ids) and not result.unresolved_filters
        step_three.setEnabled(True)
        build_button.setEnabled(can_build)
        build_button.setText("Build && Study" if can_build else "Nothing ready")

    def preview_failed(error: Exception, generation: int) -> None:
        if generation != preview_generation[0]:
            return
        preview_summary.setText("Vellum could not preview this scope")
        preview_summary.setToolTip(str(error))
        build_button.setText("Preview unavailable")

    def choose_workflow(workflow: BuilderWorkflow) -> None:
        current_workflow[0] = workflow
        legacy_definition[0] = None
        pages.setCurrentWidget(workspace)
        save_recipe_button.setVisible(True)
        if workflow is BuilderWorkflow.FIND_TOPICS:
            mode_title.setText("Find Topics")
            rail_mode.setText("Find Topics")
            step_one.setText("1   Choose topics")
            step_two.setText("2   Choose decks")
            step_three.setText("3   Inspect cards")
            step_two.setEnabled(bool(selected_find_topics))
            step_three.setEnabled(valid_scope())
            show_stage(
                0,
                1,
                "Choose topics",
                "Search topic and tag names. Select several when any of them would be useful.",
            )
            update_selected_topics()
        else:
            mode_title.setText("Browse Collection")
            rail_mode.setText("Browse Collection")
            step_one.setText("1   Choose decks")
            step_two.setText("2   Explore tags")
            step_three.setText("3   Inspect cards")
            step_two.setEnabled(bool(selected_browse_decks))
            step_three.setEnabled(valid_scope())
            show_stage(
                1,
                1,
                "Choose source decks",
                "Check a parent deck for its full scope, or open it and choose specific subdecks.",
            )
            populate_deck_tree(
                browse_deck_tree, all_deck_nodes(), selected_browse_decks
            )
            update_scope_label()
        clear_preview()
        if valid_scope():
            schedule_preview()

    def show_options_dialog() -> None:
        dialog = QDialog(window)
        dialog.setWindowTitle("Study Builder options")
        layout = QVBoxLayout(dialog)
        explanation = QLabel(
            "These choices affect which cards are selected, not Anki’s scheduler."
        )
        explanation.setWordWrap(True)
        apply_secondary_text(explanation)
        layout.addWidget(explanation)
        layout.addWidget(QLabel("Order"))
        order_combo = QComboBox()
        for label, value in (
            ("Due first", BuilderOrder.DUE),
            ("Most at risk", BuilderOrder.MOST_AT_RISK),
            ("Most lapses", BuilderOrder.MOST_LAPSES),
            ("Oldest seen", BuilderOrder.OLDEST_SEEN),
            ("Added order", BuilderOrder.ADDED),
            ("Random", BuilderOrder.RANDOM),
        ):
            order_combo.addItem(label, value)
        order_combo.setCurrentIndex(
            next(
                index
                for index in range(order_combo.count())
                if order_combo.itemData(index) is selected_order[0]
            )
        )
        layout.addWidget(order_combo)
        siblings = QCheckBox("Avoid sibling cards")
        siblings.setChecked(one_card_per_note[0])
        siblings.setToolTip("Select at most one card from each note")
        layout.addWidget(siblings)
        activate = QCheckBox("Unsuspend and include selected suspended cards")
        activate.setChecked(include_suspended[0])
        activate.setToolTip("Requires exact confirmation before permanent activation")
        layout.addWidget(activate)
        layout.addWidget(QLabel("New-card share for Due + new"))
        share = QComboBox()
        share.addItem("Natural", None)
        for percent in (25, 50, 75):
            share.addItem(f"{percent}%", percent)
        share.setCurrentIndex(
            next(
                (
                    index
                    for index in range(share.count())
                    if share.itemData(index) == new_share_percent[0]
                ),
                0,
            )
        )
        layout.addWidget(share)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        done = QPushButton("Done")
        actions.addWidget(cancel)
        actions.addWidget(done)
        layout.addLayout(actions)
        qconnect(cancel.clicked, dialog.reject)

        def apply_options() -> None:
            selected_order[0] = order_combo.currentData()
            one_card_per_note[0] = siblings.isChecked()
            include_suspended[0] = activate.isChecked()
            new_share_percent[0] = share.currentData()
            dialog.accept()
            schedule_preview()

        qconnect(done.clicked, apply_options)
        dialog.exec()

    def show_tutorial() -> None:
        guide = QDialog(window)
        guide.setWindowTitle("How Study Builder works")
        guide.setModal(True)
        guide.resize(640, 480)
        layout = QVBoxLayout(guide)
        heading = QLabel("Two simple ways to reach the cards you want")
        heading.setStyleSheet("font-size: 22px; font-weight: 750;")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        intro = QLabel(
            "You never need to write an Anki query. Choose a route, inspect the result, and Vellum builds a scheduled filtered deck."
        )
        intro.setWordWrap(True)
        apply_secondary_text(intro)
        layout.addWidget(intro)
        for number, title_text, body in (
            (
                1,
                "Find Topics",
                "Search topic or tag names, select alternatives, then choose only the decks that contain them.",
            ),
            (
                2,
                "Browse Collection",
                "Choose parent decks or subdecks first. Vellum then shows the tag tree actually present inside that scope.",
            ),
            (
                3,
                "Inspect, then study",
                "Review the exact availability and card previews. Build & Study keeps Anki and FSRS in charge of every answer.",
            ),
        ):
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card_layout = QVBoxLayout(card)
            label = QLabel(f"{number}. {title_text}")
            label.setStyleSheet("font-size: 16px; font-weight: 700;")
            text = QLabel(body)
            text.setWordWrap(True)
            card_layout.addWidget(label)
            card_layout.addWidget(text)
            layout.addWidget(card)
        layout.addStretch(1)
        done = QPushButton("Got it")
        done.setDefault(True)
        layout.addWidget(done, alignment=Qt.AlignmentFlag.AlignRight)

        def finish() -> None:
            on_tutorial_complete()
            guide.accept()

        qconnect(done.clicked, finish)
        guide.finished.connect(lambda _result: on_tutorial_complete())
        guide.exec()

    def populate_recipe_combo() -> None:
        recipes_combo.blockSignals(True)
        recipes_combo.clear()
        recipes_combo.addItem("Saved study decks…", None)
        for recipe in recipe_items:
            recipes_combo.addItem(recipe.name, recipe.recipe_id)
        recipes_combo.insertSeparator(recipes_combo.count())
        for recent in recent_items[:5]:
            recipes_combo.addItem(
                "Recent · " + recent.definition.workflow.value.replace("_", " ").title(),
                recent,
            )
        recipes_combo.blockSignals(False)

    def apply_common_definition(value: BuilderDefinition) -> None:
        state_index = next(
            (
                index
                for index in range(state_combo.count())
                if state_combo.itemData(index) is value.state_preset
            ),
            0,
        )
        state_combo.setCurrentIndex(state_index)
        limit.setValue(value.limit)
        selected_order[0] = value.order
        include_suspended[0] = value.include_suspended
        one_card_per_note[0] = value.selection_policy.one_card_per_note
        new_share_percent[0] = value.selection_policy.new_share_percent
        quick_filters[0] = value.quick_filters

    def load_definition(value: BuilderDefinition, recipe: StudyRecipe | None = None) -> None:
        loaded_recipe[0] = recipe
        apply_common_definition(value)
        selected_find_topics.clear()
        selected_find_decks.clear()
        selected_browse_decks.clear()
        selected_browse_tags.clear()
        topic_choices.clear()
        include_entire_deck[0] = False
        legacy_definition[0] = None
        if value.definition_version < 3:
            legacy_definition[0] = value
            pages.setCurrentWidget(workspace)
            mode_title.setText("Legacy combination")
            rail_mode.setText("Legacy combination")
            step_one.setText("Saved rules")
            step_two.setEnabled(False)
            step_three.setEnabled(True)
            show_stage(
                4,
                1,
                "Saved legacy rules",
                "This recipe keeps its previous query meaning exactly.",
            )
            legacy_rules.clear()
            for group in value.filter_groups:
                operator = " OR " if group.operator is FilterOperator.ANY else " AND "
                legacy_rules.addItem(
                    operator.join(
                        f"{selector.kind}: {selector.value}" for selector in group.selectors
                    )
                )
            save_recipe_button.setVisible(True)
            update_scope_label()
            schedule_preview()
            return
        if value.workflow is BuilderWorkflow.FIND_TOPICS:
            for raw in value.topic_tags:
                facet = active_catalog[0].find("topic", raw) or active_catalog[0].find("tag", raw)
                if facet is None:
                    continue
                selected_find_topics.update(facet.values)
                topic_choices[facet.values] = facet
            pending_recipe_decks[0] = value.source_decks
            choose_workflow(BuilderWorkflow.FIND_TOPICS)
            update_selected_topics()
            if selected_find_topics:
                find_deck_status.setText("Finding decks that contain these topics…")
                topic_timer.start()
        else:
            selected_browse_decks.update(value.source_decks)
            pending_recipe_tags[0] = value.topic_tags
            choose_workflow(BuilderWorkflow.BROWSE_COLLECTION)
            populate_deck_tree(browse_deck_tree, all_deck_nodes(), selected_browse_decks)
            browse_decks_changed()
            include_entire_deck[0] = value.include_entire_deck_scope
            entire_deck_button.setChecked(include_entire_deck[0])

    def recipe_chosen(index: int) -> None:
        data = recipes_combo.itemData(index)
        if isinstance(data, RecentBuilderRun):
            load_definition(data.definition)
            return
        recipe = next((item for item in recipe_items if item.recipe_id == data), None)
        if recipe is not None:
            load_definition(recipe.definition, recipe)

    def save_recipe() -> None:
        if not valid_scope():
            showWarning("Choose a complete Study Builder scope before saving.", parent=window)
            return
        existing = loaded_recipe[0]
        default_name = existing.name if existing else ""
        name, accepted = QInputDialog.getText(
            window,
            "Save Study Builder deck",
            "Name",
            text=default_name,
        )
        if not accepted or not name.strip():
            return
        try:
            saved = on_save_recipe(
                name.strip(), definition(), existing.recipe_id if existing else None
            )
        except Exception as error:
            showWarning(str(error), parent=window)
            return
        if existing is None:
            recipe_items.append(saved)
        else:
            recipe_items[:] = [
                saved if item.recipe_id == saved.recipe_id else item
                for item in recipe_items
            ]
        loaded_recipe[0] = saved
        populate_recipe_combo()
        tooltip("Study deck saved", parent=window)

    def build() -> None:
        preview = current_preview[0]
        if preview is None or not preview.selected_card_ids:
            return
        value = definition()
        if value.state_preset is StatePreset.ALL and not askUser(
            "All matching can bring cards forward from their normal schedule. Answers will still reschedule normally. Continue?",
            parent=window,
        ):
            return
        if value.include_entire_deck_scope and not value.topic_tags and not askUser(
            f"Build from the entire selected deck scope, limited to {value.limit:,} cards?",
            parent=window,
        ):
            return
        labels = find_topic_names()
        if not labels:
            labels = tuple(deck.split("::")[-1] for deck in value.source_decks)
        deck_name = "Vellum Study - " + (labels[0] if labels else "Custom")
        on_build(
            BuildRequest(
                value,
                deck_name,
                loaded_recipe[0].recipe_id if loaded_recipe[0] else None,
                preview.generation,
                preview.selected_card_ids,
                value.include_suspended,
            )
        )

    def clear_all_topics() -> None:
        selected_find_topics.clear()
        selected_find_decks.clear()
        topic_choices.clear()
        populate_topic_results()
        update_selected_topics()
        find_deck_tree.clear()
        find_deck_status.setText("Choose a topic first")
        show_empty_decks.setVisible(False)
        find_topics_continue.setEnabled(False)
        find_decks_continue.setEnabled(False)
        step_two.setEnabled(False)
        step_three.setEnabled(False)
        clear_preview()

    def toggle_empty_decks(checked: bool) -> None:
        include_empty_decks[0] = checked
        find_deck_status.setText("Refreshing the source deck tree…")
        topic_timer.start()

    def toggle_entire_deck(checked: bool) -> None:
        include_entire_deck[0] = checked
        if checked:
            selected_browse_tags.clear()
            populate_tag_tree()
        browse_tags_continue.setEnabled(valid_scope())
        step_three.setEnabled(valid_scope())
        update_scope_label()
        schedule_preview()

    def show_first_step() -> None:
        if current_workflow[0] is BuilderWorkflow.FIND_TOPICS:
            show_stage(
                0,
                1,
                "Choose topics",
                "Search topic and tag names. Select several when any of them would be useful.",
            )
        else:
            show_stage(
                1,
                1,
                "Choose source decks",
                "Check a parent deck for its full scope, or open it and choose specific subdecks.",
            )

    def show_second_step() -> None:
        if current_workflow[0] is BuilderWorkflow.FIND_TOPICS:
            show_stage(
                2,
                2,
                "Choose source decks",
                "Only decks containing the selected topics are shown. Counts include their subdecks.",
            )
        else:
            show_stage(
                3,
                2,
                "Explore tags in scope",
                "These are the tag paths actually used by cards in your selected decks.",
            )

    def show_preview_step() -> None:
        if not valid_scope():
            return
        show_stage(
            5,
            3,
            "Inspect matching cards",
            "Check exact availability and a few card previews before building.",
        )

    qconnect(find_mode.clicked, lambda: choose_workflow(BuilderWorkflow.FIND_TOPICS))
    qconnect(browse_mode.clicked, lambda: choose_workflow(BuilderWorkflow.BROWSE_COLLECTION))
    qconnect(back_to_modes.clicked, lambda: pages.setCurrentWidget(welcome))
    qconnect(topic_search.textChanged, populate_topic_results)
    qconnect(topic_results.itemClicked, topic_selection_changed)
    qconnect(clear_topics.clicked, clear_all_topics)
    qconnect(find_topics_continue.clicked, show_second_step)
    qconnect(browse_decks_continue.clicked, show_second_step)
    qconnect(find_decks_continue.clicked, show_preview_step)
    qconnect(browse_tags_continue.clicked, show_preview_step)
    qconnect(step_one.clicked, show_first_step)
    qconnect(step_two.clicked, show_second_step)
    qconnect(step_three.clicked, show_preview_step)
    qconnect(show_empty_decks.toggled, toggle_empty_decks)
    find_deck_tree.itemChanged.connect(
        lambda item, column: deck_item_changed(
            item, column, selected_find_decks, find_deck_tree
        )
    )
    browse_deck_tree.itemChanged.connect(
        lambda item, column: deck_item_changed(
            item, column, selected_browse_decks, browse_deck_tree
        )
    )
    qconnect(tag_search.textChanged, populate_tag_tree)
    qconnect(show_all_tags.toggled, populate_tag_tree)
    browse_tag_tree.itemChanged.connect(tag_item_changed)
    qconnect(entire_deck_button.toggled, toggle_entire_deck)
    qconnect(state_combo.currentIndexChanged, schedule_preview)
    qconnect(limit.valueChanged, schedule_preview)
    qconnect(more_options.clicked, show_options_dialog)
    qconnect(open_browser.clicked, lambda: on_open_browser(definition()))
    qconnect(build_button.clicked, build)
    qconnect(save_recipe_button.clicked, save_recipe)
    qconnect(recipes_combo.currentIndexChanged, recipe_chosen)
    qconnect(tutorial_button.clicked, show_tutorial)
    qconnect(topic_timer.timeout, request_topic_decks)
    qconnect(tag_timer.timeout, request_deck_tags)
    qconnect(preview_timer.timeout, request_preview)

    populate_recipe_combo()
    populate_topic_results()
    if config.tutorial_version < TUTORIAL_VERSION:
        QTimer.singleShot(300, show_tutorial)
    window.showMaximized()
    return window
