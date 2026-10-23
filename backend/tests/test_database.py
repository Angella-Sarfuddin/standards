import unittest
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

import database


class DatabaseDependencyTests(unittest.TestCase):
    def test_dbapi_error_during_dependency_cleanup_does_not_escape(self):
        class Session:
            closed = False

            def close(self):
                self.closed = True
                raise OperationalError("close", None, OSError("connection lost"))

        session = Session()
        with patch.object(database, "SessionLocal", return_value=session):
            dependency = database.get_db()
            self.assertIs(next(dependency), session)
            with self.assertRaises(StopIteration):
                next(dependency)
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
