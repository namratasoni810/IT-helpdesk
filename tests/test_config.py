from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import get_settings


class SettingsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_agent_mode_does_not_require_anthropic_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "",
                "CLASSIFIER_MODE": "agent",
                "AGENT_APP_NAME": "test-agent",
                "API_PORT": "8001",
                "HELPDESK_API_URL": "",
            },
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.classifier_mode, "agent")
        self.assertEqual(settings.agent_app_name, "test-agent")
        self.assertEqual(settings.api_base_url, "http://127.0.0.1:8001")

    def test_agent_mode_requires_app_resource(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "",
                "CLASSIFIER_MODE": "agent",
                "AGENT_APP_NAME": "",
            },
        ):
            get_settings.cache_clear()
            with self.assertRaisesRegex(ValueError, "AGENT_APP_NAME is required"):
                get_settings()

    def test_api_url_can_be_overridden(self) -> None:
        with patch.dict(
            os.environ,
            {
                "API_PORT": "8001",
                "HELPDESK_API_URL": "https://api.example.test/",
            },
        ):
            get_settings.cache_clear()
            settings = get_settings()

        self.assertEqual(settings.api_base_url, "https://api.example.test")


if __name__ == "__main__":
    unittest.main()
