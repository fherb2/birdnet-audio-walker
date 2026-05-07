find ./source -type f \( -name "*.py" -o -name "*.cu" \) | sort | while read f; do
    echo ""
    echo "# Start of next file: === $f ==="
    cat "$f"
    echo ""
    echo "# End of file: === $f ==="
done > project_source.txt