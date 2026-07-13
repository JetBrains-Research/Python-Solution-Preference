# Furniture Delivery Pricing Calculator (MVP)

A deterministic HTTP API that produces furniture delivery quotes. No UI, no accounts, no payments.

## Running

    pip install -r requirements.txt
    python3 app.py

Server listens on port 5000.

## Endpoints

### Settings
- GET /settings
- PUT /settings  body: {ruralRatePerKm, assemblyRatePerInterval, rubbishFlatRate}

### Locations
- GET /locations
- POST /locations  body: {type, name, address, city, suburb}   (type in store/warehouse/supplier)
- GET /locations/{id}
- PUT /locations/{id}
- DELETE /locations/{id}

### Rate Cards
- GET /rate-cards
- POST /rate-cards  body: {serviceType, fromCity, toCity, toSuburb, ratePerM3}
- GET /rate-cards/{id}
- PUT /rate-cards/{id}
- DELETE /rate-cards/{id}

### Furniture Catalog
- GET /catalog
- POST /catalog  body: {sku, name, cubicMetres, category}
- GET /catalog/{id}
- PUT /catalog/{id}
- DELETE /catalog/{id}

### Quote calculation
- POST /quote/calculate  body:
  {
    deliveryType: B2B|B2C,
    originId,
    destinationId (B2B) or destinationCity + destinationSuburb (B2C),
    items: [{catalogId, quantity, cubicMetresOverride?} | {name, cubicMetres, quantity}],
    services: {assemblyIntervals, rubbishQuantity, ruralKm}
  }

### Quotes
- POST /quotes  (same body as calculate; saves an immutable snapshot)
- GET /quotes
- GET /quotes/{id}
- DELETE /quotes/{id}

### Admin
- POST /admin/reset
