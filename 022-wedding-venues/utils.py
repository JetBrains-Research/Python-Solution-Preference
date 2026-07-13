import csv
import math
from typing import Dict, Tuple, Optional

POSTCODE_DATA_FILE = 'assets/postcode-outcodes.csv'
_postcode_coords: Dict[str, Tuple[float, float]] = {}

def load_postcodes():
    global _postcode_coords
    try:
        with open(POSTCODE_DATA_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            # Assume CSV format: postcode, lat, long
            for row in reader:
                if not row: continue
                # Handling potential header or malformed lines
                try:
                    pc, lat, lon = row[0].strip().upper(), float(row[1]), float(row[2])
                    _postcode_coords[pc] = (lat, lon)
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        print(f"Warning: {POSTCODE_DATA_FILE} not found.")

def get_coords(postcode: str) -> Optional[Tuple[float, float]]:
    return _postcode_coords.get(postcode.strip().upper())

def haversine(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    # Returns distance in miles
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 3958.8 # Radius of Earth in miles
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

# Initialize the data
load_postcodes()
