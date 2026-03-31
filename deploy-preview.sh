#!/usr/bin/env bash
# Deploy all example article outputs to Netlify for preview.
# Usage: ./deploy-preview.sh [--prod]
set -euo pipefail

PREVIEW_DIR="/tmp/preview"

# Clean and recreate
rm -rf "$PREVIEW_DIR"
mkdir -p "$PREVIEW_DIR"

# Copy each example's output into a subdirectory
for output_dir in examples/*/output; do
    article=$(basename "$(dirname "$output_dir")")
    dest="$PREVIEW_DIR/$article"
    mkdir -p "$dest"
    # Copy html, xml, css, and images; skip logs, cache, and netlify config
    find "$output_dir" -maxdepth 1 -type f \
        \( -name '*.html' -o -name '*.xml' -o -name '*.css' \
           -o -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.svg' \) \
        -exec cp {} "$dest/" \;
done

# Generate a simple index page
{
    echo '<!DOCTYPE html><html><head><meta charset="utf-8"><title>CCR Preview</title></head><body>'
    echo '<h1>CCR Article Previews</h1><ul>'
    for dir in "$PREVIEW_DIR"/*/; do
        article=$(basename "$dir")
        html=$(find "$dir" -maxdepth 1 -name '*.html' | head -1)
        xml=$(find "$dir" -maxdepth 1 -name '*.xml' | head -1)
        echo "<li><strong>$article</strong>"
        [ -n "$html" ] && echo " — <a href=\"$article/$(basename "$html")\">HTML</a>"
        [ -n "$xml" ] && echo " — <a href=\"$article/$(basename "$xml")\">XML</a>"
        echo "</li>"
    done
    echo '</ul></body></html>'
} > "$PREVIEW_DIR/index.html"

echo "Preview assembled in $PREVIEW_DIR"
ls -R "$PREVIEW_DIR" | head -40

# Deploy to Netlify
if [[ "${1:-}" == "--prod" ]]; then
    npx netlify-cli deploy --dir "$PREVIEW_DIR" --prod
else
    npx netlify-cli deploy --dir "$PREVIEW_DIR"
fi
