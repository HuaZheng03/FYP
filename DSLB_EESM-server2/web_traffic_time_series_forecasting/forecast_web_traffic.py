import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, mean_absolute_percentage_error
from tensorflow.keras.layers import Input, Dropout, Bidirectional
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping, ReduceLROnPlateau
from tensorflow.keras.optimizers import Adam
import time
from datetime import datetime, timedelta, timezone
import traceback
import joblib
import json
import sys

# Import alert functions
try:
    from alerts import (
        alert_forecast_failed,
        alert_model_retraining_started,
        alert_model_retraining_complete
    )
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False
    print("⚠️ Alerts module not available, alerts will be disabled")

# --- 1. CONFIGURATION ---
script_dir = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(script_dir, 'web_traffic.csv')  # Fallback CSV
MODEL_PATH = os.path.join(script_dir, 'model.keras')
BEST_MODEL_CHECKPOINT_PATH = os.path.join(script_dir, 'best_model.keras')
SCALER_X_PATH = os.path.join(script_dir, 'scaler_x.joblib')
SCALER_Y_PATH = os.path.join(script_dir, 'scaler_y.joblib')
MODEL_STATUS_FILE = os.path.join(script_dir, 'model_validity.json')

# Database configuration - primary data source
USE_DATABASE = True  # Set to False to use CSV instead
sys.path.insert(0, os.path.dirname(script_dir))  # Add parent dir to path
try:
    from database.traffic_database_manager import fetch_all_traffic_data as fetch_from_db
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("⚠️ Database module not available, falling back to CSV")

LOOK_BACK_HOURS = 168  # 7 days of hourly data
train_percentage = 0.70  # Increased training data for better learning
val_percentage = 0.15

# DEFINE UTC+8 TIMEZONE 
LOCAL_TZ = timezone(timedelta(hours=8))

# --- 2. DATA HANDLING ---

def load_and_preprocess_full_data():
    """
    Loads and preprocesses the entire dataset from database (primary) or CSV (fallback).
    Returns the dataframe with hourly resampled data.
    """
    data = None
    
    # Try database first if enabled
    if USE_DATABASE and DATABASE_AVAILABLE:
        try:
            print("[DATA] Loading data from SQLite database...")
            data = fetch_from_db()
            if data is not None and not data.empty:
                data = data.set_index('Timestamp').resample('h').sum()
                print(f"[DATA] Loaded {len(data)} hourly records from database")
                return data
            else:
                print("[DATA] Database returned empty data, trying CSV fallback...")
        except Exception as e:
            print(f"[DATA] Database error: {e}, trying CSV fallback...")
    
    # Fallback to CSV
    try:
        print(f"[DATA] Loading data from CSV: {DATA_FILE}")
        data = pd.read_csv(DATA_FILE)
        data['Timestamp'] = pd.to_datetime(data['Timestamp'])
        data = data.set_index('Timestamp').resample('h').sum()
        print(f"[DATA] Loaded {len(data)} hourly records from CSV")
        return data
    except FileNotFoundError:
        print(f"Error: The data file '{DATA_FILE}' was not found.")
        return None

def prepare_data(seq, num):
  x=[]
  y=[]
  for i in range(0,(len(seq)-num),1):
    input_ = seq[i:i+num]
    output  = seq[i+num]
    x.append(input_)
    y.append(output)
  return np.array(x), np.array(y)

# --- 3. MODEL VALIDITY & MANAGEMENT ---

