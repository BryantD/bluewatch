#!/bin/bash

# Pushover notification script for bluewatch
# Usage: pushover-notify.sh "message text" "https://post-url.com" "optional title"

# Configuration - Set these environment variables or edit below
PUSHOVER_TOKEN=""
PUSHOVER_USER=""

# Check for required environment variables
if [[ -z "$PUSHOVER_TOKEN" ]]; then
    echo "Error: PUSHOVER_TOKEN environment variable not set" >&2
    exit 1
fi

if [[ -z "$PUSHOVER_USER" ]]; then
    echo "Error: PUSHOVER_USER environment variable not set" >&2
    exit 1
fi

# Parse command line arguments
MESSAGE="$1"
URL="$2"
TITLE="${3:-Bluewatch Alert}"

# Validate required arguments
if [[ -z "$MESSAGE" ]]; then
    echo "Usage: $0 \"message text\" \"https://post-url.com\" \"optional title\"" >&2
    echo "Error: Message text is required" >&2
    exit 1
fi

# Build curl command with required parameters
CURL_ARGS=(
    -s
    -F "token=$PUSHOVER_TOKEN"
    -F "user=$PUSHOVER_USER"
    -F "message=$MESSAGE"
    -F "title=$TITLE"
)

# Add URL if provided
if [[ -n "$URL" ]]; then
    CURL_ARGS+=(-F "url=$URL")
    CURL_ARGS+=(-F "url_title=View Post")
fi

# Send notification
RESPONSE=$(curl "${CURL_ARGS[@]}" https://api.pushover.net/1/messages.json)

# Check response
if echo "$RESPONSE" | grep -q '"status":1'; then
    echo "Pushover notification sent successfully"
    exit 0
else
    echo "Pushover notification failed:" >&2
    echo "$RESPONSE" >&2
    exit 1
fi
