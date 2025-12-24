#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["click", "atproto", "requests"]
# ///
import click
import tomllib
import re
import requests
import subprocess
import sqlite3
import time
import logging
import warnings
import shlex
from datetime import datetime, timedelta
from pathlib import Path

# Suppress Pydantic warnings from atproto library
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

logger = logging.getLogger(__name__)

__version__ = "1.3.0"

def load_config(path: str):
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise click.FileError(str(config_path), hint="Config file not found")
    with open(config_path, "rb") as f:
        return tomllib.load(f)

def init_database(db_path: str):
    """Initialize SQLite database for scan state tracking."""
    db_path = Path(db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    
    # Check if table exists and what columns it has
    cursor = conn.execute("PRAGMA table_info(scan_state)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if not columns:
        # Table doesn't exist, create with new schema
        conn.execute("""
            CREATE TABLE scan_state (
                scan_name TEXT PRIMARY KEY,
                handle TEXT NOT NULL,
                last_read_timestamp TEXT NOT NULL,
                last_run_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    elif 'last_run_at' not in columns:
        # Table exists but missing last_run_at column
        conn.execute("ALTER TABLE scan_state ADD COLUMN last_run_at TEXT")
    
    conn.commit()
    conn.close()

def get_last_read_timestamp(db_path: str, scan_name: str) -> str | None:
    """Get the last read timestamp for a scan."""
    db_path = Path(db_path).expanduser()
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        "SELECT last_read_timestamp FROM scan_state WHERE scan_name = ?",
        (scan_name,)
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def update_scan_state(db_path: str, scan_name: str, handle: str, timestamp: str):
    """Update the last read timestamp and run time for a scan."""
    db_path = Path(db_path).expanduser()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO scan_state (scan_name, handle, last_read_timestamp, last_run_at, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (scan_name, handle, timestamp))
    conn.commit()
    conn.close()

def update_scan_run_time(db_path: str, scan_name: str):
    """Update only the last run time for a scan."""
    db_path = Path(db_path).expanduser()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        UPDATE scan_state 
        SET last_run_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE scan_name = ?
    """, (scan_name,))
    conn.commit()
    conn.close()

def get_scan_status(db_path: str, scan_name: str = None):
    """Get status information for scans."""
    db_path = Path(db_path).expanduser()
    conn = sqlite3.connect(db_path)
    
    if scan_name:
        cursor = conn.execute("""
            SELECT scan_name, handle, last_read_timestamp, last_run_at, updated_at
            FROM scan_state WHERE scan_name = ?
        """, (scan_name,))
    else:
        cursor = conn.execute("""
            SELECT scan_name, handle, last_read_timestamp, last_run_at, updated_at
            FROM scan_state ORDER BY scan_name
        """)
    
    results = cursor.fetchall()
    conn.close()
    return results

def reset_scan_state(db_path: str, scan_name: str):
    """Remove scan state from database entirely."""
    db_path = Path(db_path).expanduser()
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("DELETE FROM scan_state WHERE scan_name = ?", (scan_name,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

@click.group()
@click.version_option(__version__, prog_name="bluewatch")
def cli():
    """bluewatch: scan Bluesky user timelines."""
    pass

@cli.command()
@click.argument("scan_name", required=False)
@click.option("--config", "-c", default="config.toml", type=click.Path(), help="Path to config file")
@click.option("--log-level", type=click.Choice(['debug', 'info', 'warning', 'error']), default='info', help="Set logging level (default: info)")
@click.option("--lookback-hours", type=int, default=24, help="Hours to look back for posts (default: 24)")
def scan(scan_name, config, log_level, lookback_hours):
    """Run configured scans. If SCAN_NAME is provided, run only that scan."""
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(message)s'
    )
    
    cfg = load_config(config)
    bs_cfg = cfg.get("bluesky", {})
    username = bs_cfg.get("username")
    password = bs_cfg.get("password")
    if not username or not password:
        logger.error("Bluesky credentials missing in config file")
        raise click.UsageError("Bluesky credentials missing in config file")

    # Get database path from config
    storage_cfg = cfg.get("storage", {})
    db_path = storage_cfg.get("database", "bluewatch.db")
    init_database(db_path)

    scans = cfg.get("scan", [])
    if not scans:
        logger.error("No scan configurations found in config file")
        raise click.UsageError("No scan configurations found in config file")

    # Filter to specific scan if requested
    if scan_name:
        scans = [s for s in scans if s.get("name") == scan_name]
        if not scans:
            logger.error(f"Scan '{scan_name}' not found in config file")
            raise click.UsageError(f"Scan '{scan_name}' not found in config file")

    try:
        from atproto import Client
    except ImportError:
        logger.error("The atproto library is required. Install via `uv add atproto`.")
        raise click.ClickException("The atproto library is required. Install via `uv add atproto`.")
    
    client = Client()
    client.login(login=username, password=password)

    for scan_config in scans:
        run_scan(client, scan_config, db_path, lookback_hours)

@cli.command()
@click.argument("scan_name", required=False)
@click.option("--config", "-c", default="config.toml", type=click.Path(), help="Path to config file")
@click.option("--log-level", type=click.Choice(['debug', 'info', 'warning', 'error']), default='info', help="Set logging level (default: info)")
def status(scan_name, config, log_level):
    """Show status of scans. If SCAN_NAME is provided, show only that scan."""
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(message)s'
    )
    
    cfg = load_config(config)
    
    # Get database path from config
    storage_cfg = cfg.get("storage", {})
    db_path = storage_cfg.get("database", "bluewatch.db")
    
    # Initialize database (creates if not exists, migrates if needed)
    init_database(db_path)
    
    # Check if database has any data
    results = get_scan_status(db_path, scan_name)
    
    if not results:
        if scan_name:
            logger.info(f"No status found for scan '{scan_name}'")
        else:
            logger.info("No scan status found. Run a scan first.")
        return
    
    # Display results in a table format
    print("Scan Status:")
    print("-" * 80)
    print(f"{'Name':<20} {'Handle':<20} {'Last Read':<20} {'Last Run':<20}")
    print("-" * 80)
    
    for row in results:
        scan_name, handle, last_read, last_run, updated = row
        # Format timestamps consistently (ISO format, truncated to 19 chars)
        last_read_short = last_read[:19] if last_read else "Never"
        last_run_short = last_run[:19].replace(' ', 'T') if last_run else "Never"
        
        print(f"{scan_name:<20} {handle:<20} {last_read_short:<20} {last_run_short:<20}")

@cli.command()
@click.argument("scan_name")
@click.option("--config", "-c", default="config.toml", type=click.Path(), help="Path to config file")
@click.option("--log-level", type=click.Choice(['debug', 'info', 'warning', 'error']), default='info', help="Set logging level (default: info)")
def reset(scan_name, config, log_level):
    """Reset state for SCAN_NAME (removes from database)."""
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(message)s'
    )
    
    cfg = load_config(config)
    
    # Get database path from config
    storage_cfg = cfg.get("storage", {})
    db_path = storage_cfg.get("database", "bluewatch.db")
    
    # Initialize database (creates if not exists, migrates if needed)
    init_database(db_path)
    
    # Reset the scan state
    success = reset_scan_state(db_path, scan_name)
    
    if success:
        logger.info(f"Reset state for scan '{scan_name}'")
    else:
        logger.info(f"No state found for scan '{scan_name}' - nothing to reset")

@cli.command()
@click.argument("scan_name")
@click.argument("post_url")
@click.option("--config", "-c", default="config.toml", type=click.Path(), help="Path to config file")
@click.option("--log-level", type=click.Choice(['debug', 'info', 'warning', 'error']), default='info', help="Set logging level (default: info)")
@click.option("--execute", is_flag=True, help="Execute webhook/shell commands if pattern matches")
def test(scan_name, post_url, config, log_level, execute):
    """Test pattern matching against a specific post URL."""
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(message)s'
    )

    cfg = load_config(config)
    bs_cfg = cfg.get("bluesky", {})
    username = bs_cfg.get("username")
    password = bs_cfg.get("password")

    if not username or not password:
        logger.error("Bluesky credentials missing in config file")
        raise click.UsageError("Bluesky credentials missing in config file")

    # Find the scan configuration
    scans = cfg.get("scan", [])
    scan_config = next((s for s in scans if s.get("name") == scan_name), None)

    if not scan_config:
        logger.error(f"Scan '{scan_name}' not found in config file")
        raise click.UsageError(f"Scan '{scan_name}' not found in config file")

    pattern = scan_config.get("pattern")
    webhook_url = scan_config.get("webhook_url")
    shell_cmd = scan_config.get("shell")
    shell_executable = scan_config.get("shell_executable")

    if not pattern:
        logger.error(f"No pattern defined for scan '{scan_name}'")
        raise click.UsageError(f"No pattern defined for scan '{scan_name}'")

    # Parse post URL to extract handle and post ID
    # Format: https://bsky.app/profile/HANDLE/post/POST_ID
    import urllib.parse
    parsed = urllib.parse.urlparse(post_url)
    path_parts = parsed.path.strip('/').split('/')

    if len(path_parts) < 4 or path_parts[0] != 'profile' or path_parts[2] != 'post':
        logger.error("Invalid post URL format. Expected: https://bsky.app/profile/HANDLE/post/POST_ID")
        raise click.UsageError("Invalid post URL format")

    handle = path_parts[1]
    post_id = path_parts[3]

    logger.info(f"Testing pattern '{pattern}' against post {post_id} from {handle}")

    try:
        from atproto import Client
    except ImportError:
        logger.error("The atproto library is required. Install via `uv add atproto`.")
        raise click.ClickException("The atproto library is required")

    client = Client()
    client.login(login=username, password=password)

    # Fetch the specific post
    try:
        # Get the user's DID first
        profile = client.get_profile(actor=handle)
        did = profile.did

        # Construct AT URI: at://DID/app.bsky.feed.post/POST_ID
        post_uri = f"at://{did}/app.bsky.feed.post/{post_id}"

        # Fetch the post
        from atproto import models
        post_response = client.get_posts(uris=[post_uri])

        if not post_response.posts:
            logger.error(f"Post not found: {post_url}")
            return

        post = post_response.posts[0]
        text = getattr(post.record, "text", "")
        created = getattr(post.record, "created_at", "")

        logger.info(f"\nPost text ({created}):")
        logger.info(f"  {text}")
        logger.info(f"\nPattern: {pattern}")

        # Test the pattern
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        match = regex.search(text)

        if match:
            logger.info(f"\n✓ MATCH FOUND!")
            logger.info(f"  Matched: '{match.group()}'")
            logger.info(f"  Position: {match.start()}-{match.end()}")

            # Execute notifications if --execute flag is set
            if execute:
                # Construct match data
                post_uri = f"at://{did}/app.bsky.feed.post/{post_id}"
                web_url = f"https://bsky.app/profile/{handle}/post/{post_id}"

                match_data = {
                    "handle": handle,
                    "created_at": created,
                    "text": text,
                    "pattern": pattern,
                    "uri": post_uri,
                    "url": web_url
                }

                # Call webhook if configured
                if webhook_url:
                    try:
                        payload = {
                            "scan_name": scan_name,
                            "matches": [match_data],
                            "total_matches": 1,
                            "scanned_posts": 1
                        }
                        response = requests.post(webhook_url, json=payload, timeout=30)
                        response.raise_for_status()
                        logger.info(f"\n✓ Webhook called successfully: {response.status_code}")
                    except requests.RequestException as e:
                        logger.error(f"\n✗ Error calling webhook: {e}")

                # Execute shell command if configured
                if shell_cmd:
                    try:
                        # Escape all values for safe shell substitution
                        escaped_data = {k: shlex.quote(str(v)) for k, v in match_data.items()}
                        formatted_cmd = shell_cmd.format(**escaped_data)
                        logger.info(f"\nExecuting: {formatted_cmd}")
                        run_kwargs = {
                            "shell": True,
                            "capture_output": True,
                            "text": True,
                            "timeout": 30
                        }
                        if shell_executable:
                            run_kwargs["executable"] = shell_executable
                        result = subprocess.run(formatted_cmd, **run_kwargs)
                        if result.returncode == 0:
                            logger.info(f"✓ Shell command executed successfully")
                            if result.stdout.strip():
                                logger.info(f"Output: {result.stdout.strip()}")
                        else:
                            logger.error(f"✗ Shell command failed: {result.stderr}")
                    except Exception as e:
                        logger.error(f"✗ Error executing shell command: {e}")

                if not webhook_url and not shell_cmd:
                    logger.info(f"\nNo webhook or shell command configured for this scan")
        else:
            logger.info(f"\n✗ NO MATCH")
            logger.info(f"  The pattern '{pattern}' does not match the post text")

    except Exception as e:
        logger.error(f"Error fetching post: {e}")
        raise click.ClickException(str(e))

