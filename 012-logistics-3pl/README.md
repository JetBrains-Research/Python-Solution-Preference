# Apex Logistics 3PL Service (MVP)

Run: `python3 app.py` (port 5070)

Endpoints:
- GET /api/insights
- GET /api/insights/<slug>
- GET /api/roi/defaults
- POST /api/roi/step1 | /step2 | /step3
- POST /api/roi/calculate
- POST /api/contact
- POST /api/quote
- GET /api/admin/quotes (header: X-Admin-Password: apex-logistics-3421)
