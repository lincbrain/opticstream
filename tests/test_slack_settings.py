from contextlib import ExitStack
from importlib import import_module
import unittest
from unittest.mock import Mock, patch

from opticstream.utils import slack_settings


hook_module = import_module("opticstream.hooks.slack_notification_hook")
tasks = import_module("opticstream.tasks.slack_notification")


class SlackSettingsTests(unittest.TestCase):
    def test_default_and_runtime_changes(self):
        values = {}
        with patch.object(
            slack_settings.Variable, "get",
            side_effect=lambda name, default=None: values.get(name, default),
        ):
            self.assertIs(slack_settings.slack_notifications_enabled(), True)
            values["slack-notifications-enabled"] = False
            self.assertIs(slack_settings.slack_notifications_enabled(), False)
            values["slack-notifications-enabled"] = True
            self.assertIs(slack_settings.slack_notifications_enabled(), True)

    def test_rejects_non_boolean_values(self):
        for value in ("false", "true", None, 0, 1, {}):
            with self.subTest(value=value), patch.object(
                slack_settings.Variable, "get", return_value=value,
            ):
                with self.assertRaisesRegex(ValueError, "JSON boolean"):
                    slack_settings.slack_notifications_enabled()

    def test_disabled_skips_all_slack_paths_before_loading_blocks(self):
        def read_toggle(name, default=None):
            self.assertEqual(name, "slack-notifications-enabled")
            return False

        forbidden = Mock(side_effect=AssertionError("Slack must not be accessed"))
        webhook = Mock()
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                slack_settings.Variable, "get", side_effect=read_toggle,
            ))
            for block in (tasks.SlackCredentials, tasks.Secret, tasks.SlackWebhook):
                stack.enter_context(patch.object(block, "load", forbidden))
            stack.enter_context(patch.object(tasks, "WebClient", forbidden))
            stack.enter_context(patch.object(tasks.os.path, "exists", forbidden))
            hook_module.slack_notification_hook(None, None, None)
            self.assertIs(tasks.send_slack_message.fn("test"), False)
            self.assertIs(tasks.send_slack_message.fn("test", "token", "channel"), False)
            self.assertIs(tasks.send_slack_message_webhook.fn("test"), False)
            self.assertIs(
                tasks.send_slack_message_webhook.fn("test", webhook=webhook), False,
            )
            self.assertEqual(
                tasks.upload_multiple_files_to_slack.fn(["missing.nii"]),
                {"missing.nii": False},
            )
        forbidden.assert_not_called()
        webhook.notify.assert_not_called()

    def test_enabled_webhook_still_sends(self):
        webhook = Mock()
        with patch.object(slack_settings.Variable, "get", return_value=True), patch.object(
            tasks.SlackWebhook, "load", return_value=webhook,
        ) as load:
            tasks.send_slack_message_webhook.fn("test", subject="subject")
        load.assert_called_once_with("watchdog")
        webhook.notify.assert_called_once_with("test", subject="subject")
