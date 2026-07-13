from fastapi import FastAPI, HTTPException
from typing import List, Optional, Union, Dict, Any
from datetime import datetime
import uuid
from copy import deepcopy
from enum import Enum

app = FastAPI(title="Furniture Delivery Pricing Calculator")

# Data storage (in-memory)
settings = {
    'rural_rate_per_km': 0.0,
    'assembly_rate_per_interval': 0.0,
    'rubbish_flat_rate': 0.0
}

locations = []
rate_cards = []
furniture_catalog = []
quotes = []

class DeliveryType(str, Enum):
    B2B = "B2B"
    B2C = "B2C"

class LocationType(str, Enum):
    STORE = "store"
    WAREHOUSE = "warehouse"
    SUPPLIER = "supplier"

class ServiceType(str, Enum):
    B2B = "B2B"
    B2C = "B2C"

# Helper functions
def get_location_by_id(location_id: str):
    for location in locations:
        if location['id'] == location_id:
            return deepcopy(location)
    return None

def get_rate_card_by_id(rate_card_id: str):
    for rate_card in rate_cards:
        if rate_card['id'] == rate_card_id:
            return deepcopy(rate_card)
    return None

def get_furniture_item_by_id(item_id: str):
    for item in furniture_catalog:
        if item['id'] == item_id:
            return deepcopy(item)
    return None

def get_furniture_item_by_sku(catalog_sku: str):
    for item in furniture_catalog:
        if item['sku'] == catalog_sku:
            return deepcopy(item)
    return None

def validate_required_inputs(request: Dict[str, Any]) -> bool:
    required_fields = ['delivery_type', 'origin_id', 'destination', 'items']
    for field in required_fields:
        if not request.get(field):
            return False
    items = request.get('items', [])
    if len(items) == 0:
        return False
    return True

def find_matching_rate_card(service_type: str, from_city: str, to_city: str, to_suburb: str):
    matching_rates = []

    filtered_rates = [rc for rc in rate_cards
                     if rc['service_type'] == service_type and rc['from_city'] == from_city]

    exact_matches = []
    city_matches = []

    for rc in filtered_rates:
        if rc['to_city'] == to_city:
            if rc['to_suburb'] == to_suburb:
                exact_matches.append(rc)
            else:
                city_matches.append(rc)

    if exact_matches:
        return exact_matches, 'Exact Match'
    elif city_matches:
        return city_matches, 'City Match'
    else:
        # Check if there are any rate cards for this to_city
        to_city_matches = [rc for rc in filtered_rates if rc['to_city'] == to_city]
        if to_city_matches:
            return to_city_matches, 'City Match'
        else:
            return [], ''

