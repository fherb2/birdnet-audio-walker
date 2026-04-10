find ./source -type f \( -name "*.py" -o -name "*.cu" \) | sort | while read f; do
    echo "# === $f ==="
    cat "$f"
    echo ""
done > project_source.txt