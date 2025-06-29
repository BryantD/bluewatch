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
from datetime import datetime
from pathlib import Path

__version__ = "0.6.0"

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
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO scan_state (scan_name, handle, last_read_timestamp, last_run_at, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (scan_name, handle, timestamp))
    conn.commit()
    conn.close()

def update_scan_run_time(db_path: str, scan_name: str):
    """Update only the last run time for a scan."""
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

@click.group()
@click.version_option(__version__, prog_name="bluewatch")
def cli():
    """bluewatch: scan Bluesky user timelines."""
    pass

@cli.command()
@click.argument("scan_name", required=False)
@click.option("--config", "-c", default="config.toml", type=click.Path(), help="Path to config file")
def scan(scan_name, config):
    """Run configured scans. If SCAN_NAME is provided, run only that scan."""
    cfg = load_config(config)
    bs_cfg = cfg.get("bluesky", {})
    username = bs_cfg.get("username")
    password = bs_cfg.get("password")
    if not username or not password:
        raise click.UsageError("Bluesky credentials missing in config file")

    # Get database path from config
    storage_cfg = cfg.get("storage", {})
    db_path = storage_cfg.get("database", "bluewatch.db")
    init_database(db_path)

    scans = cfg.get("scan", [])
    if not scans:
        raise click.UsageError("No scan configurations found in config file")

    # Filter to specific scan if requested
    if scan_name:
        scans = [s for s in scans if s.get("name") == scan_name]
        if not scans:
            raise click.UsageError(f"Scan '{scan_name}' not found in config file")

    try:
        from atproto import Client
    except ImportError:
        raise click.ClickException("The atproto library is required. Install via `uv add atproto`.")
    
    client = Client()
    client.login(login=username, password=password)

    for scan_config in scans:
        run_scan(client, scan_config, db_path)

@cli.command()
@click.argument("scan_name", required=False)
@click.option("--config", "-c", default="config.toml", type=click.Path(), help="Path to config file")
def status(scan_name, config):
    """Show status of scans. If SCAN_NAME is provided, show only that scan."""
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
            click.echo(f"No status found for scan '{scan_name}'")
        else:
            click.echo("No scan status found. Run a scan first.")
        return
    
    # Display results in a table format
    click.echo("Scan Status:")
    click.echo("-" * 80)
    click.echo(f"{'Name':<20} {'Handle':<20} {'Last Read':<20} {'Last Run':<20}")
    click.echo("-" * 80)
    
    for row in results:
        scan_name, handle, last_read, last_run, updated = row
        # Format timestamps consistently (ISO format, truncated to 19 chars)
        last_read_short = last_read[:19] if last_read else "Never"
        last_run_short = last_run[:19].replace(' ', 'T') if last_run else "Never"
        
        click.echo(f"{scan_name:<20} {handle:<20} {last_read_short:<20} {last_run_short:<20}")

def run_scan(client, scan_config, db_path):
    """Run a single scan configuration."""
    name = scan_config.get("name", "unnamed")
    handle = scan_config.get("handle")
    pattern = scan_config.get("pattern")
    webhook_url = scan_config.get("webhook_url")
    shell_cmd = scan_config.get("shell")
    limit = scan_config.get("limit", 10)

    # Validate required fields
    if not handle or not pattern:
        click.echo(f"Skipping scan '{name}': missing handle or pattern")
        return
    
    if not webhook_url and not shell_cmd:
        click.echo(f"Skipping scan '{name}': must have webhook_url or shell")
        return

    click.echo(f"Running scan: {name}")

    # Get last read timestamp for this scan
    last_read = get_last_read_timestamp(db_path, name)

    try:
        resp = client.get_author_feed(actor=handle, limit=limit)
        items = resp.feed
    except Exception as e:
        click.echo(f"Error fetching timeline for {name}: {e}")
        return

    # Filter posts to only those newer than last read timestamp
    if last_read:
        filtered_items = []
        for item in items:
            rec = item.post.record
            created = getattr(rec, "created_at", "")
            if created > last_read:
                filtered_items.append(item)
        items = filtered_items
        click.echo(f"Filtered to {len(items)} new posts since {last_read}")

    if not items:
        click.echo(f"No new posts to scan for {name}")
        # Still update last_run_at even if no new posts
        update_scan_run_time(db_path, name)
        return

    # Compile regex pattern
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        click.echo(f"Invalid regex pattern for {name}: {e}")
        return

    # Scan posts for matches
    matches_found = []
    latest_timestamp = None
    
    for item in items:
        rec = item.post.record
        text = getattr(rec, "text", "")
        created = getattr(rec, "created_at", "")
        
        # Track the latest timestamp
        if not latest_timestamp or created > latest_timestamp:
            latest_timestamp = created
        
        if regex.search(text):
            match_data = {
                "handle": handle,
                "created_at": created,
                "text": text,
                "pattern": pattern
            }
            matches_found.append(match_data)
            click.echo(f"Match found in {name}: {created}  {text}")

    # Update scan state with latest timestamp
    if latest_timestamp:
        update_scan_state(db_path, name, handle, latest_timestamp)

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
                click.echo(f"Webhook called successfully for {name}: {response.status_code}")
            except requests.RequestException as e:
                click.echo(f"Error calling webhook for {name}: {e}")

        # Execute shell command if configured
        if shell_cmd:
            for match in matches_found:
                try:
                    formatted_cmd = shell_cmd.format(**match)
                    result = subprocess.run(formatted_cmd, shell=True, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        click.echo(f"Shell command executed successfully for {name}")
                    else:
                        click.echo(f"Shell command failed for {name}: {result.stderr}")
                except Exception as e:
                    click.echo(f"Error executing shell command for {name}: {e}")
    else:
        click.echo(f"No matches found for {name}")

if __name__ == "__main__":
    cli()