def calculate_quote(request: Dict[str, Any]) -> Dict[str, Any]:
    # Validate required inputs
    if not validate_required_inputs(request):
        return {
            'success': False,
            'error': 'Missing required inputs: Delivery Type, Origin, Destination, at least one item'
        }

    delivery_type = request.get('delivery_type')
    origin_id = request.get('origin_id')
    destination = request.get('destination')
    items = request.get('items', [])
    services = request.get('services', {})

    # Get origin location
    origin_location = get_location_by_id(origin_id)
    if not origin_location:
        return {
            'success': False,
            'error': 'Origin location not found'
        }

    # Process destination
    if delivery_type == 'B2B':
        if isinstance(destination, str):
            dest_location = get_location_by_id(destination)
            if not dest_location:
                return {
                    'success': False,
                    'error': 'Destination location not found'
                }
            dest_city = dest_location['city']
            dest_suburb = dest_location['suburb']
        else:
            return {
                'success': False,
                'error': 'B2B delivery requires destination to be a location ID'
            }
    elif delivery_type == 'B2C':
        if isinstance(destination, dict):
            dest_city = destination.get('city', '')
            dest_suburb = destination.get('suburb', '')
        else:
            return {
                'success': False,
                'error': 'B2C delivery requires destination to be city and optional suburb'
            }
    else:
        return {
            'success': False,
            'error': 'Invalid delivery type'
        }

    # Process items
    total_cubic_metres = 0.0
    processed_items = []

    for item in items:
        if 'sku' in item:  # Catalog item
            catalog_item = get_furniture_item_by_sku(item['sku'])
            if not catalog_item:
                sku = item['sku']
                return {
                    'success': False,
                    'error': f'Catalog item with SKU {sku} not found'
                }

            cubic_metres = item.get('cubic_metres_override', catalog_item['cubic_metres'])
            quantity = item.get('quantity', 1)
            item_total = cubic_metres * quantity
            total_cubic_metres += item_total

            processed_items.append({
                'sku': item['sku'],
                'name': catalog_item['name'],
                'cubic_metres': cubic_metres,
                'quantity': quantity,
                'total_cubic_metres': round(item_total, 2),
                'category': catalog_item['category'],
                'type': 'catalog'
            })
        else:  # Custom item
            name = item.get('name', 'Custom Item')
            cubic_metres = item.get('cubic_metres', 0.0)
            quantity = item.get('quantity', 1)
            item_total = cubic_metres * quantity
            total_cubic_metres += item_total

            processed_items.append({
                'name': name,
                'cubic_metres': round(cubic_metres, 2),
                'quantity': quantity,
                'total_cubic_metres': round(item_total, 2),
                'type': 'custom'
            })

    # Volume charged
    volume_charged = max(1.00, total_cubic_metres)

    # Find matching rate card
    matching_rates, match_tier = find_matching_rate_card(
        delivery_type, origin_location['city'], dest_city, dest_suburb
    )

    if not matching_rates:
        # No rate card available
        return {
            'success': True,
            'unavailable': True,
            'match_tier': 'No rate card for selected route and delivery type.',
            'volume_charged': round(volume_charged, 2),
            'processed_items': processed_items,
            'delivery_type': delivery_type,
            'origin_city': origin_location['city'],
            'destination_city': dest_city,
            'destination_suburb': dest_suburb
        }

    # Get the rate to use
    if match_tier == 'Exact Match':
        rate_per_m3 = min([r['rate_per_m3'] for r in matching_rates])
    elif match_tier == 'City Match':
        rate_per_m3 = max([r['rate_per_m3'] for r in matching_rates])
        # Count unique non-empty suburbs for this city
        unique_suburbs = set()
        for rc in matching_rates:
            if rc['to_suburb']:  # Only count non-empty suburbs
                unique_suburbs.add(rc['to_suburb'])
        suburban_count = len(unique_suburbs)
        match_tier += f" {suburban_count} suburbs available for this city."

    # Process services
    assembly_intervals = services.get('assembly_intervals', 0)
    rubbish_quantity = services.get('rubbish_quantity', 0)
    rural_km = services.get('rural_km', 0)

    # Validate service constraints
    if delivery_type == 'B2B' and rural_km > 0:
        return {
            'success': False,
            'error': 'Rural km is not accepted for B2B'
        }

    if assembly_intervals < 0 or assembly_intervals > 99:
        return {
            'success': False,
            'error': 'Assembly intervals must be between 0-99'
        }

    if rubbish_quantity < 0 or rubbish_quantity > 99:
        return {
            'success': False,
            'error': 'Rubbish quantity must be between 0-99'
        }

    if rural_km < 0:
        return {
            'success': False,
            'error': 'Rural km must be >= 0'
        }

    # Calculate costs
    base_delivery = rate_per_m3 * volume_charged
    assembly_cost = settings['assembly_rate_per_interval'] * assembly_intervals
    rubbish_cost = settings['rubbish_flat_rate'] * rubbish_quantity
    rural_cost = settings['rural_rate_per_km'] * rural_km

    total_cost = base_delivery + assembly_cost + rubbish_cost + rural_cost

    # Prepare volume message
    volume_message = f"{total_cubic_metres:.2f} m³"
    if total_cubic_metres < 1.00:
        volume_message += " (charged as 1.00 m³)"

    # Prepare result
    result = {
        'success': True,
        'unavailable': False,
        'match_tier': match_tier,
        'matched_rate_per_m3': round(rate_per_m3, 2),
        'volume_charged': round(volume_charged, 2),
        'volume_message': volume_message,
        'base_delivery': round(base_delivery, 2),
        'assembly_cost': round(assembly_cost, 2),
        'rubbish_cost': round(rubbish_cost, 2),
        'rural_cost': round(rural_cost, 2),
        'total': round(total_cost, 2),
        'processed_items': processed_items,
        'services': {
            'assembly_intervals': assembly_intervals,
            'rubbish_quantity': rubbish_quantity,
            'rural_km': rural_km
        },
        'delivery_type': delivery_type,
        'origin_city': origin_location['city'],
        'destination_city': dest_city,
        'destination_suburb': dest_suburb,
        'rate_per_m3': round(rate_per_m3, 2)
    }

    return result