def get_current_week_range(current_time):
    """
    Calculates the start (Monday 00:00) and end (Sunday 23:59:59) 
    of the week for the given timestamp.
    """
    # Find start of the week (Monday)
    start_of_week = current_time - timedelta(days=current_time.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Find end of the week (Sunday)
    end_of_week = start_of_week + timedelta(days=6)
    end_of_week = end_of_week.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return start_of_week, end_of_week

def is_model_valid_for_current_week(current_time):
    """
    Checks the JSON file to see if the current model is valid for the current week.
    Returns True if valid, False if invalid/expired/missing.
    """
    if not os.path.exists(MODEL_STATUS_FILE):
        return False
        
    try:
        with open(MODEL_STATUS_FILE, 'r') as f:
            status = json.load(f)
            
        valid_start_str = status.get('valid_start')
        valid_end_str = status.get('valid_end')
        
        if not valid_start_str or not valid_end_str:
            return False
            
        valid_start = datetime.fromisoformat(valid_start_str)
        valid_end = datetime.fromisoformat(valid_end_str)
        
        # Ensure timezone awareness for comparison
        if valid_start.tzinfo is None: valid_start = valid_start.replace(tzinfo=LOCAL_TZ)
        if valid_end.tzinfo is None: valid_end = valid_end.replace(tzinfo=LOCAL_TZ)
        
        # Check if current time falls within the validity window
        if valid_start <= current_time <= valid_end:
            return True
        else:
            print(f"[Model Status] Current time {current_time} is outside valid range ({valid_start} - {valid_end}).")
            return False
            
    except Exception as e:
        print(f"Error reading model status file: {e}")
        return False

def update_model_validity(start_date, end_date, r2_val=None, accuracy_pct=None, smape_val=None):
    """
    Updates the JSON file with the new validity period and all accuracy metrics.
    Matches the structure in model_validity.json.
    """
    # Format metrics as percentage strings if available
    r2_str = f"{r2_val*100:.2f}%" if r2_val is not None else "N/A"
    accuracy_str = f"{accuracy_pct:.2f}%" if accuracy_pct is not None else "N/A"
    smape_str = f"{smape_val:.2f}%" if smape_val is not None else "N/A"

    status_data = {
        "valid_start": start_date.isoformat(),
        "valid_end": end_date.isoformat(),
        "trained_at": datetime.now(LOCAL_TZ).isoformat(),
        "r2_score": r2_str,
        "accuracy_percentage": accuracy_str,
        "smape": smape_str
    }
    try:
        with open(MODEL_STATUS_FILE, 'w') as f:
            json.dump(status_data, f, indent=4)
        print(f"Updated model validity: {start_date} to {end_date}")
        print(f"  R2 Score: {r2_str}, Accuracy: {accuracy_str}, SMAPE: {smape_str}")
    except Exception as e:
        print(f"Error saving model status file: {e}")

# --- 4. MODEL ARCHITECTURE & TRAINING ---

def build_model(input_features=1):
    """
    Builds an optimized LSTM model with:
    - Bidirectional LSTM layers for capturing patterns in both directions
    - Dropout for regularization to prevent overfitting
    - Multiple LSTM layers for better feature extraction
    - Linear activation in output layer for regression
    - Huber loss for robustness to outliers
    - Optimized for training time between 5-30 minutes
    
    Args:
        input_features: Number of input features (1 for traffic only, 3 with time features)
    """
    model = Sequential()
    model.add(Input(shape=(LOOK_BACK_HOURS, input_features)))
    
    # First Bidirectional LSTM layer - larger units for better pattern recognition
    model.add(Bidirectional(LSTM(128, return_sequences=True)))
    model.add(Dropout(0.3))
    
    # Second Bidirectional LSTM layer
    model.add(Bidirectional(LSTM(64, return_sequences=True)))
    model.add(Dropout(0.3))
    
    # Third LSTM layer for deeper feature extraction
    model.add(Bidirectional(LSTM(32, return_sequences=False)))
    model.add(Dropout(0.2))
    
    # Dense layers for final prediction
    model.add(Dense(64, activation='relu'))
    model.add(Dropout(0.2))
    model.add(Dense(32, activation='relu'))
    model.add(Dense(16, activation='relu'))
    model.add(Dense(1, activation='linear'))  # Linear for regression output
    
    # Use Adam optimizer with MSE loss (proven to work well for this task)
    optimizer = Adam(learning_rate=0.001)
    model.compile(loss='mse', optimizer=optimizer, metrics=['mae'])
    
    return model


def calculate_smape(y_true, y_pred, clip_outliers=True):
    """
    Calculate Symmetric Mean Absolute Percentage Error (SMAPE).
    SMAPE is bounded between 0% and 200%, making it more interpretable.
    
    Args:
        y_true: Actual values
        y_pred: Predicted values
        clip_outliers: If True, exclude samples where both actual and predicted 
                       are below a threshold (removes noise from low-traffic periods)
    """
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()
    
    # Optional: Filter out very low traffic periods that add noise
    if clip_outliers:
        # Exclude periods where actual traffic is extremely low (< 100 requests)
        # These periods have high relative error but low business importance
        threshold = max(50, np.percentile(y_true, 10))  # Use 10th percentile or 50
        valid_mask = y_true >= threshold
        if np.sum(valid_mask) > 0:
            y_true = y_true[valid_mask]
            y_pred = y_pred[valid_mask]
    
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2
    # Avoid division by zero
    denominator = np.where(denominator == 0, 1e-10, denominator)
    
    smape = np.mean(np.abs(y_true - y_pred) / denominator) * 100
    return smape


def calculate_accuracy_percentage(y_true, y_pred, filter_low_traffic=True):
    """
    Calculate forecast accuracy using SMAPE-based approach.
    
    WHY SMAPE over MAPE:
    - MAPE (Mean Absolute Percentage Error) can explode to infinity when 
      actual values are near zero (e.g., nighttime traffic ~100 requests)
    - SMAPE (Symmetric MAPE) is bounded between 0% and 200%, making it
      stable and interpretable for data with high variability
    
    ACCURACY FORMULA:
    - SMAPE ranges from 0% (perfect) to 200% (worst)
    - Accuracy = 100% - (SMAPE / 2)
    - This maps SMAPE to a 0-100% accuracy scale:
      * SMAPE = 0%   -> Accuracy = 100% (perfect predictions)
      * SMAPE = 100% -> Accuracy = 50%  (average error equals average value)
      * SMAPE = 200% -> Accuracy = 0%   (worst case)
    
    Args:
        y_true: Actual values (numpy array or list)
        y_pred: Predicted values (numpy array or list)
        filter_low_traffic: If True, filters out very low traffic periods
                           that contribute noise but not business value
        
    Returns:
        Accuracy percentage bounded between 0% and 100%
    """
    y_true = np.array(y_true).flatten()
    y_pred = np.array(y_pred).flatten()
    
    # Filter out very low traffic periods which add noise to the metric
    if filter_low_traffic:
        threshold = max(50, np.percentile(y_true, 10))
        valid_mask = y_true >= threshold
        if np.sum(valid_mask) > 0:
            y_true = y_true[valid_mask]
            y_pred = y_pred[valid_mask]
    
    # Calculate SMAPE: |y_true - y_pred| / ((|y_true| + |y_pred|) / 2)
    denominator = (np.abs(y_true) + np.abs(y_pred)) / 2
    # Avoid division by zero
    denominator = np.where(denominator == 0, 1e-10, denominator)
    
    # SMAPE for each sample (as ratio, not percentage)
    smape_values = np.abs(y_true - y_pred) / denominator
    mean_smape = np.mean(smape_values) * 100  # Convert to percentage (0-200%)
    
    # Convert SMAPE to accuracy: 100% - (SMAPE/2)
    # This ensures accuracy is bounded between 0% and 100%
    accuracy = max(0, min(100, 100 - (mean_smape / 2)))
    
    return accuracy


def train_and_save_model():
    """
    Trains an improved LSTM model with:
    - Proper data preprocessing and scaling
    - Early stopping and learning rate reduction
    - Training time optimized to be between 5-30 minutes
    """
    import time as time_module
    training_start_time = time_module.time()
    
    print("Starting model training and evaluation process...")
    
    # ALERT: Model retraining started
    if ALERTS_AVAILABLE:
        alert_model_retraining_started()
    
    full_data = load_and_preprocess_full_data()
    if full_data is None:
        print("Process aborted due to data loading failure.")
        return False, None, None, None

    # Get the raw traffic values
    sessions = full_data['TrafficCount'].values.astype(np.float32)
    
    # --- Use MinMaxScaler with consistent scaling ---
    scaler = MinMaxScaler(feature_range=(0, 1))
    sessions_scaled = scaler.fit_transform(sessions.reshape(-1, 1)).flatten()
    
    # Prepare sequences using scaled data
    x_data, y_data = prepare_data(sessions_scaled, LOOK_BACK_HOURS)

    total_samples = len(x_data)
    print(f"Total samples available: {total_samples}")

    # Split indices
    train_end_idx = int(total_samples * train_percentage)
    val_end_idx = train_end_idx + int(total_samples * val_percentage)

    # Split data
    x_train, y_train = x_data[:train_end_idx], y_data[:train_end_idx]
    x_val, y_val = x_data[train_end_idx:val_end_idx], y_data[train_end_idx:val_end_idx]
    x_test, y_test = x_data[val_end_idx:], y_data[val_end_idx:]

    print(f"Training samples: {len(x_train)}")
    print(f"Validation samples: {len(x_val)}")
    print(f"Test samples: {len(x_test)}")

    # Reshape for LSTM: [samples, time_steps, features]
    x_train = x_train.reshape(x_train.shape[0], x_train.shape[1], 1)
    x_val = x_val.reshape(x_val.shape[0], x_val.shape[1], 1)
    x_test = x_test.reshape(x_test.shape[0], x_test.shape[1], 1)

    # Save the scaler with metadata
    try:
        scaler_data = {
            'scaler': scaler,
            'use_log_transform': False  # Not using log transform
        }
        joblib.dump(scaler_data, SCALER_X_PATH)
        joblib.dump(scaler_data, SCALER_Y_PATH)
        print(f"Successfully saved fitted scaler to {SCALER_X_PATH} and {SCALER_Y_PATH}")
    except Exception as e:
        print(f"Error saving scalers: {e}")
        return False, None, None, None

    # Build the optimized model
    model = build_model(input_features=1)
    model.summary()

    # Callbacks optimized for 5-30 minute training time
    callbacks = [
        ModelCheckpoint(
            BEST_MODEL_CHECKPOINT_PATH, 
            monitor='val_loss', 
            verbose=1, 
            save_best_only=True, 
            mode='min'
        ),
        EarlyStopping(
            monitor='val_loss',
            patience=12,  # Balanced patience
            verbose=1,
            restore_best_weights=True
        ),
        ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=5,
            verbose=1,
            min_lr=1e-6
        )
    ]

    print("\nTraining with improved model architecture...")
    history = model.fit(
        x_train, y_train,
        epochs=60,  # Adjusted for balanced training time
        batch_size=32,
        validation_data=(x_val, y_val),
        callbacks=callbacks,
        verbose=1
    )
    
    training_duration = time_module.time() - training_start_time
    print(f"\nTraining completed in {training_duration/60:.2f} minutes")

    # --- COMPREHENSIVE EVALUATION ON TEST SET ---
    print("\n" + "="*60)
    print("EVALUATING MODEL ON TEST SET")
    print("="*60)
    
    r2 = None
    accuracy_pct = None
    smape = None

    try:
        # Predict on entire test set
        y_pred_scaled = model.predict(x_test, verbose=0)
        
        # Inverse transform to original scale (no log transform)
        y_pred_original = scaler.inverse_transform(y_pred_scaled.reshape(-1, 1)).flatten()
        y_test_original = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()
        
        # Ensure non-negative predictions
        y_pred_original = np.maximum(0, y_pred_original)
        
        # Calculate metrics on original scale
        mse = mean_squared_error(y_test_original, y_pred_original)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_test_original, y_pred_original)
        r2 = r2_score(y_test_original, y_pred_original)
        mape = mean_absolute_percentage_error(y_test_original, y_pred_original) * 100
        smape = calculate_smape(y_test_original, y_pred_original)
        accuracy_pct = calculate_accuracy_percentage(y_test_original, y_pred_original)
        
        print(f"\n--- Model Performance Metrics ---")
        print(f"Mean Squared Error (MSE):                {mse:.2f}")
        print(f"Root Mean Squared Error (RMSE):          {rmse:.2f}")
        print(f"Mean Absolute Error (MAE):               {mae:.2f}")
        print(f"R-squared (R2):                          {r2*100:.2f}%")
        print(f"Mean Absolute Percentage Error (MAPE):   {mape:.2f}%")
        print(f"Symmetric MAPE (SMAPE):                  {smape:.2f}%")
        print(f"Forecast Accuracy (100 - SMAPE/2):       {accuracy_pct:.2f}%")
        print("-"*60)
        print(f"Training duration:                       {training_duration/60:.2f} minutes")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"Warning: Could not perform evaluation: {e}")
        traceback.print_exc()
    
    # Save the final model
    model.save(MODEL_PATH)
    print(f"Successfully trained and saved model to '{MODEL_PATH}'")
    
    # ALERT: Model retraining complete with metrics
    if ALERTS_AVAILABLE and accuracy_pct is not None and r2 is not None and smape is not None:
        alert_model_retraining_complete(accuracy_pct, r2, smape)
    
    # Clean up checkpoint if it exists
    if os.path.exists(BEST_MODEL_CHECKPOINT_PATH):
        os.remove(BEST_MODEL_CHECKPOINT_PATH)
    
    return True, r2, accuracy_pct, smape

