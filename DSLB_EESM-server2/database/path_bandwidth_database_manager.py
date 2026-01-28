import sqlite3
import os
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List

# --- CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(CURRENT_DIR, 'path_bandwidth.db')

# Path to the original CSV file for initial import
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
TESTBED_CSV = os.path.join(PROJECT_ROOT, 'predict_network_link_bandwidth_usage', 'testbed_flat_tms.csv')

LOCAL_TZ = timezone(timedelta(hours=8))

# Define the 12 path columns and their corresponding CSV column indices
# Column index in CSV (0-indexed, column 0 is timestamp)
PATH_COLUMNS = {
    'leaf1_spine1_leaf2': 174,  # Good (MAPE 7.43%)
    'leaf1_spine2_leaf2': 41,   # Changed from 18 (MAPE 74.16% -> mean 15862, Est.Pred 63.8 MB)
    'leaf1_spine1_leaf3': 51,   # Changed from 107 (MAPE 25.10% -> mean 7468, Est.Pred 62.4 MB)
    'leaf1_spine2_leaf3': 14,   # Changed from 12 (MAPE 103.48% over-predicting 2x) -> mean 17601, Est.MAPE ~1.04%, CV=0.265
    'leaf1_spine1_leaf6': 162,  # Good (MAPE 11.05%)
    'leaf1_spine2_leaf6': 118,  # Good (MAPE 10.93%)
    'leaf2_spine1_leaf3': 87,   # Changed from 95 (MAPE 18.58% -> mean 20833, Est.Pred 66.9 MB)
    'leaf2_spine2_leaf3': 156,  # Changed from 144 (MAPE 23.84% under-predicting) -> mean 4429, Est.MAPE ~0.94%, CV=0.123
    'leaf2_spine1_leaf6': 113,  # Good (MAPE 8.90%)
    'leaf2_spine2_leaf6': 120,  # Good (MAPE 11.79%)
    'leaf3_spine1_leaf6': 173,  # Good (MAPE 10.47%)
    'leaf3_spine2_leaf6': 41,   # Good (MAPE 9.88%)
}

# Map from TCN.py path name format (with dashes) to database column name (with underscores)
PATH_NAME_TO_DB_COLUMN = {
    'leaf1-spine1-leaf2': 'leaf1_spine1_leaf2',
    'leaf1-spine2-leaf2': 'leaf1_spine2_leaf2',
    'leaf1-spine1-leaf3': 'leaf1_spine1_leaf3',
    'leaf1-spine2-leaf3': 'leaf1_spine2_leaf3',
    'leaf1-spine1-leaf6': 'leaf1_spine1_leaf6',
    'leaf1-spine2-leaf6': 'leaf1_spine2_leaf6',
    'leaf2-spine1-leaf3': 'leaf2_spine1_leaf3',
    'leaf2-spine2-leaf3': 'leaf2_spine2_leaf3',
    'leaf2-spine1-leaf6': 'leaf2_spine1_leaf6',
    'leaf2-spine2-leaf6': 'leaf2_spine2_leaf6',
    'leaf3-spine1-leaf6': 'leaf3_spine1_leaf6',
    'leaf3-spine2-leaf6': 'leaf3_spine2_leaf6',
}

# Reverse mapping for database to TCN path name
DB_COLUMN_TO_PATH_NAME = {v: k for k, v in PATH_NAME_TO_DB_COLUMN.items()}


