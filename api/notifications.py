"""
FCM push notification helper using Firebase Admin SDK.
firebase-admin is already installed and initialized in settings.py.
"""
import logging
from firebase_admin import messaging

logger = logging.getLogger(__name__)


def send_fcm_notification(fcm_token, title, body, data=None):
    """Send a push notification to a single device.

    Args:
        fcm_token: The device FCM registration token (stored in Farm.fcm_token)
        title: Notification title string
        body: Notification body string
        data: Optional dict of string key-value pairs for the notification payload
    """
    if not fcm_token or not fcm_token.strip():
        return

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        token=fcm_token.strip(),
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                sound='default',
                channel_id='aviansense_alerts',
            ),
        ),
    )

    try:
        messaging.send(message)
    except Exception as e:
        # Never let notification failure break the main request
        logger.warning(f'FCM notification failed: {e}')
