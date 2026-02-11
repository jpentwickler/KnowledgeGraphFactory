"""Unit tests for Domain Graph Builder components.

Tests CSV validation, constraint creation, and import logic.
"""

import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from pipelines.domain_builder import validate_csv_uniqueness


class TestCSVValidation:
    """Test CSV validation logic."""

    def test_validate_unique_column_success(self):
        """Test validation passes with unique values."""
        # Create a temp CSV with unique values
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name,price\n")
            f.write("P001,Chair,100\n")
            f.write("P002,Table,200\n")
            f.write("P003,Desk,300\n")
            csv_path = f.name

        try:
            result = validate_csv_uniqueness(csv_path, "id")
            assert result["valid"] is True
            assert result["row_count"] == 3
            assert result["duplicates"] == []
        finally:
            os.unlink(csv_path)

    def test_validate_duplicate_values(self):
        """Test validation fails with duplicate values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name,price\n")
            f.write("P001,Chair,100\n")
            f.write("P001,Table,200\n")  # Duplicate ID
            f.write("P003,Desk,300\n")
            csv_path = f.name

        try:
            result = validate_csv_uniqueness(csv_path, "id")
            assert result["valid"] is False
            assert "duplicate" in result["message"].lower()
            assert "P001" in result["duplicates"]
        finally:
            os.unlink(csv_path)

    def test_validate_null_values(self):
        """Test validation fails with null values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name,price\n")
            f.write("P001,Chair,100\n")
            f.write(",Table,200\n")  # Empty ID
            f.write("P003,Desk,300\n")
            csv_path = f.name

        try:
            result = validate_csv_uniqueness(csv_path, "id")
            assert result["valid"] is False
            assert "null" in result["message"].lower() or "empty" in result["message"].lower()
        finally:
            os.unlink(csv_path)

    def test_validate_whitespace_values(self):
        """Test validation fails with whitespace in values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name,price\n")
            f.write("P001,Chair,100\n")
            f.write(" P002 ,Table,200\n")  # Whitespace around ID
            f.write("P003,Desk,300\n")
            csv_path = f.name

        try:
            result = validate_csv_uniqueness(csv_path, "id")
            assert result["valid"] is False
            assert "whitespace" in result["message"].lower()
        finally:
            os.unlink(csv_path)

    def test_validate_missing_column(self):
        """Test validation fails when column doesn't exist."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name,price\n")
            f.write("P001,Chair,100\n")
            csv_path = f.name

        try:
            result = validate_csv_uniqueness(csv_path, "nonexistent_column")
            assert result["valid"] is False
            assert "not found" in result["message"].lower()
        finally:
            os.unlink(csv_path)

    def test_validate_file_not_found(self):
        """Test validation fails when file doesn't exist."""
        result = validate_csv_uniqueness("/nonexistent/path/file.csv", "id")
        assert result["valid"] is False
        assert "not found" in result["message"].lower()
