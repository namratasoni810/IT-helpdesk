from __future__ import annotations

import unittest
from unittest.mock import patch

from app.worker import process_new_tickets


class ProcessNewTicketsTests(unittest.TestCase):
    @patch("app.worker.db.update_ticket_classification")
    @patch(
        "app.worker.classifier.classify_ticket",
        side_effect=RuntimeError("classifier unavailable"),
    )
    @patch("app.worker.db.get_ticket", return_value={"issue_text": "Wi-Fi is down"})
    @patch("app.worker.db.get_new_ticket_ids", return_value=[42])
    def test_failed_classification_is_left_for_retry(
        self,
        _get_new_ticket_ids,
        _get_ticket,
        _classify_ticket,
        update_ticket_classification,
    ) -> None:
        with self.assertLogs("app.worker", level="ERROR"):
            processed = process_new_tickets()

        self.assertEqual(processed, 0)
        update_ticket_classification.assert_not_called()


if __name__ == "__main__":
    unittest.main()
