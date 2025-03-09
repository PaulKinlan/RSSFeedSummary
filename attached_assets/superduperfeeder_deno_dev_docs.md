URL: https://superduperfeeder.deno.dev/docs#webhook-api
---
## Introduction

Super Duper Feeder is a spec-compliant WebSub/PubSubHubbub service that allows users to subscribe to RSS feeds
and get notified when new content is available. It provides real-time updates via WebSockets, Server-Sent Events
(SSE), and webhooks.


This documentation provides detailed information about the service's features, API endpoints, and usage
examples.


## WebSub Concepts

WebSub (formerly PubSubHubbub) is a protocol that enables real-time notifications for content updates. It
involves three main components:


- **Publishers**: Content creators who notify the hub when they update their content
- **Hub**: A server (like Super Duper Feeder) that receives update notifications from publishers
   and forwards them to subscribers
- **Subscribers**: Services or applications that want to receive real-time updates about content
   changes

The flow works as follows:


1. A subscriber discovers the hub URL from a publisher's feed
2. The subscriber sends a subscription request to the hub
3. The hub verifies the subscription request with the subscriber
4. When the publisher updates content, they notify the hub
5. The hub fetches the updated content and sends it to all subscribers

## API Reference

### Quick Navigation

- [WebSub Hub Endpoints](https://superduperfeeder.deno.dev/docs#hub-endpoints)
- [Webhook API](https://superduperfeeder.deno.dev/docs#webhook-api)
- [Callback Endpoint](https://superduperfeeder.deno.dev/docs#callback-endpoint)
- [Health Check](https://superduperfeeder.deno.dev/docs#health-check)

### WebSub Hub Endpoints

#### Main Hub Endpoint

`POST /`

This endpoint handles both subscription and publishing operations.

##### For Publishers

To publish updates to the hub:

```
POST /
Content-Type: application/x-www-form-urlencoded

hub.mode=publish&hub.url=https://example.com/feed.xml
```

##### For Subscribers

To subscribe to updates:

```
POST /
Content-Type: application/x-www-form-urlencoded

hub.callback=https://example.com/callback&hub.mode=subscribe&hub.topic=https://example.com/feed.xml&hub.lease_seconds=86400
```

To unsubscribe:

```
POST /
Content-Type: application/x-www-form-urlencoded

hub.callback=https://example.com/callback&hub.mode=unsubscribe&hub.topic=https://example.com/feed.xml
```

#### List Webhooks

`GET /firehose/webhook`

List all registered webhooks.

#### WebSub Subscription Endpoint

`POST /api/webhook`

Subscribe to a feed using WebSub, with automatic hub discovery. This endpoint will attempt to find the WebSub
hub for the specified feed and subscribe to it. If no hub is found, it will fall back to using the Super Duper
Feeder's own hub.

##### Request Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `topic` | string | Yes | The URL of the feed to subscribe to. This can be an RSS, Atom, or JSON feed, or an HTML page with feed<br> autodiscovery links. |
| `callback` | string | No | Your callback URL where updates will be forwarded. If not provided, you can still access updates via<br> the firehose endpoints. |

##### Response

Status Code: `202 Accepted` on success, `400 Bad Request` on error,
`500 Internal Server Error` on server error


Response Body (JSON):

```
{
  "success": true|false,
  "message": "Description of the result",
  "usingExternalHub": true|false,
  "subscriptionId": "uuid-of-subscription",
  "callbackId": "uuid-of-callback" // Only if callback was provided
}
```

##### Success Response Fields

| Field | Type | Description |
| --- | --- | --- |
| `success` | boolean | Indicates if the subscription request was successful |
| `message` | string | A human-readable description of the result |
| `usingExternalHub` | boolean | Indicates if an external WebSub hub was found and used (true) or if the service fell back to its own<br> hub (false) |
| `subscriptionId` | string | The UUID of the created subscription, useful for tracking |
| `callbackId` | string | The UUID of the created callback, only present if a callback URL was provided |

##### Error Responses

| Status Code | Error Message | Description |
| --- | --- | --- |
| 400 | Missing topic parameter | The required topic parameter was not provided |
| 400 | Failed to add feed for polling | The service could not add the feed for polling (when using fallback hub) |
| 500 | Internal server error: \[error details\] | An unexpected error occurred on the server |

##### Example Usage

```
// Using fetch API in JavaScript
async function subscribeToFeed(topicUrl, callbackUrl) {
  const formData = new FormData();
  formData.append('topic', topicUrl);

  if (callbackUrl) {
    formData.append('callback', callbackUrl);
  }

  const response = await fetch('https://superduperfeeder.deno.dev/api/webhook', {
    method: 'POST',
    body: formData
  });

  const result = await response.json();

  if (result.success) {
    console.log(`Successfully subscribed to ${topicUrl}`);
    console.log(`Using external hub: ${result.usingExternalHub}`);
    console.log(`Subscription ID: ${result.subscriptionId}`);

    if (result.callbackId) {
      console.log(`Callback ID: ${result.callbackId}`);
    }
  } else {
    console.error(`Failed to subscribe: ${result.message}`);
  }
}
```

##### Notes

- The service will automatically discover the WebSub hub for the feed by checking:
1. HTTP Link headers with `rel="hub"`
2. Feed content for hub links
3. HTML content for hub links or feed autodiscovery links
- If no WebSub hub is found, the service will use its own hub as a fallback
- If a callback URL is provided, updates will be forwarded to that URL
- If no callback URL is provided, you can still access updates via the firehose endpoints
- Subscriptions have a default lease time and will be automatically renewed

#### Callback Endpoint

`GET/POST /callback/:id`

This endpoint handles callbacks from external WebSub hubs. It's used internally by the system and not meant
to be called directly by users.

##### For Verification (GET)

When a hub verifies a subscription, it sends a GET request with the following parameters:

- `hub.mode`: Either "subscribe" or "unsubscribe"
- `hub.topic`: The feed URL being subscribed to
- `hub.challenge`: A challenge string that must be echoed back
- `hub.lease_seconds`: (Optional) The subscription duration in seconds

##### For Content Delivery (POST)

When a hub sends content updates, it sends a POST request with:

- A `Link` header containing the topic URL with `rel="self"`
- The updated feed content in the request body

The service will forward these updates to any registered callback URLs for the topic.

#### Health Check

`GET /health`

Check if the service is running properly.

## Usage Examples

### Publishing Updates

When you update your content, notify the hub:


```
// Using fetch API in JavaScript
async function notifyHub(feedUrl) {
  const response = await fetch('https://superduperfeeder.deno.dev/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      'hub.mode': 'publish',
      'hub.url': feedUrl,
    }),
  });

  if (response.ok) {
    console.log('Hub notified successfully');
  } else {
    console.error('Failed to notify hub:', await response.text());
  }
}
```

### Subscribing to Updates

To subscribe to updates for a feed:


```
// Using fetch API in JavaScript
async function subscribe(callbackUrl, topicUrl, leaseSeconds = 86400) {
  const response = await fetch('https://superduperfeeder.deno.dev/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      'hub.callback': callbackUrl,
      'hub.mode': 'subscribe',
      'hub.topic': topicUrl,
      'hub.lease_seconds': leaseSeconds.toString(),
    }),
  });

  if (response.ok) {
    console.log('Subscription request sent successfully');
  } else {
    console.error('Failed to send subscription request:', await response.text());
  }
}
```

### Handling WebSub Verification

When the hub verifies a subscription, it sends a GET request to your callback URL:


```
// Example using Express.js
app.get('/callback', (req, res) => {
  const mode = req.query['hub.mode'];
  const topic = req.query['hub.topic'];
  const challenge = req.query['hub.challenge'];
  const leaseSeconds = req.query['hub.lease_seconds'];

  if (mode === 'subscribe' || mode === 'unsubscribe') {
    // Verify that this subscription/unsubscription is expected
    // If it is, respond with the challenge
    res.send(challenge);
  } else {
    res.status(400).send('Invalid request');
  }
});
```

### Receiving Updates

When the hub sends updates to your callback URL:


```
// Example using Express.js
app.post('/callback', express.raw({ type: 'application/atom+xml' }), (req, res) => {
  const contentType = req.headers['content-type'];
  const body = req.body.toString();

  // Process the update (body contains the updated feed content)
  console.log('Received update:', body);

  // Acknowledge receipt
  res.status(200).end();
});
```

## Best Practices

- Always verify subscription requests to prevent spam
- Implement proper error handling for all API calls
- Use appropriate lease times for subscriptions (typically 1-7 days)
- Implement retry logic for failed webhook deliveries
- Consider using WebSockets or SSE for real-time applications
- Ensure your callback endpoint responds quickly to hub requests

## Troubleshooting

### Common Issues

- **Subscription verification fails**
  Ensure your callback URL is publicly accessible and responds correctly to verification requests.

- **Not receiving updates**
  Check that your subscription is active and that your callback endpoint is functioning properly.

- **WebSocket connection drops**
  Implement reconnection logic with exponential backoff.