def fetch_posts_backwards(client, handle, last_read_timestamp, max_age_hours=24):
    """Fetch posts backwards in time until we hit last_read_timestamp or max_age_hours."""
    cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat() + "Z"
    all_posts = []
    cursor = None
    api_calls = 0
    
    while True:
        try:
            # Fetch 100 posts at a time
            if cursor:
                resp = client.get_author_feed(actor=handle, limit=100, cursor=cursor)
            else:
                resp = client.get_author_feed(actor=handle, limit=100)
            
            api_calls += 1
            items = resp.feed
            
            if not items:
                break
                
            # Check each post in this batch
            should_stop = False
            for item in items:
                rec = item.post.record
                created = getattr(rec, "created_at", "")
                
                # Stop if we've reached our last read timestamp
                if last_read_timestamp and created <= last_read_timestamp:
                    should_stop = True
                    break
                    
                # Stop if we've gone back too far
                if created <= cutoff_time:
                    should_stop = True
                    break
                    
                all_posts.append(item)
            
            if should_stop:
                break
                
            # Get cursor for next batch (pagination)
            cursor = getattr(resp, 'cursor', None)
            if not cursor:
                break
                
            # Rate limiting: pause between API calls
            if api_calls > 1:
                logger.debug(f"Pausing 10 seconds between API calls...")
                time.sleep(10)
                
        except Exception as e:
            logger.error(f"Error fetching posts: {e}")
            break
    
    # Sort posts chronologically (oldest first) for processing
    all_posts.sort(key=lambda x: getattr(x.post.record, "created_at", ""))
    
    logger.debug(f"Fetched {len(all_posts)} posts across {api_calls} API calls")
    return all_posts

