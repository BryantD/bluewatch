# bluewatch

A command-line tool for monitoring Bluesky user timelines using the AT Protocol. Watch for specific patterns in posts and trigger webhooks or shell commands when matches are found.

## Requirements
- Python 3.11+
- uv (for dependency management and running the script)

## Setup
Clone the repository and sync dependencies:
```bash
uv sync
```

Create a config file `config.toml` (not checked in) based on `config.toml.example`:
```toml
# Bluesky credentials
[bluesky]
username = "your.handle"
password = "your-password"

# Define scans to monitor timelines
[[scan]]
name = "crypto_watch"
handle = "example_user"
pattern = "bitcoin|crypto"
webhook_url = "https://your-webhook.com/endpoint"
limit = 10

[[scan]]
name = "news_alerts"
handle = "news_account"
pattern = "breaking|urgent"
shell = "notify-send 'News Alert' '{text}'"
limit = 20
```

## Usage

### View a user's timeline
```bash
uv run ./bluewatch.py timeline example_user --limit 5
```

### Run configured scans
```bash
# Run all configured scans
uv run ./bluewatch.py scan

# Run a specific scan by name
uv run ./bluewatch.py scan crypto_watch
```

### Configuration Options

#### Scan Configuration
Each `[[scan]]` block supports:
- `name` - Unique identifier for the scan
- `handle` - Bluesky user handle to monitor
- `pattern` - Regular expression pattern (case-insensitive)
- `webhook_url` - HTTP endpoint to call when matches found (optional)
- `shell` - Shell command to execute when matches found (optional)
- `limit` - Number of recent posts to scan (default: 10)

**Note**: Each scan must have either `webhook_url` or `shell` (or both).

#### String Formatting in Shell Commands
Shell commands support string formatting with these fields:
- `{text}` - The matched post text
- `{created_at}` - Post creation timestamp
- `{handle}` - User handle that posted
- `{pattern}` - The regex pattern that matched

Example:
```toml
shell = "echo '[{created_at}] Alert from {handle}: {text}' >> alerts.log"
```

#### Webhook Payload
When a webhook is triggered, it receives a JSON payload:
```json
{
  "scan_name": "crypto_watch",
  "matches": [
    {
      "handle": "example_user",
      "created_at": "2024-01-01T12:00:00Z",
      "text": "Bitcoin is rising!",
      "pattern": "bitcoin|crypto"
    }
  ],
  "total_matches": 1,
  "scanned_posts": 10
}
```

## Installation
For system-wide use:
```bash
pip install .
```

Then use `bluewatch` instead of `uv run ./bluewatch.py`.

## Help
```bash
uv run ./bluewatch.py --help
```