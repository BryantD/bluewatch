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
- `shell_executable` - Path to shell executable (optional, defaults to `/bin/sh`)

### String Formatting in Shell Commands
Available formatting fields:
- `{text}` - Matched post text
- `{created_at}` - Post timestamp
- `{handle}` - User handle
- `{pattern}` - Regex pattern
- `{uri}` - AT Protocol URI of the post
- `{url}` - Web-accessible URL to the post

**Important**: All values are automatically escaped using `shlex.quote()` for security. Do not manually quote placeholder fields (write `{text}` not `"{text}"`). Shell features in the template (variables, pipes, redirects) work normally.

**Shell Selection**: By default, commands execute with `/bin/sh`. To use bash-specific features like `$RANDOM`, set `shell_executable = "/bin/bash"` in the scan configuration.

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
- Current version: 1.3.2

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

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
