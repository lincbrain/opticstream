"""Runtime switch shared by Slack hooks and notification tasks."""

from prefect.logging.loggers import get_logger
from prefect.variables import Variable

from opticstream.config.constants import SLACK_NOTIFICATIONS_ENABLED_VARIABLE_NAME


def slack_notifications_enabled() -> bool:
    """Read the server-wide switch each time; absent means enabled."""
    enabled = Variable.get(SLACK_NOTIFICATIONS_ENABLED_VARIABLE_NAME, default=True)
    if not isinstance(enabled, bool):
        raise ValueError(
            f"{SLACK_NOTIFICATIONS_ENABLED_VARIABLE_NAME} must be a JSON boolean "
            "(true or false), not a string or another value."
        )
    if not enabled:
        get_logger(__name__).info("Slack notifications disabled; skipping.")
    return enabled
