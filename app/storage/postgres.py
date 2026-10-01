from __future__ import annotations

import os
import secrets
import psycopg
from psycopg.rows import no_result
import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any
from uuid import uuid4


class _HybridRow(dict):
    """PostgreSQL row supporting both named and positional access."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    """Build psycopg's row-maker callback for named and positional access."""
    if cursor.description is None:
        return no_result
    columns = tuple(column.name for column in cursor.description)

    def make_row(values):
        return _HybridRow(zip(columns, values))

    return make_row


class _Connection:
    """Small compatibility adapter preserving the existing store SQL API."""
    def __init__(self, url: str):
        import psycopg
        self._conn = psycopg.connect(url, row_factory=_row_factory)

    def execute(self, query: str, params=()):
        query = query.replace("?", "%s")
        if "INSERT OR REPLACE INTO academy_active_polls" in query:
            query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
            query = query.rstrip().rstrip(";") + " ON CONFLICT (poll_id) DO UPDATE SET attempt_id=EXCLUDED.attempt_id, question_index=EXCLUDED.question_index, telegram_id=EXCLUDED.telegram_id, created_at=EXCLUDED.created_at"
        elif "INSERT OR IGNORE INTO" in query:
            query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            query = query.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return self._conn.execute(query, params)

    def executescript(self, script: str):
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._conn.rollback()
        else:
            self._conn.commit()
        return False


