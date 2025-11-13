from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from assignment_bot.storage import AssignmentError, AssignmentStorage


def _make_storage(temp_dir: str) -> AssignmentStorage:
    db_path = Path(temp_dir) / "assignment.sqlite3"
    return AssignmentStorage(db_path)


class AssignmentStorageTestCase(unittest.TestCase):
    def test_record_user_creation_and_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            created = storage.record_user(
                111,
                username="first_user",
                first_name="Ali",
                last_name="Valiyev",
            )
            self.assertTrue(created)

            created_again = storage.record_user(
                111,
                username="first_user2",
                first_name="Ali",
                last_name="Valiyev",
            )
            self.assertFalse(created_again)

            user = storage.get_user(111)
            self.assertIsNotNone(user)
            assert user  # Type narrowing for mypy/pyright
            self.assertEqual(user.username, "first_user2")

    def test_assign_sales_manager_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            storage.record_group_chat(123, title="Guruh")
            storage.record_user(111, username="manager", first_name="Ali", last_name=None)

            storage.assign_sales_manager(chat_id=123, user_id=111)

            assignment = storage.get_group_assignment(123)
            self.assertIsNotNone(assignment)
            assert assignment
            self.assertEqual(assignment["user_id"], 111)

    def test_assign_sales_manager_prevents_duplicate_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            storage.record_group_chat(1, title=None)
            storage.record_group_chat(2, title=None)
            storage.record_user(111, username=None, first_name=None, last_name=None)

            storage.assign_sales_manager(chat_id=1, user_id=111)

            with self.assertRaisesRegex(AssignmentError, "boshqa guruhda"):
                storage.assign_sales_manager(chat_id=2, user_id=111)

    def test_assign_sales_manager_blocks_existing_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            storage.record_group_chat(1, title=None)
            storage.record_user(111, username=None, first_name="Ali", last_name=None)
            storage.record_user(222, username=None, first_name="Vali", last_name=None)

            storage.assign_sales_manager(chat_id=1, user_id=111)

            with self.assertRaisesRegex(AssignmentError, "allaqachon"):
                storage.assign_sales_manager(chat_id=1, user_id=222)

    def test_store_api_credentials_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(tmp)
            storage.record_group_chat(1, title="Test group")
            storage.record_user(111, username="manager", first_name="Ali", last_name=None)

            storage.assign_sales_manager(chat_id=1, user_id=111)

            assignment = storage.get_user_assignment(111)
            self.assertIsNotNone(assignment)
            assert assignment
            self.assertEqual(assignment["credentials_status"], "pending_key")

            storage.store_api_key(111, "3739e78cec4e139")
            assignment = storage.get_user_assignment(111)
            assert assignment
            self.assertEqual(assignment["api_key"], "3739e78cec4e139")
            self.assertEqual(assignment["credentials_status"], "pending_secret")

            storage.store_api_secret(111, "2a428d03deaceb8", verified=True)
            assignment = storage.get_user_assignment(111)
            assert assignment
            self.assertEqual(assignment["api_secret"], "2a428d03deaceb8")
            self.assertEqual(assignment["credentials_status"], "active")

            storage.clear_all_assignments()
            self.assertIsNone(storage.get_user_assignment(111))


if __name__ == "__main__":
    unittest.main()
