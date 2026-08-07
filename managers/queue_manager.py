import json

from database import db
from managers.carry_manager import carry_manager


class QueueManager:

    def join(self, carry_id: str, user_id: int):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return False, "Carry not found."

        if user_id == carry["host_id"]:
            return False, "You cannot join your own carry."

        if user_id in carry["active"]:
            return False, "Already in active."

        if user_id in carry["waiting"]:
            return False, "Already waiting."

        active = carry["active"]
        waiting = carry["waiting"]

        if len(active) < carry["max_players"]:
            active.append(user_id)
            location = "active"
        else:
            waiting.append(user_id)
            location = "waiting"

        carry_manager.update_lists(
            carry_id,
            active,
            waiting
        )

        return True, location

    def leave(self, carry_id: str, user_id: int):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return False, "Carry not found."

        active = carry["active"]
        waiting = carry["waiting"]

        promoted = None

        if user_id in active:

            active.remove(user_id)

            if waiting:

                promoted = waiting.pop(0)
                active.append(promoted)

        elif user_id in waiting:

            waiting.remove(user_id)

        else:

            return False, "User is not in queue."

        carry_manager.update_lists(
            carry_id,
            active,
            waiting
        )

        return True, promoted

    def is_active(self, carry_id, user_id):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return False

        return user_id in carry["active"]

    def is_waiting(self, carry_id, user_id):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return False

        return user_id in carry["waiting"]

    def get_active(self, carry_id):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return []

        return carry["active"]

    def get_waiting(self, carry_id):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return []

        return carry["waiting"]


queue_manager = QueueManager()
