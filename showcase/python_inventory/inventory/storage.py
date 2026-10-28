"""JSON file persistence for inventory data with atomic writes."""

import json
import os
import tempfile
from pathlib import Path


class Storage:
    """Storage for inventory data with atomic JSON writes."""

    def __init__(self, path: Path):
        """Initialize storage, reading existing JSON or initializing empty state.
        
        Args:
            path: Path to the JSON file.
        """
        self._path = path
        self._data: dict = {}
        
        if self._path.exists():
            self._load()
        else:
            self._data = {
                "products": {},
                "orders": [],
                "next_order": 1,
            }

    @property
    def products(self) -> dict:
        """Return the products dict."""
        return self._data.get("products", {})

    @products.setter
    def products(self, value: dict) -> None:
        """Set the products dict."""
        self._data["products"] = value

    @property
    def orders(self) -> list:
        """Return the orders list."""
        return self._data.get("orders", [])

    @property
    def next_order(self) -> int:
        """Return the next order number."""
        return self._data.get("next_order", 1)

    @next_order.setter
    def next_order(self, value: int) -> None:
        """Set the next order number."""
        self._data["next_order"] = value

    def _load(self) -> None:
        """Load data from the JSON file."""
        with open(self._path, "r", encoding="utf-8") as f:
            self._data = json.load(f)

    def _save(self) -> None:
        """Save data to the JSON file atomically."""
        # Write to a temporary file in the same directory
        dir_path = self._path.parent
        dir_path.mkdir(parents=True, exist_ok=True)
        
        fd, temp_path = tempfile.mkstemp(suffix=".json", dir=dir_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            # Atomic rename
            os.replace(temp_path, self._path)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def save(self) -> None:
        """Save data to the JSON file atomically."""
        self._save()
