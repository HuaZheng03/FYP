import os
import json
from datetime import datetime, timedelta, timezone

# Configuration
script_dir = os.path.dirname(os.path.abspath(__file__))
DAILY_PREDICTIONS_FILE = os.path.join(script_dir, 'daily_predictions.json')

# Define UTC+8 timezone
LOCAL_TZ = timezone(timedelta(hours=8))


def _get_current_date_str() -> str:
    """Returns the current date as YYYY-MM-DD string in local timezone."""
    return datetime.now(LOCAL_TZ).strftime('%Y-%m-%d')


def _load_predictions_file() -> dict:
    """
    Loads the daily predictions file.
    If file doesn't exist or is from a previous day, returns a fresh structure for today.
    """
    today = _get_current_date_str()
    
    try:
        if os.path.exists(DAILY_PREDICTIONS_FILE):
            with open(DAILY_PREDICTIONS_FILE, 'r') as f:
                data = json.load(f)
                
            # Check if the file is from today
            if data.get('date') == today:
                return data
            else:
                # It's a new day, start fresh
                print(f"[DAILY_PREDICTIONS] New day detected. Clearing previous day's data.")
                return {'date': today, 'entries': []}
        else:
            return {'date': today, 'entries': []}
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[DAILY_PREDICTIONS] Error reading file, creating new: {e}")
        return {'date': today, 'entries': []}


def _save_predictions_file(data: dict) -> bool:
    """Saves the predictions data to file."""
    try:
        with open(DAILY_PREDICTIONS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[DAILY_PREDICTIONS] Error saving file: {e}")
        return False


def add_prediction(hour_time: str, predicted_value: int) -> bool:
    """
    Adds a new prediction entry for the given hour.
    
    Args:
        hour_time: The hour in "HH:00" format (e.g., "08:00")
        predicted_value: The predicted number of HTTP requests
        
    Returns:
        bool: True if successfully added, False otherwise
    """
    data = _load_predictions_file()
    
    # Check if entry for this hour already exists
    for entry in data['entries']:
        if entry['time'] == hour_time:
            # Update existing prediction if actual hasn't been set
            if entry.get('actual') is None:
                entry['predicted'] = predicted_value
                print(f"[DAILY_PREDICTIONS] Updated prediction for {hour_time}: {predicted_value}")
                return _save_predictions_file(data)
            else:
                print(f"[DAILY_PREDICTIONS] Entry for {hour_time} already complete, not updating prediction")
                return False
    
    # Add new entry
    new_entry = {
        'time': hour_time,
        'predicted': predicted_value,
        'actual': None
    }
    data['entries'].append(new_entry)
    
    # Sort entries by time
    data['entries'].sort(key=lambda x: x['time'])
    
    print(f"[DAILY_PREDICTIONS] Added prediction for {hour_time}: {predicted_value}")
    return _save_predictions_file(data)


def update_actual(hour_time: str, actual_value: int) -> bool:
    """
    Updates the actual value for a previously predicted hour.
    Only updates if the actual value is currently null (not already set).
    
    Args:
        hour_time: The hour in "HH:00" format (e.g., "08:00")
        actual_value: The actual number of HTTP requests collected
        
    Returns:
        bool: True if successfully updated, False if no matching prediction found
              or if actual value already exists
    """
    data = _load_predictions_file()
    
    # Find the entry for this hour
    for entry in data['entries']:
        if entry['time'] == hour_time:
            # Check if actual value already exists (not null)
            if entry.get('actual') is not None:
                return False
            
            entry['actual'] = actual_value
            print(f"[DAILY_PREDICTIONS] Updated actual for {hour_time}: {actual_value}")
            return _save_predictions_file(data)
    
    # No matching prediction found
    print(f"[DAILY_PREDICTIONS] No prediction entry found for {hour_time}, actual value not stored")
    return False


def get_daily_predictions() -> dict:
    """
    Returns the current day's predictions data.
    
    Returns:
        dict: The daily predictions data structure
    """
    return _load_predictions_file()


def clear_old_data() -> bool:
    """
    Clears the predictions file if it's from a previous day.
    This is called automatically by _load_predictions_file(), but can be called explicitly.
    
    Returns:
        bool: True if data was cleared, False if already current day
    """
    today = _get_current_date_str()
    
    try:
        if os.path.exists(DAILY_PREDICTIONS_FILE):
            with open(DAILY_PREDICTIONS_FILE, 'r') as f:
                data = json.load(f)
            
            if data.get('date') != today:
                new_data = {'date': today, 'entries': []}
                _save_predictions_file(new_data)
                print(f"[DAILY_PREDICTIONS] Cleared old data from {data.get('date')}")
                return True
        return False
    except Exception as e:
        print(f"[DAILY_PREDICTIONS] Error clearing old data: {e}")
        return False


# Initialize with empty file if it doesn't exist
if not os.path.exists(DAILY_PREDICTIONS_FILE):
    _save_predictions_file({'date': _get_current_date_str(), 'entries': []})
