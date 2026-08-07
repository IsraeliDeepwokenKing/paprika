import time

from database import db


class LogManager:

    def add(
        self,
        carry_id: str,
        user_id: int,
        action: str
    ):

        db.cursor.execute(
            """
            INSERT INTO carry_logs
            (
                carry_id,
                user_id,
                action,
                timestamp
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                carry_id,
                user_id,
                action,
                int(time.time())
            )
        )

        db.conn.commit()



    def get(self, carry_id: str):

        rows = db.cursor.execute(
            """
            SELECT
                user_id,
                action,
                timestamp
            FROM carry_logs
            WHERE carry_id=?
            ORDER BY timestamp ASC
            """,
            (carry_id,)
        ).fetchall()

        return rows



    def clear(self, carry_id: str):

        db.cursor.execute(
            """
            DELETE FROM carry_logs
            WHERE carry_id=?
            """,
            (carry_id,)
        )

        db.conn.commit()



log_manager = LogManager()
