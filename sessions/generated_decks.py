"""Durable local manifests for every filtered deck Vellum creates."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Mapping

from ..core.db import Database
from .models import Session, SessionStatus


@dataclass(frozen=True)
class GeneratedDeckCard:
    card_id: int
    note_id: int | None
    original_deck_id: int | None
    original_deck_name: str | None
    queue_position: int
    bucket: str | None = None
    answered_at: int | None = None
    rating: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class GeneratedDeckAnswer:
    card_id: int
    answered_at: int
    rating: int
    duration_ms: int | None = None


@dataclass(frozen=True)
class GeneratedDeckHistory:
    history_id: str
    session_id: str
    feature: str
    deck_id: int
    deck_name: str
    scope: str | None
    target_seconds: int | None
    created_at: int
    ended_at: int | None
    removed_at: int | None
    status: str
    removal_reason: str | None
    planned_card_count: int
    answered_card_count: int
    metadata: Mapping[str, Any]
    cards: tuple[GeneratedDeckCard, ...] = ()
    answers: tuple[GeneratedDeckAnswer, ...] = ()


class GeneratedDeckHistoryRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def create(
        self,
        session: Session,
        *,
        feature: str,
        cards: tuple[GeneratedDeckCard, ...],
        scope: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        planned_card_count: int | None = None,
    ) -> GeneratedDeckHistory:
        if session.deck_id is None or not session.deck_name:
            raise ValueError("Generated deck history requires a concrete deck")
        if not cards:
            raise ValueError("Generated deck history requires at least one card")
        history_id = session.id
        with self._database.locked() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO generated_deck_history(
                        history_id, session_id, feature, deck_id, deck_name,
                        scope, target_seconds, created_at, status,
                        planned_card_count, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        history_id,
                        session.id,
                        feature,
                        session.deck_id,
                        session.deck_name,
                        scope,
                        session.target_seconds,
                        session.started_at,
                        session.status.value,
                        max(len(cards), int(planned_card_count or 0)),
                        json.dumps(dict(metadata or {}), separators=(",", ":")),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO generated_deck_cards(
                        history_id, card_id, note_id, original_deck_id,
                        original_deck_name, queue_position, bucket
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            history_id,
                            card.card_id,
                            card.note_id,
                            card.original_deck_id,
                            card.original_deck_name,
                            card.queue_position,
                            card.bucket,
                        )
                        for card in cards
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        created = self.get(history_id)
        assert created is not None
        return created

    def backfill_session(
        self, collection: Any, session: Session
    ) -> GeneratedDeckHistory | None:
        """Reconstruct history for a pre-history generated deck on upgrade.

        Answered cards are recovered from Vellum's existing session checkpoints;
        unanswered cards are read from the still-owned filtered deck. No note
        fields or card text are read.
        """

        existing = self.get(session.id)
        if existing is not None:
            return existing
        if session.deck_id is None or not session.deck_name:
            return None
        with self._database.locked() as connection:
            answer_rows = list(
                connection.execute(
                    """
                    SELECT card_id, reviewed_at, rating, duration_ms
                    FROM session_cards
                    WHERE session_id = ?
                    ORDER BY reviewed_at
                    """,
                    (session.id,),
                )
            )
        deck_owned = (
            bool(collection.decks.is_filtered(session.deck_id))
            and collection.decks.name_if_exists(session.deck_id) == session.deck_name
        )
        remaining_ids = (
            tuple(
                int(row[0])
                for row in collection.db.all(
                    "select id from cards where did = ? order by due, id",
                    session.deck_id,
                )
            )
            if deck_owned
            else ()
        )
        ordered_ids: list[int] = []
        seen: set[int] = set()
        for card_id in (
            *(int(row["card_id"]) for row in answer_rows),
            *remaining_ids,
        ):
            if card_id not in seen:
                seen.add(card_id)
                ordered_ids.append(card_id)
        cards: list[GeneratedDeckCard] = []
        state_names = {0: "new", 1: "learning", 2: "review", 3: "relearning"}
        for position, card_id in enumerate(ordered_ids, start=1):
            try:
                card = collection.get_card(card_id)
            except Exception:
                continue
            current_deck_id = int(getattr(card, "did", 0) or 0)
            original_deck_id = int(getattr(card, "odid", 0) or 0) or (
                current_deck_id if current_deck_id != session.deck_id else None
            )
            original_deck_name = None
            if original_deck_id is not None:
                try:
                    original_deck_name = str(
                        collection.decks.name(original_deck_id)
                    )
                except Exception:
                    pass
            cards.append(
                GeneratedDeckCard(
                    card_id=card_id,
                    note_id=int(getattr(card, "nid", 0) or 0) or None,
                    original_deck_id=original_deck_id,
                    original_deck_name=original_deck_name,
                    queue_position=position,
                    bucket=state_names.get(int(getattr(card, "type", 2))),
                )
            )
        if not cards:
            return None
        expected = session.starting_due_count
        manifest_complete = expected is None or len(cards) >= expected
        history = self.create(
            session,
            feature=session.origin.value,
            cards=tuple(cards),
            scope=session.query,
            metadata={
                "legacy_backfill": True,
                "manifest_complete": manifest_complete,
                "original_starting_due_count": expected,
            },
            planned_card_count=expected,
        )
        for answer in answer_rows:
            self.record_answer(
                session.id,
                card_id=int(answer["card_id"]),
                answered_at=int(answer["reviewed_at"]),
                rating=int(answer["rating"] or 0),
                duration_ms=(
                    int(answer["duration_ms"])
                    if answer["duration_ms"] is not None
                    else None
                ),
            )
        self.mark_status(session)
        return self.get(history.history_id)

    def backfill_sessions(
        self, collection: Any, sessions: tuple[Session, ...]
    ) -> int:
        created = 0
        for session in sessions:
            history = self.get(session.id)
            if history is None:
                history = self.backfill_session(collection, session)
                if history is not None:
                    created += 1
            if history is None:
                continue
            self._cleanup_terminal_deck(collection, session, history)
        return created

    def _cleanup_terminal_deck(
        self,
        collection: Any,
        session: Session,
        history: GeneratedDeckHistory,
    ) -> bool:
        """Remove a terminal generated deck after its manifest is durable.

        This also repairs an interrupted prior cleanup on the next profile
        open. Deck identity is verified by both the immutable recorded ID and
        exact name before Vellum removes anything.
        """

        if session.status not in {
            SessionStatus.COMPLETED,
            SessionStatus.ABANDONED,
        } or history.removed_at is not None:
            return False
        deck_owned = (
            bool(collection.decks.is_filtered(session.deck_id))
            and collection.decks.name_if_exists(session.deck_id)
            == session.deck_name
        )
        if deck_owned:
            collection.decks.remove([session.deck_id])
            reason = "startup_terminal_cleanup"
        else:
            reason = (
                "legacy_already_removed"
                if history.metadata.get("legacy_backfill")
                else "already_removed_on_startup"
            )
        self.mark_removed(
            session.id,
            reason=reason,
            removed_at=session.ended_at,
        )
        return deck_owned

    def record_answer(
        self,
        session_id: str,
        *,
        card_id: int,
        answered_at: int,
        rating: int,
        duration_ms: int | None,
    ) -> bool:
        with self._database.locked() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                manifested = connection.execute(
                    """
                    SELECT 1 FROM generated_deck_cards
                    WHERE history_id = ? AND card_id = ?
                    """,
                    (session_id, card_id),
                ).fetchone()
                if manifested is None:
                    connection.rollback()
                    return False
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO generated_deck_card_answers(
                        history_id, card_id, answered_at, rating, duration_ms
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, card_id, answered_at, rating, duration_ms),
                )
                if cursor.rowcount:
                    connection.execute(
                        """
                        UPDATE generated_deck_cards
                        SET answered_at = ?, rating = ?, duration_ms = ?
                        WHERE history_id = ? AND card_id = ?
                        """,
                        (answered_at, rating, duration_ms, session_id, card_id),
                    )
                    connection.execute(
                        """
                        UPDATE generated_deck_history
                        SET status = CASE
                                WHEN status IN ('completed', 'abandoned') THEN status
                                ELSE 'active'
                            END,
                            answered_card_count = (
                                SELECT count(DISTINCT card_id)
                                FROM generated_deck_card_answers
                                WHERE history_id = ?
                            )
                        WHERE history_id = ?
                        """,
                        (session_id, session_id),
                    )
                connection.commit()
                return bool(cursor.rowcount)
            except Exception:
                connection.rollback()
                raise

    def mark_status(self, session: Session) -> None:
        with self._database.locked() as connection:
            connection.execute(
                """
                UPDATE generated_deck_history
                SET status = ?, ended_at = ?
                WHERE session_id = ?
                """,
                (session.status.value, session.ended_at, session.id),
            )
            connection.commit()

    def mark_removed(
        self,
        session_id: str,
        *,
        reason: str,
        removed_at: int | None = None,
    ) -> None:
        with self._database.locked() as connection:
            connection.execute(
                """
                UPDATE generated_deck_history
                SET removed_at = ?, removal_reason = ?
                WHERE session_id = ?
                """,
                (int(time.time()) if removed_at is None else removed_at, reason, session_id),
            )
            connection.commit()

    def interrupt_open(self) -> int:
        with self._database.locked() as connection:
            cursor = connection.execute(
                """
                UPDATE generated_deck_history
                SET status = 'interrupted'
                WHERE status IN ('started', 'active', 'paused', 'resumed')
                """
            )
            connection.commit()
            return cursor.rowcount

    def get(self, history_id: str) -> GeneratedDeckHistory | None:
        with self._database.locked() as connection:
            row = connection.execute(
                "SELECT * FROM generated_deck_history WHERE history_id = ?",
                (history_id,),
            ).fetchone()
            cards = list(
                connection.execute(
                    """
                    SELECT * FROM generated_deck_cards
                    WHERE history_id = ? ORDER BY queue_position
                    """,
                    (history_id,),
                )
            )
            answers = list(
                connection.execute(
                    """
                    SELECT * FROM generated_deck_card_answers
                    WHERE history_id = ? ORDER BY answered_at
                    """,
                    (history_id,),
                )
            )
        return self._from_rows(row, cards, answers) if row is not None else None

    def recent(self, limit: int = 100) -> tuple[GeneratedDeckHistory, ...]:
        safe_limit = max(1, min(int(limit), 500))
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT * FROM generated_deck_history
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (safe_limit,),
                )
            )
            if not rows:
                return ()
            ids = [str(row["history_id"]) for row in rows]
            placeholders = ",".join("?" for _history_id in ids)
            card_rows = list(
                connection.execute(
                    f"""
                    SELECT * FROM generated_deck_cards
                    WHERE history_id IN ({placeholders})
                    ORDER BY history_id, queue_position
                    """,
                    ids,
                )
            )
            answer_rows = list(
                connection.execute(
                    f"""
                    SELECT * FROM generated_deck_card_answers
                    WHERE history_id IN ({placeholders})
                    ORDER BY history_id, answered_at
                    """,
                    ids,
                )
            )
        cards_by_history: dict[str, list[Any]] = {
            history_id: [] for history_id in ids
        }
        answers_by_history: dict[str, list[Any]] = {
            history_id: [] for history_id in ids
        }
        for card in card_rows:
            cards_by_history[str(card["history_id"])].append(card)
        for answer in answer_rows:
            answers_by_history[str(answer["history_id"])].append(answer)
        return tuple(
            self._from_rows(
                row,
                cards_by_history[str(row["history_id"])],
                answers_by_history[str(row["history_id"])],
            )
            for row in rows
        )

    def recent_summaries(
        self, limit: int = 200
    ) -> tuple[GeneratedDeckHistory, ...]:
        """Load lightweight history rows; card manifests remain lazy."""

        safe_limit = max(1, min(int(limit), 500))
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT * FROM generated_deck_history
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (safe_limit,),
                )
            )
        return tuple(self._from_rows(row, [], []) for row in rows)

    @staticmethod
    def _from_rows(
        row: Any, cards: list[Any], answers: list[Any]
    ) -> GeneratedDeckHistory:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        return GeneratedDeckHistory(
            history_id=str(row["history_id"]),
            session_id=str(row["session_id"]),
            feature=str(row["feature"]),
            deck_id=int(row["deck_id"]),
            deck_name=str(row["deck_name"]),
            scope=str(row["scope"]) if row["scope"] is not None else None,
            target_seconds=(
                int(row["target_seconds"])
                if row["target_seconds"] is not None
                else None
            ),
            created_at=int(row["created_at"]),
            ended_at=int(row["ended_at"]) if row["ended_at"] is not None else None,
            removed_at=(
                int(row["removed_at"]) if row["removed_at"] is not None else None
            ),
            status=str(row["status"]),
            removal_reason=(
                str(row["removal_reason"])
                if row["removal_reason"] is not None
                else None
            ),
            planned_card_count=int(row["planned_card_count"]),
            answered_card_count=int(row["answered_card_count"]),
            metadata=metadata if isinstance(metadata, dict) else {},
            cards=tuple(
                GeneratedDeckCard(
                    card_id=int(card["card_id"]),
                    note_id=(
                        int(card["note_id"]) if card["note_id"] is not None else None
                    ),
                    original_deck_id=(
                        int(card["original_deck_id"])
                        if card["original_deck_id"] is not None
                        else None
                    ),
                    original_deck_name=(
                        str(card["original_deck_name"])
                        if card["original_deck_name"] is not None
                        else None
                    ),
                    queue_position=int(card["queue_position"]),
                    bucket=str(card["bucket"]) if card["bucket"] is not None else None,
                    answered_at=(
                        int(card["answered_at"])
                        if card["answered_at"] is not None
                        else None
                    ),
                    rating=int(card["rating"]) if card["rating"] is not None else None,
                    duration_ms=(
                        int(card["duration_ms"])
                        if card["duration_ms"] is not None
                        else None
                    ),
                )
                for card in cards
            ),
            answers=tuple(
                GeneratedDeckAnswer(
                    card_id=int(answer["card_id"]),
                    answered_at=int(answer["answered_at"]),
                    rating=int(answer["rating"]),
                    duration_ms=(
                        int(answer["duration_ms"])
                        if answer["duration_ms"] is not None
                        else None
                    ),
                )
                for answer in answers
            ),
        )


def collect_generated_deck_cards(
    collection: Any,
    deck_id: int,
    ordered_card_ids: tuple[int, ...],
    *,
    buckets: Mapping[int, str] | None = None,
) -> tuple[GeneratedDeckCard, ...]:
    """Capture the exact cards Anki actually placed in an owned filtered deck."""

    cards: list[GeneratedDeckCard] = []
    for position, card_id in enumerate(ordered_card_ids, start=1):
        card = collection.get_card(card_id)
        if int(getattr(card, "did", 0)) != int(deck_id):
            continue
        original_deck_id = int(getattr(card, "odid", 0) or 0) or None
        original_deck_name = None
        if original_deck_id is not None:
            try:
                original_deck_name = str(collection.decks.name(original_deck_id))
            except Exception:
                original_deck_name = None
        cards.append(
            GeneratedDeckCard(
                card_id=int(card_id),
                note_id=int(getattr(card, "nid", 0) or 0) or None,
                original_deck_id=original_deck_id,
                original_deck_name=original_deck_name,
                queue_position=position,
                bucket=(buckets or {}).get(int(card_id)),
            )
        )
    return tuple(cards)
