from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from run_app import _wait_for_api


class WaitForApiTests(unittest.TestCase):
    @patch("run_app.time.sleep")
    @patch("run_app.time.monotonic", side_effect=[0, 1, 2])
    @patch(
        "run_app.requests.get",
        side_effect=[
            requests.ConnectionError("starting"),
            Mock(status_code=200),
        ],
    )
    def test_waits_until_health_check_succeeds(
        self,
        get: Mock,
        _monotonic: Mock,
        _sleep: Mock,
    ) -> None:
        process = Mock()
        process.poll.return_value = None

        _wait_for_api(process, "http://127.0.0.1:8001")

        self.assertEqual(get.call_count, 2)

    def test_fails_if_api_exits_during_startup(self) -> None:
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1

        with self.assertRaisesRegex(RuntimeError, "exited during startup"):
            _wait_for_api(process, "http://127.0.0.1:8001")


if __name__ == "__main__":
    unittest.main()
