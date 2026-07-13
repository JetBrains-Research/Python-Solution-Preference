#!/bin/bash
BASE="http://127.0.0.1:5001"

# Login as admin
TOKEN=$(curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" -d '{"username":"core_admin","password":"CoreAdmin!2025"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# Create codes
echo "1. Create invite codes"
curl -s -X POST $BASE/admin/invite-codes -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"code":"SINGLE1","type":"single","expires_at":"2026-12-31T00:00:00"}'
echo ""
curl -s -X POST $BASE/admin/invite-codes -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"code":"MULTI5","type":"multi","max_uses":5,"expires_at":"2026-12-31T00:00:00"}'
echo ""

# Register member
echo "2. Register member with SINGLE1"
curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" -d '{"username":"artist","email":"artist@test.com","password":"Pass123!","invite_code":"SINGLE1"}'
echo ""

# Reuse code (should fail)
echo "3. Reuse exhausted code (should fail)"
curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" -d '{"username":"artist2","email":"artist2@test.com","password":"Pass123!","invite_code":"SINGLE1"}'
echo ""

# Login artist
TOKEN_ART=$(curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" -d '{"username":"artist","password":"Pass123!"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# Complete profile
echo "4. Complete profile"
curl -s -X PUT $BASE/profile -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN_ART" -d '{"full_name":"Artist One","location":"Paris","creative_role":"Photographer"}'
echo ""

# Create events
echo "5. Create events"
curl -s -X POST $BASE/admin/events -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"title":"Photo Workshop","description":"Learn photography basics in this hands-on session.","event_datetime":"2026-08-15T10:00:00","location":"Studio A","category":"workshop","capacity":2,"price_cents":2500}'
echo ""
curl -s -X POST $BASE/admin/events -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"title":"Free Mixer","description":"Free networking event.","event_datetime":"2025-06-15T18:00:00","location":"Lounge","category":"networking","capacity":5,"price_cents":0}'
echo ""

# List events
echo "6. List events"
curl -s $BASE/events | python3 -c "import sys,json; events=json.load(sys.stdin); print(f'Count: {len(events)}'); [print(f'  {e[\"title\"]} - {e[\"price\"]} - {e[\"capacity_display\"]}') for e in events]"

# RSVP to Photo Workshop (should succeed)
echo "7. RSVP to event 1"
curl -s -X POST $BASE/events/1/rsvp -H "Authorization: Bearer $TOKEN_ART" -H "Content-Type: application/json"
echo ""

# RSVP again (should fail)
echo "8. Duplicate RSVP (should fail)"
curl -s -X POST $BASE/events/1/rsvp -H "Authorization: Bearer $TOKEN_ART" -H "Content-Type: application/json"
echo ""

# Free event detail (past, should show message)
echo "9. Past event detail"
curl -s $BASE/events/2 | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message','no message'))"

# My events
echo "10. My Events"
curl -s $BASE/my-events -H "Authorization: Bearer $TOKEN_ART" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Total events: {len(d[\"events\"])}, Total owed: {d[\"total_owed\"]}'); [print(f'  {e[\"event_title\"]} - {e[\"payment_status\"]}') for e in d['events']]"

# Admin attendance
echo "11. Admin attendance mark + no-show + payment"
ATID=$(curl -s $BASE/admin/attendance -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST $BASE/admin/attendance/$ATID/mark-attended -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"attended":false}'
echo ""
curl -s -X POST $BASE/admin/attendance/$ATID/no-show-fee -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN"
echo ""
curl -s -X POST $BASE/admin/attendance/$ATID/payment-status -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"status":"paid"}'
echo ""

# Payment summary
echo "12. Payment summary"
curl -s $BASE/admin/payment-summary -H "Authorization: Bearer $TOKEN"
echo ""

# User list
echo "13. User list"
curl -s $BASE/admin/users -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; users=json.load(sys.stdin); [print(f'  {u[\"full_name\"]} - admin:{u[\"is_admin\"]}') for u in users]"

# Grant admin
echo "14. Grant admin to artist"
curl -s -X POST $BASE/admin/users/2/admin -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"action":"grant"}'
echo ""

# Delete user
echo "15. Create and delete user"
curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" -d '{"username":"todelete","email":"del@test.com","password":"Pass123!","invite_code":"MULTI5"}'
echo ""
curl -s -X DELETE $BASE/admin/users/3 -H "Authorization: Bearer $TOKEN"
echo ""

# Deactivate and delete code
echo "16. Deactivate and delete code"
curl -s -X POST $BASE/admin/invite-codes/2/deactivate -H "Authorization: Bearer $TOKEN"
echo ""
curl -s -X DELETE $BASE/admin/invite-codes/2 -H "Authorization: Bearer $TOKEN"
echo ""

echo "ALL TESTS DONE"
