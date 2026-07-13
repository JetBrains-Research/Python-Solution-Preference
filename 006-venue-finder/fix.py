import re
import math

# Read main.py and fix the keyword matching
with open('main.py', 'r') as f:
    content = f.read()

# The fix: change the normalize function and all comparisons to use normalized strings
# We need to ensure that all comparison strings are normalized too

# Replace the normalize function call and comparisons
old = """def normalize(s):
    return s.replace('-', ' ').strip()"""

new = """def normalize(s):
    return s.replace('-', ' ').strip().lower()"""

content = content.replace(old, new)

# Now fix the preference matching where we compare against 'good-value', 'family-friendly' etc.
# These should be normalized too
# We compare keywords_norm against normalized strings

# Actually the issue is:
# venue 'family-friendly' -> normalized to 'family friendly'
# we check 'family-friendly' in keywords_norm -> False (because we check non-normalized)
# Fix: normalize the comparison strings

# Let's carefully rewrite the matching function
old_match = """def venue_matches_keyword_preference(venue, pref):
    pref_norm = normalize(pref.lower())
    keywords_norm = [normalize(k) for k in venue.get('Keywords', [])]
    facilities_norm = [normalize(f) for f in venue.get('Facilities', [])]
    price = venue.get('price_range', '')
    
    if pref_norm == "highly rated":
        return venue.get('rating', 0) >= 4.5
    if pref_norm == "good value":
        return 'good-value' in keywords_norm or price in ['$', '$$']
    if pref_norm == "great atmosphere":
        atm_kw = {'lively', 'cozy', 'beautiful', 'vibrant', 'welcoming', 'elegant', 'sophisticated', 'fun'}
        return any(k in atm_kw for k in keywords_norm)
    if pref_norm == "romantic":
        return 'romantic' in keywords_norm
    if pref_norm == "group friendly":
        return 'spacious seating' in facilities_norm or 'family-gatherings' in keywords_norm
    if pref_norm == "full bar":
        return 'full bar' in facilities_norm
    if pref_norm == "scenic view":
        return 'scenic view' in facilities_norm
    if pref_norm == "quiet":
        return 'quiet' in keywords_norm
    if pref_norm == "clean":
        return 'clean' in keywords_norm
    if pref_norm == "upscale":
        return price in ['$$$', '$$$$'] or 'upscale' in keywords_norm or 'elegant' in keywords_norm
    if pref_norm == "casual":
        return price in ['$', '$$'] or 'casual' in keywords_norm
    if pref_norm == "family gathering":
        return 'family-gatherings' in keywords_norm
    if pref_norm in ["child-friendly", "kids welcome"]:
        child_facs = {'play area', 'high chairs', 'kids utensils', 'changing station'}
        if any(f in child_facs for f in facilities_norm):
            return True
        return 'family-friendly' in keywords_norm
    if pref_norm == "entertainment":
        return 'entertainment' in facilities_norm or 'entertaining' in keywords_norm
    if pref_norm == "activities":
        act_kw = {'activities', 'interactive', 'hands-on'}
        return 'play area' in facilities_norm or any(k in act_kw for k in keywords_norm)
    return False"""

new_match = """def venue_matches_keyword_preference(venue, pref):
    pref_norm = normalize(pref)
    keywords_norm = [normalize(k) for k in venue.get('Keywords', [])]
    facilities_norm = [normalize(f) for f in venue.get('Facilities', [])]
    price = normalize(venue.get('price_range', ''))
    
    if pref_norm == "highly rated":
        return venue.get('rating', 0) >= 4.5
    if pref_norm == "good value":
        return normalize('good value') in keywords_norm or price in [normalize('$'), normalize('$$')]
    if pref_norm == "great atmosphere":
        atm_kw = {normalize(k) for k in ['lively', 'cozy', 'beautiful', 'vibrant', 'welcoming', 'elegant', 'sophisticated', 'fun']}
        return any(k in atm_kw for k in keywords_norm)
    if pref_norm == "romantic":
        return normalize('romantic') in keywords_norm
    if pref_norm == "group friendly":
        return normalize('spacious seating') in facilities_norm or normalize('family gatherings') in keywords_norm
    if pref_norm == "full bar":
        return normalize('full bar') in facilities_norm
    if pref_norm == "scenic view":
        return normalize('scenic view') in facilities_norm
    if pref_norm == "quiet":
        return normalize('quiet') in keywords_norm
    if pref_norm == "clean":
        return normalize('clean') in keywords_norm
    if pref_norm == "upscale":
        return price in [normalize('$$$'), normalize('$$$$')] or normalize('upscale') in keywords_norm or normalize('elegant') in keywords_norm
    if pref_norm == "casual":
        return price in [normalize('$'), normalize('$$')] or normalize('casual') in keywords_norm
    if pref_norm == "family gathering":
        return normalize('family gatherings') in keywords_norm
    if pref_norm in ["child-friendly", "kids welcome"]:
        child_facs = {normalize(f) for f in ['play area', 'high chairs', 'kids utensils', 'changing station']}
        if any(f in child_facs for f in facilities_norm):
            return True
        return normalize('family friendly') in keywords_norm
    if pref_norm == "entertainment":
        return normalize('entertainment') in facilities_norm or normalize('entertaining') in keywords_norm
    if pref_norm == "activities":
        act_kw = {normalize(k) for k in ['activities', 'interactive', 'hands-on']}
        return normalize('play area') in facilities_norm or any(k in act_kw for k in keywords_norm)
    return False"""

content = content.replace(old_match, new_match)

# Also fix the cuisine matching to use normalize
old_cuisine = """    if prefs_dict.get('cuisine_types'):
        ven_cuisine = venue.get('cuisine_type', '').lower().strip()
        selected = [c.lower().strip() for c in prefs_dict['cuisine_types']]
        if ven_cuisine not in selected:
            return False
    if prefs_dict.get('dietary_options'):
        ven_diets = [d.lower().strip() for d in venue.get('Dietary Options', [])]
        selected = [d.lower().strip() for d in prefs_dict['dietary_options']]
        if not any(d in ven_diets for d in selected):
            return False
    if prefs_dict.get('facilities'):
        ven_facs = [f.lower().strip() for f in venue.get('Facilities', [])]
        selected = [f.lower().strip() for f in prefs_dict['facilities']]
        if not any(f in ven_facs for f in selected):
            return False"""

new_cuisine = """    if prefs_dict.get('cuisine_types'):
        ven_cuisine = normalize(venue.get('cuisine_type', ''))
        selected = [normalize(c) for c in prefs_dict['cuisine_types']]
        if ven_cuisine not in selected:
            return False
    if prefs_dict.get('dietary_options'):
        ven_diets = [normalize(d) for d in venue.get('Dietary Options', [])]
        selected = [normalize(d) for d in prefs_dict['dietary_options']]
        if not any(d in ven_diets for d in selected):
            return False
    if prefs_dict.get('facilities'):
        ven_facs = [normalize(f) for f in venue.get('Facilities', [])]
        selected = [normalize(f) for f in prefs_dict['facilities']]
        if not any(f in ven_facs for f in selected):
            return False"""

content = content.replace(old_cuisine, new_cuisine)

with open('main.py', 'w') as f:
    f.write(content)

print("Fixed!")