class AcademyStore:
    """Persistent PostgreSQL runtime store with the existing AcademyStore API."""
    def __init__(self, database_url: str | None = None) -> None:
        from config import settings
        url = (database_url or settings.database_url).strip()
        if not url:
            raise RuntimeError("DATABASE_URL is required for the PostgreSQL runtime store.")
        self._lock = threading.RLock()
        self._conn = _Connection(url)
        self._timezone = self._load_timezone()
        self._init_schema()

    def ping(self) -> bool:
        """Perform a lightweight database liveness check for readiness probes."""
        with self._lock:
            self._conn.execute("SELECT 1").fetchone()
        return True

    def _load_timezone(self) -> ZoneInfo:
        from config import settings
        raw = settings.timezone
        try:
            return ZoneInfo(raw)
        except Exception:
            return ZoneInfo("UTC")

    def _local_today(self) -> date:
        return datetime.now(self._timezone).date()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS academy_users (
                    telegram_id BIGINT PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    university TEXT,
                    department TEXT,
                    level TEXT NOT NULL,
                    privacy_consent INTEGER NOT NULL DEFAULT 0,
                    privacy_consented_at TEXT,
                    privacy_policy_version TEXT,
                    ethical_hacking_consent INTEGER NOT NULL DEFAULT 0,
                    ethical_hacking_consented_at TEXT,
                    reminder_enabled INTEGER NOT NULL DEFAULT 0,
                    reminder_hour INTEGER NOT NULL DEFAULT 18,
                    last_reminder_date TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS academy_lesson_progress (
                    telegram_id BIGINT NOT NULL,
                    lesson_id INTEGER NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, lesson_id),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_xp_events (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    amount INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (telegram_id, reason),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_favorites (
                    telegram_id BIGINT NOT NULL,
                    content_type TEXT NOT NULL,
                    content_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, content_type, content_id),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_user_stats (
                    telegram_id BIGINT PRIMARY KEY,
                    current_streak INTEGER NOT NULL DEFAULT 0,
                    last_active_date TEXT,
                    last_lesson_id INTEGER,
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_quiz_attempts (
                    id TEXT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    lesson_id INTEGER NOT NULL,
                    total_questions INTEGER NOT NULL,
                    correct_answers INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT,
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_quiz_answers (
                    attempt_id TEXT NOT NULL,
                    question_index INTEGER NOT NULL,
                    selected_option INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (attempt_id, question_index),
                    FOREIGN KEY (attempt_id) REFERENCES academy_quiz_attempts(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_active_polls (
                    poll_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    question_index INTEGER NOT NULL,
                    telegram_id BIGINT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (attempt_id) REFERENCES academy_quiz_attempts(id) ON DELETE CASCADE,
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_launch_notifications (
                    telegram_id BIGINT NOT NULL,
                    feature_key TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    notified_at TEXT,
                    PRIMARY KEY (telegram_id, feature_key),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_badges (
                    telegram_id BIGINT NOT NULL,
                    badge_key TEXT NOT NULL,
                    awarded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, badge_key),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_certificates (
                    id TEXT PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    course_key TEXT NOT NULL,
                    verification_code TEXT NOT NULL UNIQUE,
                    issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_certificate_payments (
                    telegram_id BIGINT NOT NULL,
                    course_key TEXT NOT NULL,
                    payload TEXT NOT NULL UNIQUE,
                    currency TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    telegram_payment_charge_id TEXT NOT NULL UNIQUE,
                    provider_payment_charge_id TEXT,
                    status TEXT NOT NULL DEFAULT 'paid',
                    paid_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, course_key),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_custom_lessons (
                    id BIGSERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    duration TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    theory TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT '',
                    examples TEXT NOT NULL DEFAULT '',
                    created_by INTEGER NOT NULL,
                    source_lesson_uuid TEXT UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS academy_code_drafts (
                    telegram_id BIGINT NOT NULL,
                    lesson_id INTEGER NOT NULL,
                    language TEXT NOT NULL DEFAULT 'cpp',
                    code TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, lesson_id, language),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_ai_messages (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'tutor',
                    lesson_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_ai_memory (
                    telegram_id BIGINT PRIMARY KEY,
                    summary TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_ai_usage (
                    telegram_id BIGINT NOT NULL,
                    usage_date TEXT NOT NULL,
                    tutor_count INTEGER NOT NULL DEFAULT 0,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    quiz_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (telegram_id, usage_date),
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS academy_ai_feedback (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    message_id INTEGER,
                    rating INTEGER NOT NULL CHECK(rating IN (-1,1)),
                    reason TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES academy_users(telegram_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_ai_messages_user ON academy_ai_messages(telegram_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_progress_user ON academy_lesson_progress(telegram_id);
                CREATE INDEX IF NOT EXISTS idx_xp_user ON academy_xp_events(telegram_id);
                CREATE INDEX IF NOT EXISTS idx_poll_user ON academy_active_polls(telegram_id);
                """
            )
            self._migrate_telegram_ids()
            self._migrate_users()
            self._repair_runtime_schema()

    def _repair_runtime_schema(self) -> None:
        """Repair legacy runtime constraints without losing learner data."""
        with self._lock, self._conn:
            # Existing installations may still have the old two-column PK.
            # Dropping it and replacing it with a language-aware key is safe
            # because the old PK guaranteed at most one row per user/lesson.
            self._conn.execute(
                "ALTER TABLE academy_code_drafts DROP CONSTRAINT IF EXISTS academy_code_drafts_pkey"
            )
            self._conn.execute(
                "DROP INDEX IF EXISTS ux_academy_code_drafts_user_lesson_language"
            )
            self._conn.execute(
                "CREATE UNIQUE INDEX ux_academy_code_drafts_user_lesson_language "
                "ON academy_code_drafts (telegram_id, lesson_id, language)"
            )
            self._conn.execute(
                "ALTER TABLE academy_code_drafts ADD CONSTRAINT academy_code_drafts_pkey "
                "PRIMARY KEY USING INDEX ux_academy_code_drafts_user_lesson_language"
            )
            # Remove impossible legacy duplicates before adding the unique
            # constraint. Keep the earliest issued row for each user/course.
            self._conn.execute(
                """DELETE FROM academy_certificates a
                   USING academy_certificates b
                   WHERE a.telegram_id=b.telegram_id
                     AND a.course_key=b.course_key
                     AND (a.issued_at > b.issued_at
                          OR (a.issued_at = b.issued_at AND a.id > b.id))"""
            )
            self._conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_academy_certificates_user_course "
                "ON academy_certificates (telegram_id, course_key)"
            )

    def _migrate_telegram_ids(self) -> None:
        """Widen legacy Telegram ID columns before accepting real user IDs."""
        columns = self._conn.execute(
            """SELECT table_name FROM information_schema.columns
               WHERE table_schema='public' AND column_name='telegram_id'
                 AND data_type='integer'"""
        ).fetchall()
        if not columns:
            return
        constraints = self._conn.execute(
            """SELECT conname, conrelid::regclass::text AS table_name,
                      pg_get_constraintdef(oid) AS definition
               FROM pg_constraint
               WHERE contype='f' AND pg_get_constraintdef(oid) LIKE '%%telegram_id%%'"""
        ).fetchall()
        table_names = {str(row[0]) for row in columns}
        with self._lock, self._conn:
            for row in constraints:
                table = str(row[1])
                name = str(row[0])
                if table in table_names:
                    self._conn.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"')
            for table in table_names:
                self._conn.execute(
                    f'ALTER TABLE "{table}" ALTER COLUMN telegram_id TYPE BIGINT USING telegram_id::bigint'
                )
            for row in constraints:
                table = str(row[1])
                if table in table_names:
                    self._conn.execute(
                        f'ALTER TABLE "{table}" ADD CONSTRAINT "{row[0]}" {row[2]}'
                    )

    def _migrate_users(self) -> None:
        cols = {row[0] for row in self._conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='academy_users'").fetchall()}
        additions = {
            "privacy_consent": "INTEGER NOT NULL DEFAULT 0",
            "privacy_consented_at": "TEXT",
            "privacy_policy_version": "TEXT",
            "ethical_hacking_consent": "INTEGER NOT NULL DEFAULT 0",
            "ethical_hacking_consented_at": "TEXT",
            "reminder_enabled": "INTEGER NOT NULL DEFAULT 0",
            "reminder_hour": "INTEGER NOT NULL DEFAULT 18",
            "last_reminder_date": "TEXT",
        }
        with self._lock, self._conn:
            for name, definition in additions.items():
                if name not in cols:
                    self._conn.execute(f"ALTER TABLE academy_users ADD COLUMN {name} {definition.replace('INTEGER', 'INTEGER')}")
        # V2 required university/department. We intentionally keep that schema
        # compatible and store an empty string when the user chooses "تخطي".
        # Keep the existing schema compatible and preserve all foreign keys.

        custom_cols = {row[0] for row in self._conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='academy_custom_lessons'").fetchall()}
        with self._lock, self._conn:
            if "source_lesson_uuid" not in custom_cols:
                self._conn.execute("ALTER TABLE academy_custom_lessons ADD COLUMN source_lesson_uuid TEXT UNIQUE")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def get_profile(self, telegram_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT full_name, age, university, department, level, privacy_consent, ethical_hacking_consent FROM academy_users WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()
        return dict(row) if row else None

    def save_profile(self, telegram_id: int, username: str | None, profile: dict[str, Any], *, privacy_policy_version: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO academy_users (telegram_id,username,full_name,age,university,department,level,privacy_consent,privacy_consented_at,privacy_policy_version)
                VALUES (?,?,?,?,?,?,?,1,CURRENT_TIMESTAMP,?)
                ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,full_name=excluded.full_name,
                age=excluded.age,university=excluded.university,department=excluded.department,level=excluded.level,
                privacy_consent=1,privacy_consented_at=CURRENT_TIMESTAMP,privacy_policy_version=excluded.privacy_policy_version,
                updated_at=CURRENT_TIMESTAMP""",
                (telegram_id, username, profile["full_name"], int(profile["age"]), profile.get("university") or "", profile.get("department") or "", profile["level"], privacy_policy_version),
            )
            # Keep the normalized SQLAlchemy identity table in sync with the bot profile.
            # This is intentionally separate from academy_users so the legacy runtime schema
            # cannot collide with the RBAC/identity schema managed by Alembic.
            identity_user = self._conn.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
            if identity_user:
                self._conn.execute(
                    "UPDATE users SET username=?, is_active=TRUE, updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?",
                    (username, telegram_id),
                )
            else:
                self._conn.execute(
                    "INSERT INTO users (id,telegram_id,username,is_active,is_verified) VALUES (?,?,?,?,?)",
                    (str(uuid4()), telegram_id, username, True, False),
                )
            self._conn.execute("INSERT OR IGNORE INTO academy_user_stats (telegram_id) VALUES (?)", (telegram_id,))

    def has_privacy_consent(self, telegram_id: int) -> bool:
        row = self._conn.execute("SELECT privacy_consent FROM academy_users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return bool(row and row[0])

    def delete_user_data(self, telegram_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM academy_users WHERE telegram_id=?", (telegram_id,))
            self._conn.execute("DELETE FROM users WHERE telegram_id=?", (telegram_id,))
            return cur.rowcount == 1

    def set_ethical_hacking_consent(self, telegram_id: int) -> None:
        from datetime import datetime, timezone
        with self._lock, self._conn:
            self._conn.execute("UPDATE academy_users SET ethical_hacking_consent=1,ethical_hacking_consented_at=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?", (datetime.now(timezone.utc).isoformat(), telegram_id))

    def get_code_draft(self, telegram_id: int, lesson_id: int, language: str = "cpp") -> str | None:
        row = self._conn.execute(
            "SELECT code FROM academy_code_drafts WHERE telegram_id=? AND lesson_id=? AND language=?",
            (telegram_id, lesson_id, language),
        ).fetchone()
        return str(row[0]) if row else None

    def save_code_draft(self, telegram_id: int, lesson_id: int, code: str, language: str = "cpp") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO academy_code_drafts (telegram_id,lesson_id,language,code,updated_at)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id,lesson_id,language) DO UPDATE SET code=excluded.code,updated_at=CURRENT_TIMESTAMP""",
                (telegram_id, lesson_id, language, code),
            )

    def certificate_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM academy_certificates").fetchone()[0])

    def touch_activity(self, telegram_id: int) -> int:
        today = self._local_today()
        with self._lock, self._conn:
            row = self._conn.execute("SELECT current_streak,last_active_date FROM academy_user_stats WHERE telegram_id=?", (telegram_id,)).fetchone()
            if not row:
                self._conn.execute("INSERT INTO academy_user_stats (telegram_id,current_streak,last_active_date) VALUES (?,1,?)", (telegram_id, today.isoformat()))
                return 1
            last = date.fromisoformat(row["last_active_date"]) if row["last_active_date"] else None
            streak = int(row["current_streak"] or 0)
            if last == today:
                return streak
            streak = streak + 1 if last == today - timedelta(days=1) else 1
            self._conn.execute("UPDATE academy_user_stats SET current_streak=?,last_active_date=? WHERE telegram_id=?", (streak,today.isoformat(),telegram_id))
            return streak

    def streak(self, telegram_id: int) -> int:
        row = self._conn.execute("SELECT current_streak FROM academy_user_stats WHERE telegram_id=?", (telegram_id,)).fetchone()
        return int(row[0]) if row else 0

    def set_last_lesson(self, telegram_id: int, lesson_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR IGNORE INTO academy_user_stats (telegram_id) VALUES (?)", (telegram_id,))
            self._conn.execute("UPDATE academy_user_stats SET last_lesson_id=? WHERE telegram_id=?", (lesson_id, telegram_id))

    def last_lesson(self, telegram_id: int) -> int | None:
        row = self._conn.execute("SELECT last_lesson_id FROM academy_user_stats WHERE telegram_id=?", (telegram_id,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def complete_lesson(self, telegram_id: int, lesson_id: int) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("INSERT OR IGNORE INTO academy_lesson_progress (telegram_id,lesson_id) VALUES (?,?)", (telegram_id,lesson_id))
            inserted = cur.rowcount == 1
            if inserted:
                self._add_xp_locked(telegram_id,50,f"lesson:{lesson_id}")
            return inserted

    def is_completed(self, telegram_id: int, lesson_id: int) -> bool:
        return bool(self._conn.execute("SELECT 1 FROM academy_lesson_progress WHERE telegram_id=? AND lesson_id=?", (telegram_id,lesson_id)).fetchone())

    def completed_lessons(self, telegram_id: int) -> set[int]:
        return {int(r[0]) for r in self._conn.execute("SELECT lesson_id FROM academy_lesson_progress WHERE telegram_id=?", (telegram_id,)).fetchall()}

    def add_xp(self, telegram_id: int, amount: int, reason: str) -> bool:
        with self._lock, self._conn:
            return self._add_xp_locked(telegram_id, amount, reason)

    def _add_xp_locked(self, telegram_id: int, amount: int, reason: str) -> bool:
        cur = self._conn.execute("INSERT OR IGNORE INTO academy_xp_events (telegram_id,amount,reason) VALUES (?,?,?)", (telegram_id,amount,reason))
        return cur.rowcount == 1

    def xp(self, telegram_id: int) -> int:
        row = self._conn.execute("SELECT COALESCE(SUM(amount),0) FROM academy_xp_events WHERE telegram_id=?", (telegram_id,)).fetchone()
        return int(row[0]) if row else 0

    def toggle_favorite(self, telegram_id: int, content_type: str, content_id: str) -> bool:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT 1 FROM academy_favorites WHERE telegram_id=? AND content_type=? AND content_id=?", (telegram_id,content_type,content_id)).fetchone()
            if row:
                self._conn.execute("DELETE FROM academy_favorites WHERE telegram_id=? AND content_type=? AND content_id=?", (telegram_id,content_type,content_id)); return False
            self._conn.execute("INSERT INTO academy_favorites (telegram_id,content_type,content_id) VALUES (?,?,?)", (telegram_id,content_type,content_id)); return True

    def is_favorite(self, telegram_id: int, content_type: str, content_id: str) -> bool:
        return bool(self._conn.execute("SELECT 1 FROM academy_favorites WHERE telegram_id=? AND content_type=? AND content_id=?", (telegram_id,content_type,content_id)).fetchone())

    def favorites(self, telegram_id: int, content_type: str = "lesson") -> list[int]:
        return [int(r[0]) for r in self._conn.execute("SELECT content_id FROM academy_favorites WHERE telegram_id=? AND content_type=? ORDER BY created_at DESC", (telegram_id,content_type)).fetchall()]

    def snapshot(self, telegram_id: int, total_lessons: int) -> dict[str, Any]:
        completed = len(self.completed_lessons(telegram_id) & set(range(1, total_lessons + 1)))
        return {"completed":completed,"total":total_lessons,"percent":round(completed/total_lessons*100) if total_lessons else 0,"xp":self.xp(telegram_id),"streak":self.streak(telegram_id),"last_lesson":self.last_lesson(telegram_id)}

    # ---- Quiz polls -----------------------------------------------------
    def create_quiz_attempt(self, telegram_id: int, lesson_id: int, total_questions: int) -> str:
        attempt_id = str(uuid4())
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO academy_quiz_attempts (id,telegram_id,lesson_id,total_questions) VALUES (?,?,?,?)", (attempt_id,telegram_id,lesson_id,total_questions))
        return attempt_id

    def register_poll(self, poll_id: str, attempt_id: str, question_index: int, telegram_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO academy_active_polls (poll_id,attempt_id,question_index,telegram_id) VALUES (?,?,?,?)", (poll_id,attempt_id,question_index,telegram_id))

    def get_poll(self, poll_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM academy_active_polls WHERE poll_id=?", (poll_id,)).fetchone()
        return dict(row) if row else None

    def quiz_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM academy_quiz_attempts WHERE id=?", (attempt_id,)).fetchone()
        return dict(row) if row else None

    def record_poll_answer(self, poll_id: str, selected_option: int, correct_option: int) -> dict[str, Any] | None:
        with self._lock, self._conn:
            poll = self._conn.execute("SELECT * FROM academy_active_polls WHERE poll_id=?", (poll_id,)).fetchone()
            if not poll: return None
            attempt = self._conn.execute("SELECT * FROM academy_quiz_attempts WHERE id=?", (poll["attempt_id"],)).fetchone()
            if not attempt: return None
            correct = int(selected_option == correct_option)
            answer_cursor = self._conn.execute("INSERT OR IGNORE INTO academy_quiz_answers (attempt_id,question_index,selected_option,correct) VALUES (?,?,?,?)", (poll["attempt_id"],poll["question_index"],selected_option,correct))
            if answer_cursor.rowcount == 1 and correct:
                self._conn.execute("UPDATE academy_quiz_attempts SET correct_answers=correct_answers+1 WHERE id=?", (poll["attempt_id"],))
            self._conn.execute("DELETE FROM academy_active_polls WHERE poll_id=?", (poll_id,))
            updated = self._conn.execute("SELECT * FROM academy_quiz_attempts WHERE id=?", (poll["attempt_id"],)).fetchone()
            return dict(updated) if updated else None

    def finish_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE academy_quiz_attempts SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE id=?", (attempt_id,))
            row = self._conn.execute("SELECT * FROM academy_quiz_attempts WHERE id=?", (attempt_id,)).fetchone()
            return dict(row) if row else None

    # ---- Launch notifications -----------------------------------------
    def toggle_launch_notification(self, telegram_id: int, feature_key: str) -> bool:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT 1 FROM academy_launch_notifications WHERE telegram_id=? AND feature_key=?", (telegram_id,feature_key)).fetchone()
            if row:
                self._conn.execute("DELETE FROM academy_launch_notifications WHERE telegram_id=? AND feature_key=?", (telegram_id,feature_key)); return False
            self._conn.execute("INSERT INTO academy_launch_notifications (telegram_id,feature_key) VALUES (?,?)", (telegram_id,feature_key)); return True

    def launch_subscribers(self, feature_key: str) -> list[int]:
        rows = self._conn.execute("SELECT telegram_id FROM academy_launch_notifications WHERE feature_key=? AND notified_at IS NULL", (feature_key,)).fetchall()
        return [int(r[0]) for r in rows]

    def mark_launch_notified(self, telegram_id: int, feature_key: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE academy_launch_notifications SET notified_at=CURRENT_TIMESTAMP WHERE telegram_id=? AND feature_key=?", (telegram_id, feature_key))

    # ---- Badges / certificates ----------------------------------------
    def award_badge(self, telegram_id: int, badge_key: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("INSERT OR IGNORE INTO academy_badges (telegram_id,badge_key) VALUES (?,?)", (telegram_id,badge_key))
            return cur.rowcount == 1

    def badges(self, telegram_id: int) -> list[str]:
        return [r[0] for r in self._conn.execute("SELECT badge_key FROM academy_badges WHERE telegram_id=? ORDER BY awarded_at", (telegram_id,)).fetchall()]

    def issue_certificate(self, telegram_id: int, course_key: str) -> dict[str, Any]:
        """Issue one certificate per user/course, safely under concurrency."""
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT * FROM academy_certificates WHERE telegram_id=? AND course_key=?",
                (telegram_id, course_key),
            ).fetchone()
            if existing:
                return dict(existing)
            code = secrets.token_urlsafe(9).replace("-", "").replace("_", "").upper()
            cid = str(uuid4())
            self._conn.execute(
                """INSERT INTO academy_certificates
                   (id,telegram_id,course_key,verification_code)
                   VALUES (?,?,?,?)
                   ON CONFLICT (telegram_id, course_key) DO NOTHING""",
                (cid, telegram_id, course_key, code),
            )
            row = self._conn.execute(
                "SELECT * FROM academy_certificates WHERE telegram_id=? AND course_key=?",
                (telegram_id, course_key),
            ).fetchone()
            if not row:
                raise RuntimeError("Certificate issuance completed without a certificate row")
            return dict(row)

    def certificate(self, telegram_id: int, course_key: str = "cpp_beginner") -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM academy_certificates WHERE telegram_id=? AND course_key=?", (telegram_id,course_key)).fetchone()
        return dict(row) if row else None
    def certificate_payment(self, telegram_id: int, course_key: str = "cpp_beginner") -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM academy_certificate_payments WHERE telegram_id=? AND course_key=?",
            (telegram_id, course_key),
        ).fetchone()
        return dict(row) if row else None

    def record_certificate_payment(
        self,
        telegram_id: int,
        course_key: str,
        payload: str,
        currency: str,
        amount: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None = None,
    ) -> bool:
        """Persist a successful Stars payment once; safe for Telegram retries."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                """INSERT INTO academy_certificate_payments
                (telegram_id,course_key,payload,currency,amount,telegram_payment_charge_id,provider_payment_charge_id,status)
                VALUES (?,?,?,?,?,?,?,'paid') ON CONFLICT DO NOTHING""",
                (
                    telegram_id,
                    course_key,
                    payload,
                    currency,
                    amount,
                    telegram_payment_charge_id,
                    provider_payment_charge_id,
                ),
            )
            return cur.rowcount == 1

    # ---- Reminders -----------------------------------------------------
    def set_reminders(self, telegram_id: int, enabled: bool, hour: int = 18) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE academy_users SET reminder_enabled=?,reminder_hour=?,updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?", (int(enabled),hour,telegram_id))

    def reminder_users(self, hour: int) -> list[int]:
        rows = self._conn.execute("SELECT telegram_id FROM academy_users WHERE reminder_enabled=1 AND reminder_hour=?", (hour,)).fetchall()
        return [int(r[0]) for r in rows]

    def claim_reminder(self, telegram_id: int) -> bool:
        today = self._local_today().isoformat()
        with self._lock, self._conn:
            row = self._conn.execute(
                """UPDATE academy_users
                   SET last_reminder_date=?, updated_at=CURRENT_TIMESTAMP
                   WHERE telegram_id=? AND last_reminder_date IS DISTINCT FROM ?
                   RETURNING telegram_id""",
                (today, telegram_id, today),
            ).fetchone()
            return row is not None

    # ---- Admin / custom lessons ---------------------------------------
    def user_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM academy_users").fetchone()[0])

    def leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT u.telegram_id, u.full_name, COALESCE(SUM(x.amount),0) AS xp "
            "FROM academy_users u LEFT JOIN academy_xp_events x ON x.telegram_id=u.telegram_id "
            "GROUP BY u.telegram_id, u.full_name ORDER BY xp DESC, u.telegram_id ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def all_user_ids(self) -> list[int]:
        return [int(r[0]) for r in self._conn.execute("SELECT telegram_id FROM academy_users").fetchall()]

    def add_custom_lesson(self, title: str, duration: str, objective: str, theory: str, code: str, examples: str, created_by: int) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute("INSERT INTO academy_custom_lessons (title,duration,objective,theory,code,examples,created_by) VALUES (?,?,?,?,?,?,?) RETURNING id", (title,duration,objective,theory,code,examples,created_by))
            return int(cur.fetchone()[0])

    def sync_admin_lesson(
        self, source_lesson_uuid: str, *, title: str, theory: str, summary: str = "",
        status: str = "DRAFT", created_by: int = 0, code: str = "", examples: str = "",
    ) -> int | None:
        """Mirror a Web Admin lesson into the Telegram runtime catalog.

        Only PUBLISHED lessons are exposed to Telegram. DRAFT/IN_REVIEW/APPROVED/ARCHIVED
        content stays in the normalized admin content tables until it is published.
        """
        if not source_lesson_uuid:
            raise ValueError("source_lesson_uuid is required")
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT id FROM academy_custom_lessons WHERE source_lesson_uuid=?",
                (source_lesson_uuid,),
            ).fetchone()
            if status != "PUBLISHED":
                if row:
                    self._conn.execute("DELETE FROM academy_custom_lessons WHERE source_lesson_uuid=?", (source_lesson_uuid,))
                return None
            duration = ""
            objective = summary or ""
            if row:
                self._conn.execute(
                    """UPDATE academy_custom_lessons
                       SET title=?,duration=?,objective=?,theory=?,code=?,examples=?
                       WHERE source_lesson_uuid=?""",
                    (title[:255], duration, objective[:10000], theory[:200000], code[:50000], examples[:50000], source_lesson_uuid),
                )
                return int(row[0])
            cur = self._conn.execute(
                """INSERT INTO academy_custom_lessons
                   (title,duration,objective,theory,code,examples,created_by,source_lesson_uuid)
                   VALUES (?,?,?,?,?,?,?,?) RETURNING id""",
                (title[:255], duration, objective[:10000], theory[:200000], code[:50000], examples[:50000], int(created_by or 0), source_lesson_uuid),
            )
            return int(cur.fetchone()[0])

    def delete_admin_lesson(self, source_lesson_uuid: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM academy_custom_lessons WHERE source_lesson_uuid=?", (source_lesson_uuid,))

    def custom_lessons(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM academy_custom_lessons ORDER BY id").fetchall()
        return [dict(r) for r in rows]


    # ---- AI learning layer --------------------------------------------
    def ai_history(self, telegram_id: int, limit: int = 12) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, role, content, mode, lesson_id, created_at FROM academy_ai_messages WHERE telegram_id=? AND mode='tutor' ORDER BY id DESC LIMIT ?",
            (telegram_id, max(1, min(limit, 50))),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def add_ai_message(self, telegram_id: int, role: str, content: str, *, mode: str = "tutor", lesson_id: int | None = None) -> int:
        if role not in {"user", "assistant"}:
            raise ValueError("Invalid AI message role")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO academy_ai_messages (telegram_id,role,content,mode,lesson_id) VALUES (?,?,?,?,?) RETURNING id",
                (telegram_id, role, content[:20000], mode[:30], lesson_id),
            )
            # Keep a bounded conversation window per user. The separate ai_memory
            # record can preserve a compact learning summary without retaining an
            # unlimited transcript.
            self._conn.execute(
                "DELETE FROM academy_ai_messages WHERE telegram_id=? AND id NOT IN (SELECT id FROM academy_ai_messages WHERE telegram_id=? ORDER BY id DESC LIMIT 200)",
                (telegram_id, telegram_id),
            )
            return int(cur.fetchone()[0])

    def clear_ai_history(self, telegram_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM academy_ai_messages WHERE telegram_id=?", (telegram_id,))
            self._conn.execute("DELETE FROM academy_ai_memory WHERE telegram_id=?", (telegram_id,))

    def get_ai_memory(self, telegram_id: int) -> str:
        row = self._conn.execute("SELECT summary FROM academy_ai_memory WHERE telegram_id=?", (telegram_id,)).fetchone()
        return str(row[0]) if row else ""

    def refresh_ai_memory(self, telegram_id: int, limit: int = 6) -> str:
        rows = self._conn.execute(
            "SELECT content FROM academy_ai_messages WHERE telegram_id=? AND role='user' ORDER BY id DESC LIMIT ?",
            (telegram_id, max(1, min(limit, 12))),
        ).fetchall()
        questions = [str(r[0]).replace("\n", " ").strip()[:280] for r in reversed(rows)]
        summary = "الأسئلة الأخيرة للطالب:\n" + "\n".join(f"- {q}" for q in questions) if questions else ""
        self.set_ai_memory(telegram_id, summary)
        return summary

    def set_ai_memory(self, telegram_id: int, summary: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO academy_ai_memory (telegram_id,summary) VALUES (?,?) ON CONFLICT(telegram_id) DO UPDATE SET summary=excluded.summary,updated_at=CURRENT_TIMESTAMP",
                (telegram_id, summary[:12000]),
            )

    def ai_usage(self, telegram_id: int) -> dict[str, int]:
        today = self._local_today().isoformat()
        with self._lock, self._conn:
            self._conn.execute("INSERT OR IGNORE INTO academy_ai_usage (telegram_id,usage_date) VALUES (?,?)", (telegram_id, today))
            row = self._conn.execute("SELECT tutor_count,review_count,quiz_count FROM academy_ai_usage WHERE telegram_id=? AND usage_date=?", (telegram_id,today)).fetchone()
        return {"tutor": int(row[0]), "review": int(row[1]), "quiz": int(row[2])}

    def consume_ai_quota(self, telegram_id: int, kind: str, limit: int) -> tuple[bool, int]:
        """Atomically reserve one AI request. Returns (allowed, new_count)."""
        if kind not in {"tutor", "review", "quiz"}:
            raise ValueError("Invalid AI quota kind")
        if limit <= 0:
            return False, 0
        today = self._local_today().isoformat()
        column = f"{kind}_count"
        with self._lock, self._conn:
            self._conn.execute("INSERT OR IGNORE INTO academy_ai_usage (telegram_id,usage_date) VALUES (?,?)", (telegram_id,today))
            cur = self._conn.execute(
                f"UPDATE academy_ai_usage SET {column}={column}+1 WHERE telegram_id=? AND usage_date=? AND {column} < ?",
                (telegram_id,today,limit),
            )
            row = self._conn.execute(f"SELECT {column} FROM academy_ai_usage WHERE telegram_id=? AND usage_date=?", (telegram_id,today)).fetchone()
            current = int(row[0]) if row else 0
            return cur.rowcount == 1, current

    def refund_ai_quota(self, telegram_id: int, kind: str) -> None:
        if kind not in {"tutor", "review", "quiz"}:
            raise ValueError("Invalid AI quota kind")
        today = self._local_today().isoformat()
        column = f"{kind}_count"
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE academy_ai_usage SET {column}=CASE WHEN {column}>0 THEN {column}-1 ELSE 0 END WHERE telegram_id=? AND usage_date=?",
                (telegram_id,today),
            )

    def add_ai_feedback(self, telegram_id: int, message_id: int | None, rating: int, reason: str | None = None) -> None:
        if rating not in {-1, 1}:
            raise ValueError("Invalid AI feedback rating")
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO academy_ai_feedback (telegram_id,message_id,rating,reason) VALUES (?,?,?,?)", (telegram_id,message_id,rating,(reason or "")[:200]))


store = AcademyStore()