def run_scan(client, scan_config, db_path, max_age_hours=24):
    """Run a single scan configuration."""
    name = scan_config.get("name", "unnamed")
    handle = scan_config.get("handle")
    pattern = scan_config.get("pattern")
    webhook_url = scan_config.get("webhook_url")
    shell_cmd = scan_config.get("shell")
    shell_executable = scan_config.get("shell_executable")

    # Validate required fields
    if not handle or not pattern:
        logger.warning(f"Skipping scan '{name}': missing handle or pattern")
        return
    
    if not webhook_url and not shell_cmd:
        logger.warning(f"Skipping scan '{name}': must have webhook_url or shell")
        return

    logger.info(f"Running scan: {name}")

    # Get last read timestamp for this scan
    last_read = get_last_read_timestamp(db_path, name)

    # Fetch posts backwards until we hit last_read or max_age_hours ago
    items = fetch_posts_backwards(client, handle, last_read, max_age_hours)

    if not items:
        logger.info(f"No new posts to scan for {name}")
        # Still update last_run_at even if no new posts
        update_scan_run_time(db_path, name)
        return

    # Compile regex pattern
    try:
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
    except re.error as e:
        logger.error(f"Invalid regex pattern for {name}: {e}")
        return

    # Scan posts for matches
    matches_found = []
    latest_timestamp = None
    
    for item in items:
        rec = item.post.record
        text = getattr(rec, "text", "")
        created = getattr(rec, "created_at", "")

        logger.debug(f"Scanning post [{created}]: {text[:100]}...")

        # Track the latest timestamp
        if not latest_timestamp or created > latest_timestamp:
            latest_timestamp = created

        if regex.search(text):
            # Get post URI and convert to web URL
            post_uri = item.post.uri
            # Convert AT URI to web URL: at://did:plc:xyz/app.bsky.feed.post/abc -> https://bsky.app/profile/handle/post/abc
            post_id = post_uri.split('/')[-1] if '/' in post_uri else ''
            web_url = f"https://bsky.app/profile/{handle}/post/{post_id}"
            
            match_data = {
                "handle": handle,
                "created_at": created,
                "text": text,
                "pattern": pattern,
                "uri": post_uri,
                "url": web_url
            }
            matches_found.append(match_data)
            logger.info(f"Match found in {name}: {created}  {text}")

    # Update scan state with latest timestamp
    if latest_timestamp:
        update_scan_state(db_path, name, handle, latest_timestamp)
    else:
        # Even if no posts, still update run time
        update_scan_run_time(db_path, name)

    # Process matches
    if matches_found:
        # Call webhook if configured
        if webhook_url:
            try:
                payload = {
                    "scan_name": name,
                    "matches": matches_found,
                    "total_matches": len(matches_found),
                    "scanned_posts": len(items)
                }
                response = requests.post(webhook_url, json=payload, timeout=30)
                response.raise_for_status()
                logger.info(f"Webhook called successfully for {name}: {response.status_code}")
            except requests.RequestException as e:
                logger.error(f"Error calling webhook for {name}: {e}")

        # Execute shell command if configured
        if shell_cmd:
            for match in matches_found:
                try:
                    # Escape all values for safe shell substitution
                    escaped_data = {k: shlex.quote(str(v)) for k, v in match.items()}
                    formatted_cmd = shell_cmd.format(**escaped_data)
                    run_kwargs = {
                        "shell": True,
                        "capture_output": True,
                        "text": True,
                        "timeout": 30
                    }
                    if shell_executable:
                        run_kwargs["executable"] = shell_executable
                    result = subprocess.run(formatted_cmd, **run_kwargs)
                    if result.returncode == 0:
                        logger.info(f"Shell command executed successfully for {name}")
                        if result.stdout.strip():
                            logger.info(f"Output: {result.stdout.strip()}")
                    else:
                        logger.error(f"Shell command failed for {name}: {result.stderr}")
                except Exception as e:
                    logger.error(f"Error executing shell command for {name}: {e}")
    else:
        logger.info(f"No matches found for {name}")

if __name__ == "__main__":
    cli()