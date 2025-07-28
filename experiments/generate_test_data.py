import os
import csv
from datetime import datetime, timedelta

# Create data directory
data_dir = Path(__file__).parent / "input_data"
os.makedirs(data_dir, exist_ok=True)

# Define sample dates
base_date = datetime(2025, 7, 23)
dates = [base_date + timedelta(days=i) for i in range(3)]

# Sample staypoints for each day
sample_staypoints = {
    0: [("loc_home", "07:00:00", "08:00:00"),
        ("loc_work", "08:30:00", "17:00:00"),
        ("loc_gym", "17:30:00", "18:30:00"),
        ("loc_home", "19:00:00", "22:00:00")],
    1: [("loc_home", "07:15:00", "08:15:00"),
        ("loc_coffee", "08:30:00", "09:00:00"),
        ("loc_work", "09:30:00", "17:30:00"),
        ("loc_home", "18:00:00", "21:30:00")],
    2: [("loc_home", "06:50:00", "07:50:00"),
        ("loc_park", "08:00:00", "09:00:00"),
        ("loc_work", "09:30:00", "17:00:00"),
        ("loc_home", "17:30:00", "23:00:00")],
}

# Write CSV files
for idx, date in enumerate(dates):
    filename = f"{date.strftime('%Y%m%d')}_staypoints.csv"
    filepath = os.path.join(data_dir, filename)
    with open(filepath, mode="w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["place_id", "start_iso", "end_iso"])
        for place_id, start_t, end_t in sample_staypoints[idx]:
            start_iso = f"{date.strftime('%Y-%m-%d')}T{start_t}"
            end_iso = f"{date.strftime('%Y-%m-%d')}T{end_t}"
            writer.writerow([place_id, start_iso, end_iso])

# List created files
created_files = os.listdir(data_dir)
created_files
