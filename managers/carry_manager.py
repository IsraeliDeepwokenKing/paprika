import json
import random
import string
import time

from database import db


class CarryManager:

    def generate_id(self):

        while True:

            carry_id = "".join(
                random.choices(
                    string.ascii_uppercase + string.digits,
                    k=6
                )
            )

            row = db.cursor.execute(
                """
                SELECT carry_id
                FROM carries
                WHERE carry_id=?
                """,
                (carry_id,)
            ).fetchone()

            if row is None:
                return carry_id

    def create(
        self,
        carry_id: str,
        guild_id: int,
        host_id: int,
        boss: str,
        max_players: int,
        stage_id: int,
        message_id: int,
        channel_id: int,
        role_id: int
    ):

        db.cursor.execute(
            """
            INSERT INTO carries(
                carry_id,
                guild_id,
                host_id,
                boss,
                max_players,
                stage_id,
                message_id,
                channel_id,
                role_id,
                active,
                waiting,
                created
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                carry_id,
                guild_id,
                host_id,
                boss,
                max_players,
                stage_id,
                message_id,
                channel_id,
                role_id,
                json.dumps([]),
                json.dumps([]),
                int(time.time())
            )
        )

        db.conn.commit()

    def get(self, carry_id: str):

        row = db.cursor.execute(
            """
            SELECT *
            FROM carries
            WHERE carry_id=?
            """,
            (carry_id,)
        ).fetchone()

        if row is None:
            return None

        return {
            "carry_id": row[0],
            "guild_id": row[1],
            "host_id": row[2],
            "boss": row[3],
            "max_players": row[4],
            "stage_id": row[5],
            "message_id": row[6],
            "channel_id": row[7],
            "role_id": row[8],
            "active": json.loads(row[9]),
            "waiting": json.loads(row[10]),
            "created": row[11]
        }

    def update_lists(
        self,
        carry_id: str,
        active: list,
        waiting: list
    ):

        db.cursor.execute(
            """
            UPDATE carries
            SET active=?, waiting=?
            WHERE carry_id=?
            """,
            (
                json.dumps(active),
                json.dumps(waiting),
                carry_id
            )
        )

        db.conn.commit()

    def set_message(
        self,
        carry_id: str,
        message_id: int
    ):

        db.cursor.execute(
            """
            UPDATE carries
            SET message_id=?
            WHERE carry_id=?
            """,
            (
                message_id,
                carry_id
            )
        )

        db.conn.commit()

    def set_stage(
        self,
        carry_id: str,
        stage_id: int
    ):

        db.cursor.execute(
            """
            UPDATE carries
            SET stage_id=?
            WHERE carry_id=?
            """,
            (
                stage_id,
                carry_id
            )
        )

        db.conn.commit()

    def set_role(
        self,
        carry_id: str,
        role_id: int
    ):

        db.cursor.execute(
            """
            UPDATE carries
            SET role_id=?
            WHERE carry_id=?
            """,
            (
                role_id,
                carry_id
            )
        )

        db.conn.commit()

    def host_has_carry(
        self,
        host_id: int
    ):

        row = db.cursor.execute(
            """
            SELECT 1
            FROM carries
            WHERE host_id=?
            """,
            (host_id,)
        ).fetchone()

        return row is not None

    def get_by_host(
        self,
        host_id: int
    ):

        row = db.cursor.execute(
            """
            SELECT carry_id
            FROM carries
            WHERE host_id=?
            """,
            (host_id,)
        ).fetchone()

        if row is None:
            return None

        return self.get(row[0])

    def get_by_message(
        self,
        message_id: int
    ):

        row = db.cursor.execute(
            """
            SELECT carry_id
            FROM carries
            WHERE message_id=?
            """,
            (message_id,)
        ).fetchone()

        if row is None:
            return None

        return self.get(row[0])

    def player_count(
        self,
        carry_id: str
    ):

        carry = self.get(carry_id)

        if carry is None:
            return 0

        return len(carry["active"])

    def is_full(
        self,
        carry_id: str
    ):

        carry = self.get(carry_id)

        if carry is None:
            return False

        return len(carry["active"]) >= carry["max_players"]

    def delete(
        self,
        carry_id: str
    ):

        db.cursor.execute(
            """
            DELETE FROM carries
            WHERE carry_id=?
            """,
            (carry_id,)
        )

        db.conn.commit()


carry_manager = CarryManager()
