# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Tasks

### Running the Application
```bash
# Run all configured scans
uv run ./bluewatch.py scan

# Run specific scan by name
uv run ./bluewatch.py scan crypto_watch

# With logging levels
uv run ./bluewatch.py scan --log-level debug    # Verbose output
uv run ./bluewatch.py scan --log-level warning  # Quiet (warnings/errors only)
uv run ./bluewatch.py scan --log-level error    # Silent (errors only)

# View scan status
uv run ./bluewatch.py status
uv run ./bluewatch.py status crypto_watch

# Reset scan state
uv run ./bluewatch.py reset crypto_watch

# With custom config file
uv run ./bluewatch.py scan --config /path/to/config.toml

# Get help
uv run ./bluewatch.py --help
```

### Dependency Management
```bash
# Sync dependencies
uv sync

# Add new dependency (update script header too)
uv add package_name
```

### Installation
```bash
# Install for system-wide use
pip install .
```

## Architecture

### Single-File Application
This is a single-file Python CLI application (`bluewatch.py`) that uses PEP 723 dependency specification in the script header. The application structure is:

- **Main Module**: `bluewatch.py` - Contains all CLI commands and logic
- **Configuration**: `config.toml` - Stores credentials and scan configurations (not in git)
- **Dependencies**: Managed via `uv` and specified in script header

### Core Components

**CLI Framework**: Uses Click for command-line interface
- Main command group: `cli()`
- Scan command: `scan()` - Runs configured pattern monitoring
- Status command: `status()` - Shows scan state and timestamps
- Reset command: `reset()` - Clears scan state from database
- Configuration loading: `load_config()` - Loads TOML config files

**Bluesky Integration**: Uses AT Protocol client
- Authentication via username/password from config
- Timeline fetching via `get_author_feed()`
- Error handling for network and API failures

**Scan System**: Pattern-based timeline monitoring
- Backward scanning: fetches all posts since last scan (up to 24 hours)
- Pagination with 100 posts per API call and 10-second rate limiting
- Regex pattern matching (case-insensitive)
- Multiple scan configurations via `[[scan]]` TOML blocks
- Webhook notifications with JSON payloads including post URIs/URLs
- Shell command execution with string formatting
- Validation requiring webhook_url or shell (or both)

**Configuration System**: TOML-based configuration
- Bluesky credentials in `[bluesky]` section
- Scan configurations in `[[scan]]` array blocks
- Supports path expansion with `~`
- Configurable via `--config` option

### Scan Configuration Structure
Each `[[scan]]` block supports:
- `name` - Unique identifier
- `handle` - Bluesky user to monitor
- `pattern` - Regex pattern for matching
- `webhook_url` - HTTP endpoint (optional)
- `shell` - Shell command with formatting (optional)

### String Formatting in Shell Commands
Available formatting fields:
- `{text}` - Matched post text
- `{created_at}` - Post timestamp
- `{handle}` - User handle
- `{pattern}` - Regex pattern
- `{uri}` - AT Protocol URI of the post
- `{url}` - Web-accessible URL to the post

**Important**: All values are automatically escaped using `shlex.quote()` for security. Do not manually quote placeholder fields (write `{text}` not `"{text}"`). Shell features in the template (variables, pipes, redirects) work normally.

### Webhook Payload Format
```json
{
  "scan_name": "scan_identifier",
  "matches": [{"handle": "...", "created_at": "...", "text": "...", "pattern": "...", "uri": "...", "url": "..."}],
  "total_matches": 1,
  "scanned_posts": 10
}
```

### Logging Levels
- `--log-level debug` - Detailed output (API calls, post counts)
- `--log-level info` - Normal operation (default)
- `--log-level warning` - Warnings and errors only
- `--log-level error` - Errors only

### Versioning
- Uses semantic versioning via `__version__` variable in `bluewatch.py`
- Version must be updated when making changes before committing
- Current version: 1.2.1

### Error Handling
- Configuration file validation
- Missing dependency detection
- Network/API error handling
- Regex compilation validation
- Webhook and shell command error handling
- User-friendly error messages via Click exceptions

## Development Notes

- Python 3.11+ required
- Dependencies: click, atproto, requests
- No test suite currently exists
- Uses uv for dependency management and script execution
- Single-file design keeps complexity low
- Credentials stored externally in config.toml (not tracked in git)
- Shell commands executed with 30-second timeout
- Webhook requests have 30-second timeout
- Uses Python's standard logging module for output control
- Backward scanning prevents duplicate notifications and missing posts