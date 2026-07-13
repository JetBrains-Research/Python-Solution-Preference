#!/bin/bash
BASE="http://127.0.0.1:5001"

# 1. Health and default admin login
echo "=== LOGIN DEFAULT ADMIN ==="
curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d '{"username":"core_admin","password":"CoreAdmin!2025"}'
echo ""

# 2. Create invite codes
echo "=== CREATE INVITE CODES ==="
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d '{"username":"core_admin","password":"CoreAdmin!2025"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "Token: $TOKEN"
# Create a single-use code
curl -s -X POST "$BASE/admin/invite-codes" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"code":"TEST1","type":"single","expires_at":"2026-12-31T00:00:00","description":"Single use"}'
echo ""
# Create a multi-use code
curl -s -X POST "$BASE/admin/invite-codes" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"code":"MULTI10","type":"multi","max_uses":10,"expires_at":"2026-12-31T00:00:00","description":"Multi use"}'
echo ""

# 3. Register a member
echo "=== REGISTER MEMBER ==="
curl -s -X POST "$BASE/auth/register" -H "Content-Type: application/json" -d '{"username":"artgal","email":"artgal@example.com","password":"Password123","invite_code":"TEST1"}'
echo ""

# 4. Try to use same code again (should fail)
echo "=== REGISTER WITH SAME CODE (FAIL) ==="
curl -s -X POST "$BASE/auth/register" -H "Content-Type: application/json" -d '{"username":"another","email":"another@example.com","password":"Password123","invite_code":"TEST1"}'
echo ""

# 5. Login as artgal
echo "=== LOGIN ARTGAL ==="
curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d '{"username":"artgal","password":"Password123"}'
echo ""

TOKEN_ARTGAL=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d '{"username":"artgal","password":"Password123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "Token artgal: $TOKEN_ARTGAL"

# 6. Try RSVP before profile complete (should fail)
echo "=== RSVP BEFORE PROFILE COMPLETE ==="
curl -s -X POST "$BASE/events/1/rsvp" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN_ARTGAL"
echo ""

# 7. Complete profile
echo "=== COMPLETE PROFILE ==="
curl -s -X PUT "$BASE/profile" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN_ARTGAL" -d '{"full_name":"Art Gal","location":"NYC","creative_role":"Photographer","bio":"Loves art"}'
echo ""

# 8. Admin creates an event
echo "=== CREATE EVENT ==="
curl -s -X POST "$BASE/admin/events" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"title":"Photo Workshop","description":"A great workshop on photography basics.","event_datetime":"2026-06-15T10:00:00","location":"Studio 42","category":"workshop","capacity":2,"price_cents":2500}'
echo ""

# 9. List events (public)
echo "=== LIST EVENTS ==="
curl -s "$BASE/events"
echo ""

# 10. RSVP to event 1 (artgal)
echo "=== RSVP ARTGAL ==="
curl -s -X POST "$BASE/events/1/rsvp" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN_ARTGAL"
echo ""

# 11. RSVP again (should fail)
echo "=== RSVP AGAIN (FAIL) ==="
curl -s -X POST "$BASE/events/1/rsvp" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN_ARTGAL"
echo ""

# 12. Event detail (artgal should see attendee list)
echo "=== EVENT DETAIL (ARTGAL) ==="
curl -s "$BASE/events/1" -H "Authorization: Bearer $TOKEN_ARTGAL"
echo ""

# 13. My Events
echo "=== MY EVENTS ==="
curl -s "$BASE/my-events" -H "Authorization: Bearer $TOKEN_ARTGAL"
echo ""

# 14. Admin attendance
echo "=== ADMIN ATTENDANCE ==="
curl -s "$BASE/admin/attendance" -H "Authorization: Bearer $TOKEN"
echo ""

# 15. Apply no-show fee
ATID=$(curl -s "$BASE/admin/attendance" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
echo "Attendance ID: $ATID"
echo "=== APPLY NO-SHOW FEE ==="
curl -s -X POST "$BASE/admin/attendance/$ATID/no-show-fee" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN"
echo ""

# 16. Mark paid
echo "=== MARK PAID ==="
curl -s -X POST "$BASE/admin/attendance/$ATID/payment-status" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"status":"paid"}'
echo ""

# 17. Payment summary
echo "=== PAYMENT SUMMARY ==="
curl -s "$BASE/admin/payment-summary" -H "Authorization: Bearer $TOKEN"
echo ""

# 18. List users
echo "=== LIST USERS ==="
curl -s "$BASE/admin/users" -H "Authorization: Bearer $TOKEN"
echo ""

# 19. Register new member with multi-use code
echo "=== REGISTER MEMBER WITH MULTI ==="
curl -s -X POST "$BASE/auth/register" -H "Content-Type: application/json" -d '{"username":"writer1","email":"writer1@example.com","password":"Password123","invite_code":"MULTI10"}'
echo ""

# 20. Edge: free event
echo "=== CREATE FREE EVENT ==="
curl -s -X POST "$BASE/admin/events" -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"title":"Free Networking","description":"Free event for all.","event_datetime":"2026-07-01T18:00:00","location":"Lobby","category":"networking","capacity":5,"price_cents":0}'
echo ""

echo "=== EVENT DETAIL FREE (before RSVP) ==="
curl -s "$BASE/events/2"
echo ""

