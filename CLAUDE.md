# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Tasks

### Running the Application
```bash
# View a user's timeline
uv run ./bluewatch.py timeline example_user --limit 5

# Run all configured scans
uv run ./bluewatch.py scan

# Run specific scan by name
uv run ./bluewatch.py scan crypto_watch

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
- Timeline command: `timeline()` - Fetches and displays user timelines
- Scan command: `scan()` - Runs configured pattern monitoring
- Configuration loading: `load_config()` - Loads TOML config files

**Bluesky Integration**: Uses AT Protocol client
- Authentication via username/password from config
- Timeline fetching via `get_author_feed()`
- Error handling for network and API failures

**Scan System**: Pattern-based timeline monitoring
- Regex pattern matching (case-insensitive)
- Multiple scan configurations via `[[scan]]` TOML blocks
- Webhook notifications with JSON payloads
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
- `limit` - Posts to scan (default: 10)

### String Formatting in Shell Commands
Available formatting fields:
- `{text}` - Matched post text
- `{created_at}` - Post timestamp
- `{handle}` - User handle
- `{pattern}` - Regex pattern

### Webhook Payload Format
```json
{
  "scan_name": "scan_identifier",
  "matches": [{"handle": "...", "created_at": "...", "text": "...", "pattern": "..."}],
  "total_matches": 1,
  "scanned_posts": 10
}
```

### Versioning
- Uses semantic versioning via `__version__` variable in `bluewatch.py`
- Version must be updated when making changes before committing
- Current version: 0.3.0

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