# --- 5. REAL-TIME PREDICTION ---

def get_realtime_prediction_input(full_data, scaler_data):
    """
    Finds a historical data window *within the test data split* matching
    the current day/hour, scales it using the fitted scaler, and returns input array.
    
    Args:
        full_data: Complete DataFrame with hourly resampled data
        scaler_data: Dict containing 'scaler' and 'use_log_transform' flag
        
    Returns:
        Scaled 3D input array for LSTM prediction, or None if error
    """
    if full_data is None or scaler_data is None:
        print("Error: full_data or scaler not provided.")
        return None

    # Handle both old format (just scaler) and new format (dict with scaler and flag)
    if isinstance(scaler_data, dict):
        scaler = scaler_data['scaler']
        use_log = scaler_data.get('use_log_transform', False)
    else:
        scaler = scaler_data
        use_log = False

    try:
        # 1. Identify the Test Data Portion
        total_hours = len(full_data)
        if total_hours <= LOOK_BACK_HOURS:
            print(f"Error: full_data has {total_hours} hours, not enough for look_back={LOOK_BACK_HOURS}.")
            return None

        total_sequences = total_hours - LOOK_BACK_HOURS
        test_sequence_start_index = int(total_sequences * (train_percentage + val_percentage))

        test_data_start_timestamp = full_data.index[test_sequence_start_index]
        test_data = full_data[full_data.index >= test_data_start_timestamp]

        if test_data.empty:
            print("Error: Could not isolate test data portion.")
            return None

        # 2. Search Within Test Data for Time Match
        now = datetime.now(LOCAL_TZ) 
        matching_indices_in_test = test_data[
            (test_data.index.weekday == now.weekday()) &
            (test_data.index.hour == now.hour)
        ]

        # 3. Determine End Index within Test Data Slice
        if matching_indices_in_test.empty:
            print(f"Warning: No match found *in test data* for {now.strftime('%A %H:00')}. Using last window.")
            end_index_in_test = len(test_data)
        else:
            last_matching_timestamp = matching_indices_in_test.index[-1]
            try:
                end_index_in_test = test_data.index.get_loc(last_matching_timestamp) + 1
                print(f"Found match in test data ending at {last_matching_timestamp}.")
            except KeyError:
                 end_index_in_test = len(test_data)

        # 4. Calculate Start Index
        start_index_in_test = max(0, end_index_in_test - LOOK_BACK_HOURS)

        if end_index_in_test < LOOK_BACK_HOURS:
             print(f"Warning: Not enough history ({end_index_in_test} hrs).")
             start_index_in_test = 0
             end_index_in_test = LOOK_BACK_HOURS
             if len(test_data) < LOOK_BACK_HOURS:
                 return None

        # 5. Extract Window
        prediction_window = test_data.iloc[start_index_in_test:end_index_in_test]

        if len(prediction_window) != LOOK_BACK_HOURS:
             return None

        # 6. Get values and apply log transform if needed
        input_values = prediction_window['TrafficCount'].values.astype(np.float32)
        
        if use_log:
            input_values = np.log1p(input_values)  # log(1 + x)
        
        # Scale the input values
        input_scaled = scaler.transform(input_values.reshape(-1, 1)).flatten()

        # 7. Reshape for LSTM: [1, time_steps, 1]
        return input_scaled.reshape(1, LOOK_BACK_HOURS, 1)

    except Exception as e:
        print(f"Error during get_realtime_prediction_input: {e}")
        traceback.print_exc()
        return None


