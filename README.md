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

[[scan]]
name = "news_alerts"
handle = "news_account"
pattern = "breaking|urgent"
shell = "notify-send 'News Alert' '{text}'"
```

## Usage


### Run configured scans
```bash
# Run all configured scans
uv run ./bluewatch.py scan

# Run a specific scan by name
uv run ./bluewatch.py scan crypto_watch

# With logging levels
uv run ./bluewatch.py scan --log-level debug    # Verbose output
uv run ./bluewatch.py scan --log-level warning  # Quiet (warnings/errors only)
uv run ./bluewatch.py scan --log-level error    # Silent (errors only)

# Test a scan configuration against a specific post
uv run ./bluewatch.py test crypto_watch https://bsky.app/profile/user.bsky.social/post/abc123
uv run ./bluewatch.py test crypto_watch POST_URL --execute  # Actually trigger webhook/shell if match found

# View scan status and history
uv run ./bluewatch.py status
uv run ./bluewatch.py status crypto_watch

# Reset scan state (start fresh)
uv run ./bluewatch.py reset crypto_watch
```

### Configuration Options

#### Scan Configuration
Each `[[scan]]` block supports:
- `name` - Unique identifier for the scan
- `handle` - Bluesky user handle to monitor
- `pattern` - Regular expression pattern (case-insensitive)
- `webhook_url` - HTTP endpoint to call when matches found (optional)
- `shell` - Shell command to execute when matches found (optional)
- `shell_executable` - Path to shell executable (optional, defaults to `/bin/sh`)

**Note**: Each scan must have either `webhook_url` or `shell` (or both).

Scans automatically fetch all posts since the last scan (up to 24 hours ago) to avoid missing content.

#### String Formatting in Shell Commands
Shell commands support string formatting with these fields:
- `{text}` - The matched post text
- `{created_at}` - Post creation timestamp
- `{handle}` - User handle that posted
- `{pattern}` - The regex pattern that matched
- `{uri}` - AT Protocol URI of the post
- `{url}` - Web-accessible URL to the post

**Security**: All substituted values are automatically escaped using `shlex.quote()` to prevent shell injection and handle special characters safely. You don't need to manually quote the placeholder fields - just write `{text}` not `"{text}"`. Shell features like variables (`$VAR`), pipes (`|`), and redirects (`>`) in your command template work normally.

Example:
```toml
shell = "echo '[{created_at}] Alert from {handle}: {text}' >> alerts.log"
```

To use bash-specific features like `$RANDOM`, specify the shell executable:
```toml
[[scan]]
name = "example"
handle = "user.bsky.social"
pattern = "important"
shell_executable = "/bin/bash"
shell = """
TMP=/tmp/alert.$RANDOM
echo {text} > $TMP
process-alert $TMP
rm $TMP
"""
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
      "pattern": "bitcoin|crypto",
      "uri": "at://did:plc:xyz123/app.bsky.feed.post/abc456",
      "url": "https://bsky.app/profile/example_user/post/abc456"
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