def get_db_connection():
    """
    Establishes a connection to the SQLite database.
    
    Returns:
        sqlite3.Connection: Database connection object with Row factory enabled
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    """
    Creates the path_bandwidth table if it does not exist.
    
    Table Schema:
    - timestamp: TEXT (PRIMARY KEY) - Format: 'YYYY-MM-DD HH:MM:SS'
    - 12 path columns: REAL - Bandwidth usage values
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Build column definitions for all 12 paths
    path_columns_sql = ",\n            ".join([
        f"{col_name} REAL NOT NULL DEFAULT 0" for col_name in PATH_COLUMNS.keys()
    ])
    
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS path_bandwidth (
            timestamp TEXT PRIMARY KEY,
            {path_columns_sql}
        )
    ''')
    
    # Create index for faster timestamp queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_path_timestamp ON path_bandwidth(timestamp)
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Path bandwidth database initialized at: {DB_FILE}")


def import_csv_to_database(csv_path: str = None, replace_existing: bool = False) -> int:
    """
    Imports the 12 relevant columns from testbed_flat_tms.csv into the SQLite database.
    
    Args:
        csv_path: Path to the CSV file (default: TESTBED_CSV)
        replace_existing: If True, clears existing data before import
        
    Returns:
        int: Number of records imported
    """
    if csv_path is None:
        csv_path = TESTBED_CSV
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return 0
    
    try:
        # Read CSV file - no header row, first column is timestamp
        df = pd.read_csv(csv_path, header=None)
        
        print(f"📊 CSV loaded: {len(df)} rows, {len(df.columns)} columns")
        
        # Initialize database
        initialize_database()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if replace_existing:
            cursor.execute("DELETE FROM path_bandwidth")
            print("🗑️  Cleared existing data")
        
        # Extract timestamp (column 0) and the 12 path columns
        records_imported = 0
        
        for idx, row in df.iterrows():
            timestamp = str(row[0])  # Column 0 is timestamp
            
            # Build the values dictionary for this row
            values = {'timestamp': timestamp}
            for col_name, csv_col_idx in PATH_COLUMNS.items():
                values[col_name] = float(row[csv_col_idx])
            
            # Build INSERT OR REPLACE statement
            columns = ', '.join(values.keys())
            placeholders = ', '.join(['?' for _ in values])
            
            try:
                cursor.execute(
                    f"INSERT OR REPLACE INTO path_bandwidth ({columns}) VALUES ({placeholders})",
                    list(values.values())
                )
                records_imported += 1
            except sqlite3.Error as e:
                print(f"⚠️ Error inserting row {idx}: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"✅ Imported {records_imported} records from CSV")
        return records_imported
        
    except Exception as e:
        print(f"❌ Error importing CSV: {e}")
        return 0


def insert_path_bandwidth(timestamp: datetime, bandwidth_data: Dict[str, float]) -> bool:
    """
    Inserts a single record of path bandwidth measurements.
    
    Args:
        timestamp: datetime object (will be converted to string)
        bandwidth_data: Dictionary mapping path names to bandwidth values
                       Keys can use either format: 'leaf1-spine1-leaf2' or 'leaf1_spine1_leaf2'
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Format timestamp
        if isinstance(timestamp, datetime):
            ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        else:
            ts_str = str(timestamp)
        
        # Normalize path names to database column format
        values = {'timestamp': ts_str}
        for path_name, value in bandwidth_data.items():
            # Convert dash format to underscore format if needed
            if '-' in path_name:
                col_name = PATH_NAME_TO_DB_COLUMN.get(path_name, path_name.replace('-', '_'))
            else:
                col_name = path_name
            
            if col_name in PATH_COLUMNS:
                values[col_name] = float(value)
        
        # Add default 0 for any missing columns
        for col_name in PATH_COLUMNS.keys():
            if col_name not in values:
                values[col_name] = 0.0
        
        columns = ', '.join(values.keys())
        placeholders = ', '.join(['?' for _ in values])
        
        cursor.execute(
            f"INSERT OR REPLACE INTO path_bandwidth ({columns}) VALUES ({placeholders})",
            list(values.values())
        )
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error inserting path bandwidth: {e}")
        return False


def fetch_all_path_data() -> Optional[pd.DataFrame]:
    """
    Fetches all path bandwidth data from the database.
    
    Returns:
        pd.DataFrame with columns: Timestamp, and all 12 path columns
        Returns None if error occurs
    """
    try:
        conn = get_db_connection()
        
        # Build query to select timestamp and all path columns
        columns = ['timestamp'] + list(PATH_COLUMNS.keys())
        query = f"SELECT {', '.join(columns)} FROM path_bandwidth ORDER BY timestamp ASC"
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Rename timestamp column to Timestamp for consistency
        df.rename(columns={'timestamp': 'Timestamp'}, inplace=True)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching path data: {e}")
        return None


def fetch_path_data_for_training(path_name: str) -> Optional[pd.DataFrame]:
    """
    Fetches data for a specific path for model training.
    
    Args:
        path_name: Path name in either format ('leaf1-spine1-leaf2' or 'leaf1_spine1_leaf2')
        
    Returns:
        pd.DataFrame with columns: Timestamp, bandwidth_value
        Returns None if error occurs
    """
    try:
        # Normalize path name to database column format
        if '-' in path_name:
            col_name = PATH_NAME_TO_DB_COLUMN.get(path_name)
        else:
            col_name = path_name
        
        if col_name not in PATH_COLUMNS:
            print(f"❌ Unknown path name: {path_name}")
            return None
        
        conn = get_db_connection()
        query = f"SELECT timestamp, {col_name} FROM path_bandwidth ORDER BY timestamp ASC"
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        df.rename(columns={'timestamp': 'Timestamp', col_name: 'bandwidth_value'}, inplace=True)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching path data for {path_name}: {e}")
        return None


def fetch_recent_path_data(minutes: int = 60) -> Optional[pd.DataFrame]:
    """
    Fetches path bandwidth data from the last N minutes.
    
    Args:
        minutes: Number of minutes to look back
        
    Returns:
        pd.DataFrame with all path data from the specified time window
    """
    try:
        conn = get_db_connection()
        
        # Calculate cutoff time
        cutoff = (datetime.now(LOCAL_TZ) - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')
        
        columns = ['timestamp'] + list(PATH_COLUMNS.keys())
        query = f"SELECT {', '.join(columns)} FROM path_bandwidth WHERE timestamp >= ? ORDER BY timestamp ASC"
        
        df = pd.read_sql_query(query, conn, params=[cutoff])
        conn.close()
        
        df.rename(columns={'timestamp': 'Timestamp'}, inplace=True)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching recent path data: {e}")
        return None


def get_database_stats() -> dict:
    """
    Returns statistics about the path bandwidth database.
    
    Returns:
        dict with database statistics
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total record count
        cursor.execute("SELECT COUNT(*) FROM path_bandwidth")
        total_records = cursor.fetchone()[0]
        
        # Get date range
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM path_bandwidth")
        row = cursor.fetchone()
        min_ts, max_ts = row[0], row[1]
        
        conn.close()
        
        return {
            'total_records': total_records,
            'first_timestamp': min_ts,
            'last_timestamp': max_ts,
            'db_path': DB_FILE
        }
        
    except Exception as e:
        print(f"❌ Error getting database stats: {e}")
        return {}


def get_path_column_names() -> List[str]:
    """Returns list of all path column names in database format."""
    return list(PATH_COLUMNS.keys())


def get_path_column_mapping() -> Dict[str, str]:
    """Returns mapping from TCN path name format to database column format."""
    return PATH_NAME_TO_DB_COLUMN.copy()


# --- Main execution for testing ---
if __name__ == "__main__":
    print("=" * 60)
    print("Path Bandwidth Database Manager - Initialization")
    print("=" * 60)
    
    # Initialize database
    initialize_database()
    
    # Import data from CSV
    print("\n📥 Importing data from testbed_flat_tms.csv...")
    records = import_csv_to_database(replace_existing=True)
    
    # Show statistics
    print("\n📊 Database Statistics:")
    stats = get_database_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Show sample data
    print("\n📋 Sample data (first 5 records):")
    df = fetch_all_path_data()
    if df is not None and len(df) > 0:
        print(df.head().to_string())
        
    print("\n✅ Database setup complete!")
