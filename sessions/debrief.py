"""Durable, learner-facing summaries built from Vellum session metadata."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Mapping

from ..core.db import Database
from .models import Session, SessionOrigin, SessionStatus


RATING_NAMES = {1: "again", 2: "hard", 3: "good", 4: "easy"}
CARD_STATES = frozenset({"none", "pending", "opened", "dismissed"})
NOTE_EVENTS = frozenset({"created", "resurfaced"})


@dataclass(frozen=True)
class DebriefTopic:
    topic_id: str
    label: str
    path: tuple[str, ...]
    raw_topic_tag: str | None
    unique_cards: int
    answer_count: int
    again_count: int
    hard_count: int
    last_seen_at: int
    error_cluster: bool = False


@dataclass(frozen=True)
class DebriefMindNote:
    note_id: int
    event_type: str
    body: str
    topic_label: str


@dataclass(frozen=True)
class SessionDebrief:
    session_id: str
    origin: str
    status: str
    started_at: int
    ended_at: int
    unique_card_count: int
    answer_count: int
    active_duration_ms: int | None
    elapsed_seconds: int
    planned_card_count: int | None
    remaining_card_count: int | None
    target_seconds: int | None
    estimated_seconds: float | None
    again_count: int
    hard_count: int
    good_count: int
    easy_count: int
    pace_delta_percent: float | None
    topics: tuple[DebriefTopic, ...]
    mind_notes: tuple[DebriefMindNote, ...]
    suggestion: Mapping[str, Any]
    handoff_text: str | None
    handoff_acknowledged_at: int | None
    completion_card_state: str
    created_at: int

    @property
    def is_generated(self) -> bool:
        return self.origin in {
            SessionOrigin.TIME_MACHINE.value,
            SessionOrigin.RECOVERY.value,
        }


class DebriefRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def record_mind_note_event(
        self,
        session_id: str,
        note_id: int,
        event_type: str,
        *,
        occurred_at: int | None = None,
    ) -> bool:
        if event_type not in NOTE_EVENTS:
            raise ValueError("Unsupported Mind Note event")
        with self._database.locked() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO session_mind_note_events(
                    session_id, note_id, event_type, occurred_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(note_id),
                    event_type,
                    int(time.time()) if occurred_at is None else int(occurred_at),
                ),
            )
            connection.commit()
            return bool(cursor.rowcount)

    def finalize(
        self,
        session: Session,
        *,
        show_completion_card: bool,
        recovery_enabled: bool = True,
    ) -> SessionDebrief | None:
        if session.status not in {SessionStatus.COMPLETED, SessionStatus.ABANDONED}:
            return None
        existing = self.get(session.id)
        if existing is not None:
            return existing

        with self._database.locked() as connection:
            answers = list(
                connection.execute(
                    """
                    SELECT card_id, reviewed_at, rating, duration_ms, topic_id,
                           topic_label, topic_path_json, raw_topic_tag
                    FROM session_cards WHERE session_id = ? ORDER BY reviewed_at
                    """,
                    (session.id,),
                )
            )
            generated = connection.execute(
                """
                SELECT planned_card_count, answered_card_count, removed_at,
                       metadata_json
                FROM generated_deck_history WHERE session_id = ?
                """,
                (session.id,),
            ).fetchone()
            note_rows = list(
                connection.execute(
                    """
                    SELECT event.note_id, event.event_type, event.occurred_at,
                           note.body, note.topic_label
                    FROM session_mind_note_events AS event
                    JOIN mind_notes AS note ON note.id = event.note_id
                    WHERE event.session_id = ?
                    ORDER BY event.occurred_at, event.note_id
                    """,
                    (session.id,),
                )
            )

        # New records always persist at least an empty JSON topic path. All-NULL
        # rows are pre-v7 history and cannot support a truthful learning summary.
        if answers and all(row["topic_path_json"] is None for row in answers):
            return None
        if not answers:
            if session.origin is SessionOrigin.NORMAL:
                return None
            try:
                generated_metadata = json.loads(
                    str(generated["metadata_json"] or "{}")
                ) if generated is not None else {}
            except (json.JSONDecodeError, TypeError):
                generated_metadata = {}
            if not bool(generated_metadata.get("debrief_topic_snapshots")):
                return None
        if session.origin in {SessionOrigin.TIME_MACHINE, SessionOrigin.RECOVERY}:
            if generated is None or generated["removed_at"] is None:
                return None

        unique_cards = len({int(row["card_id"]) for row in answers})
        rating_counts = {name: 0 for name in RATING_NAMES.values()}
        valid_durations: list[int] = []
        topic_data: dict[str, dict[str, Any]] = {}
        for row in answers:
            rating = RATING_NAMES.get(int(row["rating"] or 0))
            if rating is not None:
                rating_counts[rating] += 1
            if row["duration_ms"] is not None:
                duration = int(row["duration_ms"])
                if 250 <= duration <= 120_000:
                    valid_durations.append(duration)
            topic_id = str(row["topic_id"] or "")
            if not topic_id:
                continue
            try:
                path_payload = json.loads(row["topic_path_json"] or "[]")
            except (json.JSONDecodeError, TypeError):
                path_payload = []
            path = tuple(item for item in path_payload if isinstance(item, str))
            current = topic_data.setdefault(
                topic_id,
                {
                    "label": str(row["topic_label"] or (path[-1] if path else "Topic")),
                    "path": path,
                    "raw_topic_tag": (
                        str(row["raw_topic_tag"])
                        if row["raw_topic_tag"] is not None
                        else None
                    ),
                    "cards": set(),
                    "answer_count": 0,
                    "again_count": 0,
                    "hard_count": 0,
                    "last_seen_at": 0,
                },
            )
            current["cards"].add(int(row["card_id"]))
            current["answer_count"] += 1
            current["last_seen_at"] = max(
                current["last_seen_at"], int(row["reviewed_at"])
            )
            if rating == "again":
                current["again_count"] += 1
            elif rating == "hard":
                current["hard_count"] += 1

        topics: list[DebriefTopic] = []
        for topic_id, value in topic_data.items():
            again = int(value["again_count"])
            hard = int(value["hard_count"])
            topics.append(
                DebriefTopic(
                    topic_id=topic_id,
                    label=str(value["label"]),
                    path=tuple(value["path"]),
                    raw_topic_tag=value["raw_topic_tag"],
                    unique_cards=len(value["cards"]),
                    answer_count=int(value["answer_count"]),
                    again_count=again,
                    hard_count=hard,
                    last_seen_at=int(value["last_seen_at"]),
                    error_cluster=again >= 2 or (again >= 1 and hard >= 2),
                )
            )
        topics.sort(
            key=lambda item: (
                -(2 * item.again_count + item.hard_count),
                -((item.again_count + item.hard_count) / max(1, item.answer_count)),
                -item.last_seen_at,
                item.label.casefold(),
            )
        )

        planned = (
            int(generated["planned_card_count"])
            if generated is not None
            else session.estimated_total or session.starting_due_count
        )
        remaining = max(0, planned - unique_cards) if planned is not None else None
        active_ms = sum(valid_durations) if valid_durations else None
        pace_delta = None
        if (
            len(valid_durations) >= 5
            and session.estimated_seconds is not None
            and session.estimated_seconds > 0
            and planned
        ):
            actual_per_answer = sum(valid_durations) / len(valid_durations) / 1000
            expected_per_card = session.estimated_seconds / planned
            if expected_per_card > 0:
                pace_delta = ((actual_per_answer - expected_per_card) / expected_per_card) * 100

        note_events = tuple(
            DebriefMindNote(
                note_id=int(row["note_id"]),
                event_type=str(row["event_type"]),
                body=str(row["body"]),
                topic_label=str(row["topic_label"]),
            )
            for row in note_rows
        )
        suggestion = self._suggestion(
            tuple(topics), session, remaining, recovery_enabled=recovery_enabled
        )
        card_state = (
            "pending"
            if show_completion_card
            and session.origin in {SessionOrigin.TIME_MACHINE, SessionOrigin.RECOVERY}
            else "none"
        )
        ended_at = int(session.ended_at or session.last_active_at)
        created_at = int(time.time())
        payload = (
            session.id,
            session.origin.value,
            session.status.value,
            session.started_at,
            ended_at,
            unique_cards,
            len(answers),
            active_ms,
            max(0, ended_at - session.started_at),
            planned,
            remaining,
            session.target_seconds,
            session.estimated_seconds,
            rating_counts["again"],
            rating_counts["hard"],
            rating_counts["good"],
            rating_counts["easy"],
            pace_delta,
            json.dumps([self._topic_mapping(item) for item in topics], separators=(",", ":")),
            json.dumps([self._note_mapping(item) for item in note_events], separators=(",", ":")),
            json.dumps(dict(suggestion), separators=(",", ":")),
            card_state,
            created_at,
        )
        with self._database.locked() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO session_debriefs(
                    session_id, origin, status, started_at, ended_at,
                    unique_card_count, answer_count, active_duration_ms,
                    elapsed_seconds, planned_card_count, remaining_card_count,
                    target_seconds, estimated_seconds, again_count, hard_count,
                    good_count, easy_count, pace_delta_percent, topics_json,
                    mind_notes_json, suggestion_json, completion_card_state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            connection.commit()
        return self.get(session.id)

    @staticmethod
    def _suggestion(
        topics: tuple[DebriefTopic, ...],
        session: Session,
        remaining: int | None,
        *,
        recovery_enabled: bool,
    ) -> Mapping[str, Any]:
        for topic in topics:
            if recovery_enabled and topic.error_cluster and topic.raw_topic_tag:
                return {
                    "kind": "recovery",
                    "title": f"Recover {topic.label}",
                    "detail": "Again and Hard answers clustered here.",
                    "topic_id": topic.topic_id,
                    "topic_label": topic.label,
                    "topic_path": list(topic.path),
                    "raw_topic_tag": topic.raw_topic_tag,
                }
        if session.status is SessionStatus.ABANDONED and remaining:
            return {
                "kind": "time_machine",
                "title": "Plan another session when you are ready",
                "detail": f"{remaining} unanswered cards returned safely to Anki.",
            }
        return {
            "kind": "done",
            "title": "Done for now",
            "detail": "Anki has recorded your answers. No extra action is required.",
        }

    def get(self, session_id: str) -> SessionDebrief | None:
        with self._database.locked() as connection:
            row = connection.execute(
                "SELECT * FROM session_debriefs WHERE session_id = ?", (session_id,)
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def recent(self, limit: int = 200) -> tuple[SessionDebrief, ...]:
        safe_limit = max(1, min(int(limit), 500))
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    "SELECT * FROM session_debriefs ORDER BY created_at DESC LIMIT ?",
                    (safe_limit,),
                )
            )
        return tuple(self._from_row(row) for row in rows)

    def pending_completion(self) -> SessionDebrief | None:
        with self._database.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM session_debriefs
                WHERE completion_card_state = 'pending'
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def set_completion_state(self, session_id: str, state: str) -> bool:
        if state not in CARD_STATES:
            raise ValueError("Invalid completion card state")
        with self._database.locked() as connection:
            cursor = connection.execute(
                "UPDATE session_debriefs SET completion_card_state = ? WHERE session_id = ?",
                (state, session_id),
            )
            connection.commit()
            return bool(cursor.rowcount)

    def save_handoff(self, session_id: str, text: str) -> SessionDebrief:
        clean = " ".join(text.split())
        if len(clean) > 280:
            raise ValueError("Handoff must be 280 characters or fewer")
        now = int(time.time())
        with self._database.locked() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE session_debriefs
                    SET handoff_acknowledged_at = ?
                    WHERE handoff_text IS NOT NULL
                      AND handoff_acknowledged_at IS NULL
                      AND session_id <> ?
                    """,
                    (now, session_id),
                )
                cursor = connection.execute(
                    """
                    UPDATE session_debriefs
                    SET handoff_text = ?, handoff_acknowledged_at = ?
                    WHERE session_id = ?
                    """,
                    (clean or None, None if clean else now, session_id),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if not cursor.rowcount:
            raise ValueError("Debrief is unavailable")
        saved = self.get(session_id)
        assert saved is not None
        return saved

    def active_handoff(self) -> SessionDebrief | None:
        with self._database.locked() as connection:
            row = connection.execute(
                """
                SELECT * FROM session_debriefs
                WHERE handoff_text IS NOT NULL AND handoff_acknowledged_at IS NULL
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def acknowledge_handoff(self, session_id: str) -> bool:
        with self._database.locked() as connection:
            cursor = connection.execute(
                """
                UPDATE session_debriefs SET handoff_acknowledged_at = ?
                WHERE session_id = ? AND handoff_text IS NOT NULL
                  AND handoff_acknowledged_at IS NULL
                """,
                (int(time.time()), session_id),
            )
            connection.commit()
            return bool(cursor.rowcount)

    def terminal_sessions_without_debrief(self, limit: int = 500) -> tuple[str, ...]:
        with self._database.locked() as connection:
            rows = list(
                connection.execute(
                    """
                    SELECT sessions.id FROM sessions
                    LEFT JOIN session_debriefs
                      ON session_debriefs.session_id = sessions.id
                    WHERE sessions.status IN ('completed', 'abandoned')
                      AND session_debriefs.session_id IS NULL
                    ORDER BY COALESCE(sessions.ended_at, sessions.last_active_at)
                    LIMIT ?
                    """,
                    (max(1, min(int(limit), 5_000)),),
                )
            )
        return tuple(str(row["id"]) for row in rows)

    def prune_normal(self, history_days: int, maximum_sessions: int) -> int:
        with self._database.locked() as connection:
            before = connection.total_changes
            try:
                connection.execute("BEGIN IMMEDIATE")
                if history_days > 0:
                    cutoff = int(time.time()) - history_days * 86400
                    connection.execute(
                        """
                        DELETE FROM session_debriefs
                        WHERE origin NOT IN ('time_machine', 'recovery')
                          AND created_at < ?
                          AND NOT (
                            handoff_text IS NOT NULL
                            AND handoff_acknowledged_at IS NULL
                          )
                        """,
                        (cutoff,),
                    )
                connection.execute(
                    """
                    DELETE FROM session_debriefs WHERE session_id IN (
                        SELECT session_id FROM session_debriefs
                        WHERE origin NOT IN ('time_machine', 'recovery')
                          AND NOT (
                            handoff_text IS NOT NULL
                            AND handoff_acknowledged_at IS NULL
                          )
                        ORDER BY created_at DESC LIMIT -1 OFFSET ?
                    )
                    """,
                    (max(10, int(maximum_sessions)),),
                )
                connection.commit()
                return connection.total_changes - before
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _topic_mapping(topic: DebriefTopic) -> Mapping[str, Any]:
        return {
            "topic_id": topic.topic_id,
            "label": topic.label,
            "path": list(topic.path),
            "raw_topic_tag": topic.raw_topic_tag,
            "unique_cards": topic.unique_cards,
            "answer_count": topic.answer_count,
            "again_count": topic.again_count,
            "hard_count": topic.hard_count,
            "last_seen_at": topic.last_seen_at,
            "error_cluster": topic.error_cluster,
        }

    @staticmethod
    def _note_mapping(note: DebriefMindNote) -> Mapping[str, Any]:
        return {
            "note_id": note.note_id,
            "event_type": note.event_type,
            "body": note.body,
            "topic_label": note.topic_label,
        }

    @classmethod
    def _from_row(cls, row: Any) -> SessionDebrief:
        def payload(name: str, fallback: Any) -> Any:
            try:
                parsed = json.loads(row[name] or json.dumps(fallback))
                return parsed
            except (json.JSONDecodeError, TypeError):
                return fallback

        topics = tuple(
            DebriefTopic(
                topic_id=str(item.get("topic_id") or ""),
                label=str(item.get("label") or "Topic"),
                path=tuple(value for value in item.get("path", []) if isinstance(value, str)),
                raw_topic_tag=(
                    str(item["raw_topic_tag"])
                    if item.get("raw_topic_tag") is not None
                    else None
                ),
                unique_cards=int(item.get("unique_cards") or 0),
                answer_count=int(item.get("answer_count") or 0),
                again_count=int(item.get("again_count") or 0),
                hard_count=int(item.get("hard_count") or 0),
                last_seen_at=int(item.get("last_seen_at") or 0),
                error_cluster=bool(item.get("error_cluster")),
            )
            for item in payload("topics_json", [])
            if isinstance(item, dict)
        )
        notes = tuple(
            DebriefMindNote(
                note_id=int(item.get("note_id") or 0),
                event_type=str(item.get("event_type") or "resurfaced"),
                body=str(item.get("body") or ""),
                topic_label=str(item.get("topic_label") or "Topic"),
            )
            for item in payload("mind_notes_json", [])
            if isinstance(item, dict)
        )
        return SessionDebrief(
            session_id=str(row["session_id"]),
            origin=str(row["origin"]),
            status=str(row["status"]),
            started_at=int(row["started_at"]),
            ended_at=int(row["ended_at"]),
            unique_card_count=int(row["unique_card_count"]),
            answer_count=int(row["answer_count"]),
            active_duration_ms=(
                int(row["active_duration_ms"])
                if row["active_duration_ms"] is not None
                else None
            ),
            elapsed_seconds=int(row["elapsed_seconds"]),
            planned_card_count=(
                int(row["planned_card_count"])
                if row["planned_card_count"] is not None
                else None
            ),
            remaining_card_count=(
                int(row["remaining_card_count"])
                if row["remaining_card_count"] is not None
                else None
            ),
            target_seconds=(
                int(row["target_seconds"])
                if row["target_seconds"] is not None
                else None
            ),
            estimated_seconds=(
                float(row["estimated_seconds"])
                if row["estimated_seconds"] is not None
                else None
            ),
            again_count=int(row["again_count"]),
            hard_count=int(row["hard_count"]),
            good_count=int(row["good_count"]),
            easy_count=int(row["easy_count"]),
            pace_delta_percent=(
                float(row["pace_delta_percent"])
                if row["pace_delta_percent"] is not None
                else None
            ),
            topics=topics,
            mind_notes=notes,
            suggestion=payload("suggestion_json", {}),
            handoff_text=(str(row["handoff_text"]) if row["handoff_text"] else None),
            handoff_acknowledged_at=(
                int(row["handoff_acknowledged_at"])
                if row["handoff_acknowledged_at"] is not None
                else None
            ),
            completion_card_state=str(row["completion_card_state"]),
            created_at=int(row["created_at"]),
        )
