import sqlite3
import os
import pandas as pd
from datetime import datetime, timedelta, timezone

# --- CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(CURRENT_DIR, 'traffic_data.db')

# Path to the original CSV file for initial import
WEB_TRAFFIC_CSV = os.path.join(
    os.path.dirname(CURRENT_DIR), 
    'web_traffic_time_series_forecasting', 
    'web_traffic.csv'
)

LOCAL_TZ = timezone(timedelta(hours=8))


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
    Creates the hourly_traffic table if it does not exist.
    
    Table Schema:
    - timestamp: TEXT (PRIMARY KEY) - Format: 'YYYY-MM-DD HH:MM:SS'
    - traffic_count: REAL - Number of HTTP requests (float to match CSV)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hourly_traffic (
            timestamp TEXT PRIMARY KEY,
            traffic_count REAL NOT NULL
        )
    ''')
    
    # Create index for faster timestamp queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_timestamp ON hourly_traffic(timestamp)
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Database initialized at: {DB_FILE}")


def import_csv_to_database(csv_path: str = None, replace_existing: bool = False) -> int:
    """
    Imports data from web_traffic.csv into the SQLite database.
    
    Args:
        csv_path: Path to the CSV file (default: WEB_TRAFFIC_CSV)
        replace_existing: If True, clears existing data before import
        
    Returns:
        int: Number of records imported
    """
    if csv_path is None:
        csv_path = WEB_TRAFFIC_CSV
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return 0
    
    try:
        # Read CSV file
        df = pd.read_csv(csv_path)
        
        # Validate columns
        if 'Timestamp' not in df.columns or 'TrafficCount' not in df.columns:
            print("❌ CSV must have 'Timestamp' and 'TrafficCount' columns")
            return 0
        
        # Parse timestamps
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Optionally clear existing data
        if replace_existing:
            cursor.execute('DELETE FROM hourly_traffic')
            print("🗑️  Cleared existing data from database")
        
        # Insert records
        imported_count = 0
        skipped_count = 0
        
        for _, row in df.iterrows():
            timestamp_str = row['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            traffic_count = float(row['TrafficCount'])
            
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO hourly_traffic (timestamp, traffic_count)
                    VALUES (?, ?)
                ''', (timestamp_str, traffic_count))
                
                if cursor.rowcount > 0:
                    imported_count += 1
                else:
                    skipped_count += 1
            except sqlite3.IntegrityError:
                skipped_count += 1
        
        conn.commit()
        conn.close()
        
        print(f"✅ Imported {imported_count} records from CSV")
        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} duplicate records")
        
        return imported_count
        
    except Exception as e:
        print(f"❌ Error importing CSV: {e}")
        return 0


def insert_hourly_traffic(timestamp_obj: datetime, count: float) -> bool:
    """
    Inserts or updates a single hourly traffic record.
    Used by run.py to add real-time Prometheus data.
    
    Args:
        timestamp_obj: datetime object for the hour
        count: Number of HTTP requests
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Normalize timestamp to hour boundary
        normalized_timestamp = timestamp_obj.replace(minute=0, second=0, microsecond=0)
        timestamp_str = normalized_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        cursor.execute('''
            INSERT OR REPLACE INTO hourly_traffic (timestamp, traffic_count)
            VALUES (?, ?)
        ''', (timestamp_str, float(count)))
        
        conn.commit()
        conn.close()
        
        print(f"💾 Saved to Database ({timestamp_str}): {int(count):,} requests")
        return True
        
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return False


def fetch_all_traffic_data() -> pd.DataFrame:
    """
    Retrieves all traffic data from the database for model training.
    Returns data in the same format as the original CSV.
    
    Returns:
        pd.DataFrame: DataFrame with 'Timestamp' and 'TrafficCount' columns,
                      or None if error/empty
    """
    try:
        conn = get_db_connection()
        
        query = "SELECT timestamp, traffic_count FROM hourly_traffic ORDER BY timestamp ASC"
        df = pd.read_sql_query(query, conn)
        
        conn.close()
        
        if df.empty:
            print("⚠️  Database is empty")
            return None

        # Convert to match CSV format expected by forecast_web_traffic.py
        df['Timestamp'] = pd.to_datetime(df['timestamp'])
        df['TrafficCount'] = df['traffic_count']
        df = df[['Timestamp', 'TrafficCount']]  # Keep only required columns
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching data from DB: {e}")
        return None


def fetch_recent_traffic_data(hours: int = 168) -> pd.DataFrame:
    """
    Retrieves the most recent N hours of traffic data.
    Useful for prediction input (default 168 hours = 1 week).
    
    Args:
        hours: Number of hours to fetch
        
    Returns:
        pd.DataFrame: Recent traffic data
    """
    try:
        conn = get_db_connection()
        
        query = f"""
            SELECT timestamp, traffic_count 
            FROM hourly_traffic 
            ORDER BY timestamp DESC 
            LIMIT {hours}
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return None
        
        # Convert and sort ascending (oldest first)
        df['Timestamp'] = pd.to_datetime(df['timestamp'])
        df['TrafficCount'] = df['traffic_count']
        df = df[['Timestamp', 'TrafficCount']].sort_values('Timestamp').reset_index(drop=True)
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching recent data: {e}")
        return None


def get_record_count() -> int:
    """Returns the total number of records in the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM hourly_traffic')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


def get_date_range() -> tuple:
    """
    Returns the date range of data in the database.
    
    Returns:
        tuple: (min_timestamp, max_timestamp) or (None, None) if empty
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT MIN(timestamp), MAX(timestamp) FROM hourly_traffic')
        result = cursor.fetchone()
        conn.close()
        
        if result[0] and result[1]:
            return (
                datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S'),
                datetime.strptime(result[1], '%Y-%m-%d %H:%M:%S')
            )
        return (None, None)
    except:
        return (None, None)


def print_database_status():
    """Prints a summary of the database status."""
    print("\n" + "=" * 50)
    print("📊 Traffic Database Status")
    print("=" * 50)
    print(f"Database File: {DB_FILE}")
    print(f"File Exists: {os.path.exists(DB_FILE)}")
    
    count = get_record_count()
    print(f"Total Records: {count:,}")
    
    min_date, max_date = get_date_range()
    if min_date and max_date:
        print(f"Date Range: {min_date} to {max_date}")
        days = (max_date - min_date).days
        print(f"Coverage: {days} days")
    
    print("=" * 50 + "\n")


# # --- Main execution for testing/setup ---
# if __name__ == "__main__":
#     print("=" * 60)
#     print("Traffic Database Manager - Setup & Test")
#     print("=" * 60)
    
#     # 1. Initialize database
#     print("\n[1] Initializing database...")
#     initialize_database()
    
#     # 2. Import CSV data
#     print("\n[2] Importing data from web_traffic.csv...")
#     imported = import_csv_to_database(replace_existing=False)
    
#     # 3. Print status
#     print("\n[3] Database status:")
#     print_database_status()
    
#     # 4. Test fetching data
#     print("[4] Testing data fetch...")
#     df = fetch_all_traffic_data()
#     if df is not None:
#         print(f"    Retrieved {len(df)} records")
#         print(f"    First record: {df.iloc[0]['Timestamp']} - {df.iloc[0]['TrafficCount']}")
#         print(f"    Last record: {df.iloc[-1]['Timestamp']} - {df.iloc[-1]['TrafficCount']}")
    
#     print("\n✅ Setup complete!")