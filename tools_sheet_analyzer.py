import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import config

# --- CONFIGURATION ---
SHEET_NAME = "Sheet1"  # Check your actual tab name
CREDENTIALS_FILE = "google_credentials.json" # Your Service Account Key
SCORE_COLUMN = "Score"      # The exact header name in your sheet

def connect_to_sheet():
    """Connects to Google Sheets and returns the DataFrame."""
    print(f"⚡ [ANALYZER] Connecting to Google Sheet: '{SHEET_NAME}'...")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        # Open the specific tab
        sheet = client.open_by_key(config.GOOGLE_SHEET_NAME).worksheet(SHEET_NAME)
        
        # Get all records as a list of dicts
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Convert Score to Numeric (forcing errors to NaN then dropping)
        df[SCORE_COLUMN] = pd.to_numeric(df[SCORE_COLUMN], errors='coerce')
        df.dropna(subset=[SCORE_COLUMN], inplace=True)
        
        print(f"✅ [ANALYZER] Successfully loaded {len(df)} records.")
        return df
        
    except Exception as e:
        print(f"❌ [ANALYZER] Connection Failed: {e}")
        return None

def run_sensitivity_analysis(df):
    """
    Simulates different filter thresholds to help select the best one.
    """
    print("\n" + "="*50)
    print(f"🔍 SENSITIVITY ANALYSIS (Target: {SCORE_COLUMN})")
    print("="*50)
    
    total_records = len(df)
    
    # Define test thresholds
    thresholds = [60, 70, 75, 80, 85, 90, 95]
    
    print(f"{'THRESHOLD':<12} | {'SURVIVORS':<10} | {'DROP RATE':<10} | {'SAMPLE TICKERS'}")
    print("-" * 75)
    
    for cut in thresholds:
        # Filter logic
        survivors = df[df[SCORE_COLUMN] >= cut]
        count = len(survivors)
        drop_rate = ((total_records - count) / total_records) * 100
        
        # Get a quick sample of tickers that pass this filter
        sample_tickers = survivors['Ticker'].head(5).tolist() # Assumes 'Ticker' column exists
        sample_str = ", ".join(sample_tickers)
        if len(survivors) > 5:
            sample_str += ", ..."
            
        print(f"> {cut:<10} | {count:<10} | {drop_rate:>6.1f}%    | {sample_str}")
    
    print("-" * 75)
    
    # --- STATISTICS ---
    avg_score = df[SCORE_COLUMN].mean()
    median_score = df[SCORE_COLUMN].median()
    print(f"\n📊 DATASET STATS:")
    print(f"   - Average Score: {avg_score:.2f}")
    print(f"   - Median Score:  {median_score:.2f}")
    print(f"   - Max Score:     {df[SCORE_COLUMN].max()}")
    print("="*50)

    # --- RECOMMENDATION ---
    # Simple logic: Suggest a cutoff that keeps top 20% of data (Pareto Principle)
    top_20_percentile = df[SCORE_COLUMN].quantile(0.80)
    print(f"💡 RECOMMENDATION: Consider setting filter to > {top_20_percentile:.0f}")
    print(f"   (This retains the top 20% of your historical signals)")

if __name__ == "__main__":
    df = connect_to_sheet()
    if df is not None:
        run_sensitivity_analysis(df)