# Settings endpoints
@app.get("/settings")
async def get_settings():
    return settings

@app.post("/settings")
async def create_settings(rural_rate_per_km: float = 0.0, assembly_rate_per_interval: float = 0.0, rubbish_flat_rate: float = 0.0):
    global settings
    settings['rural_rate_per_km'] = rural_rate_per_km
    settings['assembly_rate_per_interval'] = assembly_rate_per_interval
    settings['rubbish_flat_rate'] = rubbish_flat_rate
    return settings

# Locations endpoints
@app.get("/locations")
async def get_locations():
    return locations

@app.post("/locations")
async def create_location(type: LocationType, name: str, address: str, city: str, suburb: str = ""):
    location = {
        'id': str(uuid.uuid4()),
        'type': type.value if hasattr(type, 'value') else type,
        'name': name,
        'address': address,
        'city': city,
        'suburb': suburb
    }
    locations.append(location)
    return location

@app.get("/locations/{location_id}")
async def get_location(location_id: str):
    location = get_location_by_id(location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location

@app.put("/locations/{location_id}")
async def update_location(location_id: str, type: Optional[LocationType] = None, name: Optional[str] = None, address: Optional[str] = None, city: Optional[str] = None, suburb: Optional[str] = None):
    location = get_location_by_id(location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    location_copy = deepcopy(location)
    if type is not None:
        location_copy['type'] = type.value if hasattr(type, 'value') else type
    if name is not None:
        location_copy['name'] = name
    if address is not None:
        location_copy['address'] = address
    if city is not None:
        location_copy['city'] = city
    if suburb is not None:
        location_copy['suburb'] = suburb

    # Update the location in the list
    for i, loc in enumerate(locations):
        if loc['id'] == location_id:
            locations[i] = location_copy
            break

    return location_copy

@app.delete("/locations/{location_id}")
async def delete_location(location_id: str):
    for i, location in enumerate(locations):
        if location['id'] == location_id:
            locations.pop(i)
            return {"message": "Location deleted successfully"}
    raise HTTPException(status_code=404, detail="Location not found")

# Rate Cards endpoints
@app.get("/rateCards")
async def get_rate_cards():
    return rate_cards

@app.post("/rateCards")
async def create_rate_card(service_type: ServiceType, from_city: str, to_city: str, to_suburb: str = "", rate_per_m3: float = 0.0):
    if rate_per_m3 <= 0:
        raise HTTPException(status_code=400, detail="rate_per_m3 must be greater than 0")
    rate_card = {
        'id': str(uuid.uuid4()),
        'service_type': service_type.value if hasattr(service_type, 'value') else service_type,
        'from_city': from_city,
        'to_city': to_city,
        'to_suburb': to_suburb,
        'rate_per_m3': rate_per_m3
    }
    rate_cards.append(rate_card)
    return rate_card

@app.get("/rateCards/{rate_card_id}")
async def get_rate_card(rate_card_id: str):
    rate_card = get_rate_card_by_id(rate_card_id)
    if not rate_card:
        raise HTTPException(status_code=404, detail="Rate card not found")
    return rate_card

@app.put("/rateCards/{rate_card_id}")
async def update_rate_card(rate_card_id: str, service_type: Optional[ServiceType] = None, from_city: Optional[str] = None, to_city: Optional[str] = None, to_suburb: Optional[str] = None, rate_per_m3: Optional[float] = None):
    rate_card = get_rate_card_by_id(rate_card_id)
    if not rate_card:
        raise HTTPException(status_code=404, detail="Rate card not found")

    rate_card_copy = deepcopy(rate_card)
    if service_type is not None:
        rate_card_copy['service_type'] = service_type.value if hasattr(service_type, 'value') else service_type
    if from_city is not None:
        rate_card_copy['from_city'] = from_city
    if to_city is not None:
        rate_card_copy['to_city'] = to_city
    if to_suburb is not None:
        rate_card_copy['to_suburb'] = to_suburb
    if rate_per_m3 is not None:
        rate_card_copy['rate_per_m3'] = rate_per_m3

    # Update the rate card in the list
    for i, rc in enumerate(rate_cards):
        if rc['id'] == rate_card_id:
            rate_cards[i] = rate_card_copy
            break

    return rate_card_copy

@app.delete("/rateCards/{rate_card_id}")
async def delete_rate_card(rate_card_id: str):
    for i, rate_card in enumerate(rate_cards):
        if rate_card['id'] == rate_card_id:
            rate_cards.pop(i)
            return {"message": "Rate card deleted successfully"}
    raise HTTPException(status_code=404, detail="Rate card not found")

# Furniture Catalog endpoints
@app.get("/furniture")
async def get_furniture_catalog():
    return furniture_catalog

@app.post("/furniture")
async def create_furniture_item(sku: str, name: str, cubic_metres: float, category: str):
    furniture_item = {
        'id': str(uuid.uuid4()),
        'sku': sku,
        'name': name,
        'cubic_metres': cubic_metres,
        'category': category
    }
    furniture_catalog.append(furniture_item)
    return furniture_item

@app.get("/furniture/{item_id}")
async def get_furniture_item(item_id: str):
    item = get_furniture_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Furniture item not found")
    return item

@app.put("/furniture/{item_id}")
async def update_furniture_item(item_id: str, sku: Optional[str] = None, name: Optional[str] = None, cubic_metres: Optional[float] = None, category: Optional[str] = None):
    item = get_furniture_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Furniture item not found")

    item_copy = deepcopy(item)
    if sku is not None:
        item_copy['sku'] = sku
    if name is not None:
        item_copy['name'] = name
    if cubic_metres is not None:
        item_copy['cubic_metres'] = cubic_metres
    if category is not None:
        item_copy['category'] = category

    # Update the item in the list
    for i, fi in enumerate(furniture_catalog):
        if fi['id'] == item_id:
            furniture_catalog[i] = item_copy
            break

    return item_copy

@app.delete("/furniture/{item_id}")
async def delete_furniture_item(item_id: str):
    for i, item in enumerate(furniture_catalog):
        if item['id'] == item_id:
            furniture_catalog.pop(i)
            return {"message": "Furniture item deleted successfully"}
    raise HTTPException(status_code=404, detail="Furniture item not found")

# Quote Calculation endpoints
@app.post("/calculate")
async def calculate_quote_endpoint(request: Dict[str, Any]):
    result = calculate_quote(request)
    return result

# Quotes management endpoints
@app.post("/quotes")
async def save_quote(request: Dict[str, Any]):
    # First calculate the quote
    calculation_result = calculate_quote(request)

    # Create quote object with immutable snapshot
    quote = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'calculation_request': deepcopy(request),
        'calculation_result': deepcopy(calculation_result),
        'delivery_type': request.get('delivery_type', ''),
        'origin_city': '',
        'destination_city': '',
        'destination_suburb': '',
        'match_tier': calculation_result.get('match_tier', 'Unavailable'),
        'total': calculation_result.get('total', 'Unavailable')
    }

    # Set origin city from request
    origin_id = request.get('origin_id')
    origin_location = get_location_by_id(origin_id) if origin_id else None
    if origin_location:
        quote['origin_city'] = origin_location['city']

    # Set destination info
    destination = request.get('destination')
    if isinstance(destination, dict):
        quote['destination_city'] = destination.get('city', '')
        quote['destination_suburb'] = destination.get('suburb', '')
    elif isinstance(destination, str):
        # B2B destination is a location ID
        dest_location = get_location_by_id(destination)
        if dest_location:
            quote['destination_city'] = dest_location['city']
            quote['destination_suburb'] = dest_location['suburb']

    # Store the quote
    quotes.append(quote)

    # Return the quote in list format
    destination_city = quote.get('destination_city', '')
    destination_suburb = quote.get('destination_suburb', '')
    destination_str = destination_city
    if destination_suburb:
        destination_str += f" ({destination_suburb})"

    total = quote.get('total', 'Unavailable')
    if isinstance(total, (int, float)):
        total = f"{total:.2f}"

    return {
        'id': quote['id'],
        'timestamp': quote['timestamp'],
        'delivery_type': quote['delivery_type'],
        'origin_city': quote['origin_city'],
        'destination': destination_str,
        'match_tier': quote['match_tier'],
        'total': total
    }

@app.get("/quotes")
async def get_quotes():
    quotes_list = []
    for quote in quotes:
        destination_city = quote.get('destination_city', '')
        destination_suburb = quote.get('destination_suburb', '')
        destination_str = destination_city
        if destination_suburb:
            destination_str += f" ({destination_suburb})"

        total = quote.get('total', 'Unavailable')
        if isinstance(total, (int, float)):
            total = f"{total:.2f}"

        quotes_list.append({
            'id': quote['id'],
            'timestamp': quote['timestamp'],
            'delivery_type': quote['delivery_type'],
            'origin_city': quote.get('origin_city', ''),
            'destination': destination_str,
            'match_tier': quote['match_tier'],
            'total': total
        })
    return quotes_list

@app.get("/quotes/{quote_id}")
async def get_quote(quote_id: str):
    for quote in quotes:
        if quote['id'] == quote_id:
            calculation_result = quote['calculation_result']

            # Format the response
            destination_city = quote.get('destination_city', '')
            destination_suburb = quote.get('destination_suburb', '')
            destination_str = destination_city
            if destination_suburb:
                destination_str += f" ({destination_suburb})"

            response = {
                'id': quote['id'],
                'timestamp': quote['timestamp'],
                'delivery_type': quote['delivery_type'],
                'origin': get_location_by_id(quote['calculation_request'].get('origin_id', '')) or {},
                'destination': destination_str,
                'items': calculation_result.get('processed_items', []),
                'services': quote['calculation_request'].get('services', {}),
                'match_tier': calculation_result.get('match_tier', 'Unavailable')
            }

            if not calculation_result.get('unavailable', False):
                response.update({
                    'matched_rate_per_m3': calculation_result.get('matched_rate_per_m3'),
                    'volume_charged': calculation_result.get('volume_charged'),
                    'cost_breakdown': {
                        'base_delivery': calculation_result.get('base_delivery'),
                        'assembly_cost': calculation_result.get('assembly_cost'),
                        'rubbish_cost': calculation_result.get('rubbish_cost'),
                        'rural_cost': calculation_result.get('rural_cost'),
                        'total': calculation_result.get('total')
                    }
                })

            return response

    raise HTTPException(status_code=404, detail="Quote not found")

@app.delete("/quotes/{quote_id}")
async def delete_quote(quote_id: str):
    for i, quote in enumerate(quotes):
        if quote['id'] == quote_id:
            quotes.pop(i)
            return {"message": "Quote deleted successfully"}
    raise HTTPException(status_code=404, detail="Quote not found")

# Admin endpoints
@app.post("/reset")
async def reset_data():
    global settings, locations, rate_cards, furniture_catalog, quotes

    settings = {
        'rural_rate_per_km': 0.0,
        'assembly_rate_per_interval': 0.0,
        'rubbish_flat_rate': 0.0
    }
    locations.clear()
    rate_cards.clear()
    furniture_catalog.clear()
    quotes.clear()

    return {"message": "All data reset successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
