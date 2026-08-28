"""
Key-based reconciliation engine supporting multiple reconciliation types.
Never matches by row position; always uses configurable keys.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd
import re

log = logging.getLogger("siar.reconciliation")

# Status constants
STATUS_MATCHED = "MATCHED"
STATUS_MISMATCH = "MISMATCH"
STATUS_MISSING_REFERENCE = "MISSING_IN_REFERENCE"
STATUS_MISSING_CSV = "MISSING_IN_CSV"
STATUS_DUPLICATE_KEY = "DUPLICATE_KEY"


class ReconciliationEngine:
    """Key-based reconciliation for inventory management."""

    KEY_CANDIDATES = [
        "sku", "SKU",
        "variant sku", "Variant SKU", "Variant_SKU",
        "handle", "Handle",
        "barcode", "Barcode",
        "product id", "Product ID", "Product_ID",
    ]

    def __init__(self):
        self.reconciliation_key = None

    @staticmethod
    def normalize_value(value: Any) -> str:
        """Normalize values for comparison."""
        if pd.isna(value) or value is None:
            return ""
        return re.sub(r"\s+", " ", str(value).strip()).lower()

    def choose_key(self, ref_df: pd.DataFrame, csv_df: pd.DataFrame) -> Optional[str]:
        """
        Choose the best reconciliation key.
        Returns None if no reliable key found.
        """
        for key_candidate in self.KEY_CANDIDATES:
            # Try exact match first
            for ref_col in ref_df.columns:
                if ref_col.lower() == key_candidate.lower():
                    for csv_col in csv_df.columns:
                        if csv_col.lower() == key_candidate.lower():
                            # Check if this key has actual values
                            ref_values = ref_df[ref_col].astype(str).str.strip().ne("").sum()
                            csv_values = csv_df[csv_col].astype(str).str.strip().ne("").sum()

                            if ref_values > 0 and csv_values > 0:
                                log.info(f"Selected reconciliation key: {ref_col} ({ref_values} ref values, {csv_values} csv values)")
                                self.reconciliation_key = (ref_col, csv_col)
                                return ref_col

        return None

    def reconcile_generic(
        self,
        ref_df: pd.DataFrame,
        csv_df: pd.DataFrame,
        ref_key_col: str,
        csv_key_col: str,
    ) -> Dict[str, Any]:
        """
        Generic key-based reconciliation.
        Handles mismatches for any field.
        """

        ref = ref_df.copy()
        csv = csv_df.copy()

        # Normalize keys
        ref["_key_normalized"] = ref[ref_key_col].map(self.normalize_value)
        csv["_key_normalized"] = csv[csv_key_col].map(self.normalize_value)

        # Remove empty keys
        ref = ref[ref["_key_normalized"] != ""].reset_index(drop=True)
        csv = csv[csv["_key_normalized"] != ""].reset_index(drop=True)

        # Find duplicates
        ref_dupes = ref[ref["_key_normalized"].duplicated(keep=False)]
        csv_dupes = csv[csv["_key_normalized"].duplicated(keep=False)]

        if not ref_dupes.empty or not csv_dupes.empty:
            log.warning(f"Duplicate keys found: {len(ref_dupes)} in reference, {len(csv_dupes)} in CSV")

        # Create indices for fast lookup
        ref_idx = ref.set_index("_key_normalized")
        csv_idx = csv.set_index("_key_normalized")

        # Get all unique keys
        all_keys = sorted(set(ref_idx.index) | set(csv_idx.index))

        rows = []
        for key in all_keys:
            in_ref = key in ref_idx.index
            in_csv = key in csv_idx.index

            # Determine status
            if not in_ref:
                status = STATUS_MISSING_REFERENCE
                mismatch_details = ""
            elif not in_csv:
                status = STATUS_MISSING_CSV
                mismatch_details = ""
            else:
                # Found in both; check for mismatches
                ref_row = ref_idx.loc[key]
                csv_row = csv_idx.loc[key]

                # Handle MultiIndex (duplicate keys)
                if isinstance(ref_row, pd.DataFrame):
                    ref_row = ref_row.iloc[0]
                if isinstance(csv_row, pd.DataFrame):
                    csv_row = csv_row.iloc[0]

                # Find mismatches in common columns
                common_cols = [c for c in ref.columns if c in csv.columns and not c.startswith("_")]
                mismatches = []

                for col in common_cols:
                    ref_val = self.normalize_value(ref_row.get(col, ""))
                    csv_val = self.normalize_value(csv_row.get(col, ""))

                    # Both have values but they differ
                    if ref_val and csv_val and ref_val != csv_val:
                        mismatches.append(col)

                status = STATUS_MISMATCH if mismatches else STATUS_MATCHED
                mismatch_details = ", ".join(mismatches)

            rows.append({
                "key": key,
                "status": status,
                "mismatches": mismatch_details,
            })

        result_df = pd.DataFrame(rows)

        # Calculate statistics
        return {
            "key_field": ref_key_col,
            "total_records": len(result_df),
            "matched": int((result_df["status"] == STATUS_MATCHED).sum()),
            "mismatch": int((result_df["status"] == STATUS_MISMATCH).sum()),
            "missing_in_reference": int((result_df["status"] == STATUS_MISSING_REFERENCE).sum()),
            "missing_in_csv": int((result_df["status"] == STATUS_MISSING_CSV).sum()),
            "details": result_df,
        }

    def reconcile(
        self,
        reference_file: Path,
        csv_file: Path,
        reconciliation_type: str = "generic",
    ) -> Dict[str, Any]:
        """
        Perform reconciliation between reference and current CSV.

        Args:
            reference_file: Excel or CSV file (source of truth)
            csv_file: Excel or CSV file (current data)
            reconciliation_type: Type of reconciliation (generic, fashion, jewelry)

        Returns:
            Reconciliation result with statistics and details
        """

        try:
            # Load files
            if str(reference_file).lower().endswith((".xlsx", ".xlsm")):
                ref_df = pd.read_excel(reference_file, dtype=str)
            else:
                ref_df = pd.read_csv(reference_file, dtype=str)

            if str(csv_file).lower().endswith((".xlsx", ".xlsm")):
                csv_df = pd.read_excel(csv_file, dtype=str)
            else:
                csv_df = pd.read_csv(csv_file, dtype=str)

            log.info(f"Loaded reference: {len(ref_df)} rows, {len(ref_df.columns)} cols")
            log.info(f"Loaded CSV: {len(csv_df)} rows, {len(csv_df.columns)} cols")

        except Exception as e:
            log.error(f"Failed to load files: {e}")
            raise

        # Choose reconciliation key
        ref_key = self.choose_key(ref_df, csv_df)
        if not ref_key:
            raise ValueError(
                "No reliable reconciliation key found. "
                "Ensure both files have one of these columns: SKU, Handle, Variant SKU, Barcode, or Product ID"
            )

        # Get corresponding CSV column
        csv_key = None
        for csv_col in csv_df.columns:
            if csv_col.lower() == ref_key.lower():
                csv_key = csv_col
                break

        if not csv_key:
            raise ValueError(f"Key '{ref_key}' not found in CSV file")

        # Perform reconciliation
        if reconciliation_type == "generic":
            result = self.reconcile_generic(ref_df, csv_df, ref_key, csv_key)
        else:
            # Default to generic for unsupported types
            result = self.reconcile_generic(ref_df, csv_df, ref_key, csv_key)

        return result


def reconcile(reference_file: Path, csv_file: Path) -> Dict[str, Any]:
    """Functional wrapper for backward compatibility."""
    engine = ReconciliationEngine()
    return engine.reconcile(reference_file, csv_file)