def predict_next_hour(model, input_data, scaler_data):
    """
    Makes a prediction and inverse transforms to original scale.
    
    Args:
        model: Trained LSTM model
        input_data: Scaled input data (3D array)
        scaler_data: Dict containing 'scaler' and 'use_log_transform' flag
        
    Returns:
        Predicted traffic count as integer
    """
    # Handle both old format (just scaler) and new format (dict with scaler and flag)
    if isinstance(scaler_data, dict):
        scaler = scaler_data['scaler']
        use_log = scaler_data.get('use_log_transform', False)
    else:
        scaler = scaler_data
        use_log = False
    
    predicted_scaled = model.predict(input_data, verbose=0)
    
    # Inverse scale
    predicted_log = scaler.inverse_transform(predicted_scaled.reshape(-1, 1))
    
    # Inverse log transform if used during training
    if use_log:
        predicted_traffic = np.expm1(predicted_log)  # inverse of log1p
    else:
        predicted_traffic = predicted_log
    
    return max(0, int(predicted_traffic[0][0]))  # Ensure non-negative

# --- 6. MAIN INTERFACE ---

def get_hourly_forecast():
    """
    Main function to run the forecasting application.
    Checks model validity for the current week, retrains if necessary, and returns prediction.
    """
    now = datetime.now(LOCAL_TZ) 
    
    # --- MODEL VALIDITY CHECK ---
    # Determine what the valid range SHOULD be for today
    valid_start, valid_end = get_current_week_range(now)
    
    print(f"\n[Model Check] Checking model validity for week: {valid_start} to {valid_end}")
    
    # If model is missing OR invalid for this specific week, Retrain.
    if not os.path.exists(MODEL_PATH) or not is_model_valid_for_current_week(now):
        print(f"[Model Check] Model is expired, missing, or invalid for this week. Initiating Retraining...")
        
        # RETRAIN - now returns 4 values
        success, r2_val, accuracy_pct, smape_val = train_and_save_model()
        
        if success:
            # Update the JSON validity file with all metrics
            update_model_validity(valid_start, valid_end, r2_val, accuracy_pct, smape_val)
            print("[Model Check] Retraining complete. Validity and metrics updated.")
        else:
            print("[Model Check] FATAL: Retraining failed. Cannot proceed with prediction.")
            # ALERT: Forecast failed due to retraining failure
            if ALERTS_AVAILABLE:
                alert_forecast_failed("Model retraining failed")
            return None
    else:
        print("[Model Check] Model is valid for the current week. Proceeding to prediction.")

    # --- PREDICTION EXECUTION ---
    if os.path.exists(MODEL_PATH):
        print(f"Loading model...")
        prediction_model = load_model(MODEL_PATH)
        
        print("Loading and preparing data from test range dataset for predictions...")
        full_data = load_and_preprocess_full_data()
        if full_data is None:
             print("Fatal Error: Could not load data. Exiting.")
             # ALERT: Forecast failed due to data loading failure
             if ALERTS_AVAILABLE:
                 alert_forecast_failed("Could not load traffic data")
             return None

        # Load the scaler (same scaler for both input scaling and output inverse transform)
        scaler = joblib.load(SCALER_X_PATH)
        prediction_input = get_realtime_prediction_input(full_data, scaler)
        
        if prediction_input is not None:
            predicted_value = predict_next_hour(prediction_model, prediction_input, scaler)
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Predicted Web Traffic for next hour: {predicted_value} requests.")
            return predicted_value
        else:
            print("Error: Could not generate prediction input.")
            # ALERT: Forecast failed due to input generation failure
            if ALERTS_AVAILABLE:
                alert_forecast_failed("Could not generate prediction input")
            return None
    else:
        print(f"Fatal Error: Could not create or find model at '{MODEL_PATH}'. Exiting.")
        # ALERT: Forecast failed due to missing model
        if ALERTS_AVAILABLE:
            alert_forecast_failed(f"Model file not found at {MODEL_PATH}")
        return None