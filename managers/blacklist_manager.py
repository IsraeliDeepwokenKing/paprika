from database import db


class BlacklistManager:

    # ------------------------
    # ADD PLAYER
    # ------------------------

    def add(
        self,
        host_id: int,
        player_id: int
    ):

        if self.is_blacklisted(
            host_id,
            player_id
        ):
            return False

        db.cursor.execute(
            """
            INSERT INTO blacklist
            (
                host_id,
                player_id
            )
            VALUES (?, ?)
            """,
            (
                host_id,
                player_id
            )
        )

        db.conn.commit()

        return True


    # ------------------------
    # REMOVE PLAYER
    # ------------------------

    def remove(
        self,
        host_id: int,
        player_id: int
    ):

        db.cursor.execute(
            """
            DELETE FROM blacklist
            WHERE host_id=?
            AND player_id=?
            """,
            (
                host_id,
                player_id
            )
        )

        db.conn.commit()


    # ------------------------
    # CHECK
    # ------------------------

    def is_blacklisted(
        self,
        host_id: int,
        player_id: int
    ) -> bool:

        row = db.cursor.execute(
            """
            SELECT 1
            FROM blacklist
            WHERE host_id=?
            AND player_id=?
            """,
            (
                host_id,
                player_id
            )
        ).fetchone()

        return row is not None


    # ------------------------
    # GET ALL
    # ------------------------

    def get_players(
        self,
        host_id: int
    ):

        rows = db.cursor.execute(
            """
            SELECT player_id
            FROM blacklist
            WHERE host_id=?
            """,
            (
                host_id,
            )
        ).fetchall()

        return [row[0] for row in rows]


    # ------------------------
    # CLEAR
    # ------------------------

    def clear(
        self,
        host_id: int
    ):

        db.cursor.execute(
            """
            DELETE FROM blacklist
            WHERE host_id=?
            """,
            (
                host_id,
            )
        )

        db.conn.commit()


blacklist_manager = BlacklistManager()
