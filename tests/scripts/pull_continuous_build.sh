#!/bin/bash
# Update atoti to the latest version from Artifactory using jfrog-cli

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/../.."
PYPROJECT_FILE="$PROJECT_DIR/pyproject.toml"

# Configuration
if [ -z "$ARTIFACTORY_URL" ]; then
    echo "Error: ARTIFACTORY_URL environment variable not set" >&2
    exit 1
fi

if [ -z "$ARTIFACTORY_REPO" ]; then
    echo "Error: ARTIFACTORY_REPO environment variable not set" >&2
    exit 1
fi

if [ -z "$ARTIFACTORY_PACKAGE" ]; then
    echo "Error: ARTIFACTORY_PACKAGE environment variable not set" >&2
    exit 1
fi

# Check if jfrog CLI is installed
if ! command -v jf &> /dev/null; then
    echo "jfrog-cli not found. Installing..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install jfrog-cli
    else
        curl -fL https://install-cli.jfrog.io | sh
        sudo mv jfrog /usr/local/bin/
    fi
fi

# Check if ARTIFACTORY_API_KEY is set
if [ -z "$ARTIFACTORY_API_KEY" ]; then
    echo "Error: ARTIFACTORY_API_KEY environment variable not set" >&2
    echo "Set it using: export ARTIFACTORY_API_KEY='your-api-key'" >&2
    exit 1
fi

# Check if ARTIFACTORY_USERNAME is set
if [ -z "$ARTIFACTORY_USERNAME" ]; then
    echo "Error: ARTIFACTORY_USERNAME environment variable not set" >&2
    exit 1
fi

# Configure jfrog CLI (if not already configured)
if ! jf config show 2>/dev/null | grep -q "activeviam"; then
    echo "Configuring jfrog CLI..."
    jf config add activeviam --artifactory-url="$ARTIFACTORY_URL" --access-token="$ARTIFACTORY_API_KEY" --interactive=false
fi

echo "Fetching latest version of $ARTIFACTORY_PACKAGE from Artifactory..."

# Search for all version directories under pypi/atoti/
SEARCH_RESULT=$(jf rt s "pypi/atoti/*/" --sort-by=created --sort-order=desc --limit=1 2>/dev/null || true)

if [ -z "$SEARCH_RESULT" ] || [ "$SEARCH_RESULT" = "[]" ]; then
    echo "Error: No versions found for $ARTIFACTORY_PACKAGE" >&2
    exit 1
fi

# Extract version from the path (e.g., "path": "atoti-python-sdk-pypi-continuous/atoti/0.9.11.dev20251210080526+ba3b981/...")
LATEST_VERSION=$(echo "$SEARCH_RESULT" | grep -o '"path"[^"]*"[^"]*atoti/[^/"]*/[^"]*' | sed 's/.*\/atoti\///' | sed 's/\/.*//' | head -1)

if [ -z "$LATEST_VERSION" ]; then
    echo "Error: Could not extract version from search result" >&2
    echo "Search result was: $SEARCH_RESULT" >&2
    exit 1
fi
echo "Latest version found: $LATEST_VERSION"

# Read current dependency line to preserve extras
CURRENT_DEP=$(grep "^    \"$ARTIFACTORY_PACKAGE" "$PYPROJECT_FILE" || true)

if [ -z "$CURRENT_DEP" ]; then
    echo "Error: Package $ARTIFACTORY_PACKAGE not found in $PYPROJECT_FILE" >&2
    exit 1
fi

# Extract extras if present (e.g., atoti[aws,azure,gcp])
if echo "$CURRENT_DEP" | grep -q '\['; then
    EXTRAS=$(echo "$CURRENT_DEP" | sed -n 's/.*\[\([^]]*\)\].*/\1/p')
    NEW_DEP="$ARTIFACTORY_PACKAGE[$EXTRAS]==$LATEST_VERSION"
    echo "Preserving extras: $EXTRAS"
else
    NEW_DEP="$ARTIFACTORY_PACKAGE==$LATEST_VERSION"
fi

echo "Updating $(realpath "$PYPROJECT_FILE")..."
echo "  Old: $CURRENT_DEP"
echo "  New:     \"$NEW_DEP\","

# Update the pyproject.toml file
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' "s|^    \"$ARTIFACTORY_PACKAGE\[.*\]==.*\"|    \"$NEW_DEP\"|" "$PYPROJECT_FILE"
else
    # Linux
    sed -i "s|^    \"$ARTIFACTORY_PACKAGE\[.*\]==.*\"|    \"$NEW_DEP\"|" "$PYPROJECT_FILE"
fi

# Build the extra-index-url from ARTIFACTORY_URL with credentials
# Extract domain from URL (e.g., https://activeviam.jfrog.io/artifactory -> activeviam.jfrog.io)
DOMAIN=$(echo "$ARTIFACTORY_URL" | sed -E 's|https?://||' | sed 's|/artifactory.*||')
# Build URL with credentials embedded (note: domain should not have protocol prefix)
EXTRA_INDEX_URL="https://${ARTIFACTORY_USERNAME}:${ARTIFACTORY_API_KEY}@${DOMAIN}/artifactory/api/pypi/${ARTIFACTORY_REPO}/simple"

# Add or update [tool.uv] section with extra-index-url
if ! grep -q "\[tool\.uv\]" "$PYPROJECT_FILE"; then
    echo "" >> "$PYPROJECT_FILE"
    echo "[tool.uv]" >> "$PYPROJECT_FILE"
    echo "extra-index-url = [\"${EXTRA_INDEX_URL}\"]" >> "$PYPROJECT_FILE"
elif ! grep -q "extra-index-url" "$PYPROJECT_FILE"; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "/\[tool\.uv\]/a\\
extra-index-url = [\"${EXTRA_INDEX_URL}\"]
" "$PYPROJECT_FILE"
    else
        sed -i "/\[tool\.uv\]/a extra-index-url = [\"${EXTRA_INDEX_URL}\"]" "$PYPROJECT_FILE"
    fi
else
    # Update existing extra-index-url
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|extra-index-url = \[.*\]|extra-index-url = [\"${EXTRA_INDEX_URL}\"]|" "$PYPROJECT_FILE"
    else
        sed -i "s|extra-index-url = \[.*\]|extra-index-url = [\"${EXTRA_INDEX_URL}\"]|" "$PYPROJECT_FILE"
    fi
fi

echo "✓ Successfully updated $(realpath "$PYPROJECT_FILE")"

# Update install_dq.sh with the latest version
INSTALL_DQ_SCRIPT="$SCRIPT_DIR/install_dq.sh"
if [ -f "$INSTALL_DQ_SCRIPT" ]; then
    echo "Updating $(realpath "$INSTALL_DQ_SCRIPT")..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' -E "s|\"atoti\[directquery-([^]]+)\]\"(==[^\"]*)?|\"atoti[directquery-\1]==$LATEST_VERSION\"|g" "$INSTALL_DQ_SCRIPT"
    else
        sed -i -E "s|\"atoti\[directquery-([^]]+)\]\"(==[^\"]*)?|\"atoti[directquery-\1]==$LATEST_VERSION\"|g" "$INSTALL_DQ_SCRIPT"
    fi
    echo "✓ Successfully updated $(realpath "$INSTALL_DQ_SCRIPT")"
fi

echo "✓ Done! $ARTIFACTORY_PACKAGE updated to version $LATEST_VERSION"
echo ""
echo "Run 'uv sync' to install the updated version."
