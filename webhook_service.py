import logging
import requests
import uuid
import os
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# SuperDuperFeeder API base URL
FEEDER_BASE_URL = "https://superduperfeeder.deno.dev/api/"
CALLBACK_URL = "https://tldr.express/api/webhook"


def generate_callback_url(app_url):
    """Generate a callback URL for the webhook service."""
    # Use the app_url parameter instead of hardcoded CALLBACK_URL
    # to ensure we're generating a proper URL based on the current deployment
    return urljoin(app_url, "/api/webhook")


def register_webhook(feed_url, callback_url):
    """Register a webhook for a feed with the SuperDuperFeeder webhook API.
    
    Args:
        feed_url: The URL of the RSS feed to monitor
        callback_url: The callback URL to ping when the feed is updated
        
    Returns:
        dict: The response from the webhook service, containing at least a 'id' field
              on success or None on failure
    """
    try:
        logger.info(f"Registering webhook for feed: {feed_url}")

        endpoint = urljoin(FEEDER_BASE_URL, "webhook")

        # Using form-encoded data as required by SuperDuperFeeder webhook API
        form_data = {
            "topic": feed_url,
            "callback": callback_url,
            "secret": os.environ.get("WEBHOOK_SECRET", str(uuid.uuid4()))
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'tldr.express'
        }

        response = requests.post(endpoint, data=form_data, headers=headers)
        response.raise_for_status()

        webhook_data = response.json()
        webhook_id = webhook_data.get('subscriptionId')

        if not webhook_id:
            logger.error(
                f"Webhook registration response missing 'subscriptionId': {webhook_data}"
            )
            return None

        logger.info(
            f"Successfully registered webhook (ID: {webhook_id}) for feed: {feed_url}"
        )
        return webhook_data

    except requests.RequestException as e:
        logger.error(
            f"Error registering webhook for feed {feed_url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error registering webhook: {str(e)}",
                     exc_info=True)
        return None


def unregister_webhook(webhook_id):
    """Unregister a webhook with the SuperDuperFeeder webhook API.
    
    Args:
        webhook_id: The ID of the webhook to unregister
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if not webhook_id:
            logger.warning("Attempted to unregister webhook with no ID")
            return False

        logger.info(f"Unregistering webhook (ID: {webhook_id})")

        endpoint = urljoin(FEEDER_BASE_URL, f"webhook/{webhook_id}")

        response = requests.delete(endpoint)
        response.raise_for_status()

        logger.info(f"Successfully unregistered webhook (ID: {webhook_id})")
        return True

    except requests.RequestException as e:
        logger.error(
            f"Error unregistering webhook (ID: {webhook_id}): {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error unregistering webhook: {str(e)}",
                     exc_info=True)
        return False


def verify_webhook_signature(request_headers, request_body):
    """Verify the signature of a webhook callback.
    
    This is a placeholder for future implementation of security verification.
    When the SuperDuperFeeder service implements signature verification,
    this function should be updated to verify the signature.
    
    Args:
        request_headers: The headers of the webhook request
        request_body: The body of the webhook request
        
    Returns:
        bool: Always returns True for now
    """
    # TODO: Implement proper signature verification when SuperDuperFeeder adds support
    logger.info(
        "Webhook signature verification called (placeholder implementation)")

    # For now, we're simply checking for the existence of the request body
    if not request_body:
        logger.warning("Empty request body in webhook call")
        return False

    # Return True as we don't have actual signature verification yet
    return True
