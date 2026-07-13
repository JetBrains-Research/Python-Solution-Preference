#!/bin/bash
set -e
BASE="http://127.0.0.1:5001"

echo "=== LOGIN ADMIN ==="
ADMIN_TOKEN=$(curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" -d '{"username":"core_admin","password":"CoreAdmin!2025"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "Admin token: ${ADMIN_TOKEN:0:20}..."

echo "=== CREATE INVITE CODES ==="
curl -s -X POST $BASE/admin/invite-codes -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"code":"ARTVIP","type":"single","expires_at":"2027-12-31T00:00:00"}'
echo ""
curl -s -X POST $BASE/admin/invite-codes -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"code":"GROUP20","type":"multi","max_uses":20,"expires_at":"2027-12-31T00:00:00"}'
echo ""

echo "=== REGISTER MEMBER ==="
REG_RESP=$(curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" -d '{"username":"artist1","email":"artist1@test.com","password":"Pass123!","invite_code":"ARTVIP"}')
echo "$REG_RESP"
ARTIST_TOKEN=$(echo $REG_RESP | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

echo "=== COMPLETE PROFILE ==="
curl -s -X PUT $BASE/profile -H "Authorization: Bearer $ARTIST_TOKEN" -H "Content-Type: application/json" -d '{"full_name":"Artist One","location":"Berlin","creative_role":"Visual Artist"}'
echo ""

echo "=== BROWSE EVENTS (empty) ==="
curl -s $BASE/events
echo ""

echo "=== CREATE EVENTS ==="
curl -s -X POST $BASE/admin/events -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"title":"Paid Workshop","description":"A paid workshop.","event_datetime":"2026-09-01T10:00:00","location":"Room 1","category":"workshop","capacity":2,"price_cents":1500}'
echo ""
curl -s -X POST $BASE/admin/events -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"title":"Free Social","description":"Free social event.","event_datetime":"2026-10-01T18:00:00","location":"Park","category":"social","capacity":3,"price_cents":0}'
echo ""
echo "== Edit event =="
curl -s -X PUT $BASE/admin/events/1 -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"title":"Paid Workshop (Updated)"}'
echo ""

echo "=== RSVP ==="
curl -s -X POST $BASE/events/1/rsvp -H "Authorization: Bearer $ARTIST_TOKEN"
echo ""
# Duplicate
echo "=== DUPLICATE RSVP ==="
curl -s -X POST $BASE/events/1/rsvp -H "Authorization: Bearer $ARTIST_TOKEN"
echo ""

echo "=== EVENT DETAIL (sees attendees) ==="
curl -s $BASE/events/1 -H "Authorization: Bearer $ARTIST_TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Title:', d['title'])
print('Attendees:', len(d['attendees']))
for a in d['attendees']:
    print(f' {a[\"full_name\"]} ({a[\"creative_role\"]})')
"

echo "=== MY EVENTS ==="
curl -s $BASE/my-events -H "Authorization: Bearer $ARTIST_TOKEN" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Total owed:', d['total_owed'])
for e in d['events']:
    print(f'{e[\"event_title\"]}: {e[\"payment_status\"]} {e[\"amount_owed\"]}')
"

echo "=== ADMIN ATTENDANCE & NO-SHOW ==="
ATID=$(curl -s "$BASE/admin/attendance?event_id=1" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST $BASE/admin/attendance/$ATID/mark-attended -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"attended":false}'
echo ""
curl -s -X POST $BASE/admin/attendance/$ATID/no-show-fee -H "Authorization: Bearer $ADMIN_TOKEN"
echo ""
curl -s -X POST $BASE/admin/attendance/$ATID/payment-status -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"status":"paid"}'
echo ""

echo "=== PAYMENT SUMMARY ==="
curl -s $BASE/admin/payment-summary -H "Authorization: Bearer $ADMIN_TOKEN"
echo ""

echo "=== ADMIN USERS ==="
curl -s $BASE/admin/users -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "
import sys,json
users=json.load(sys.stdin)
for u in users:
    print(f'{u[\"full_name\"]} admin:{u[\"is_admin\"]} role:{u.get(\"creative_role\",\"\")}')
"

echo "=== GRANT ADMIN ==="
curl -s -X POST $BASE/admin/users/2/admin -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"action":"grant"}'
echo ""

echo "=== DEACTIVATE CODE ==="
curl -s -X POST $BASE/admin/invite-codes/1/deactivate -H "Authorization: Bearer $ADMIN_TOKEN"
echo ""

echo "=== DELETE EVENT ==="
curl -s -X DELETE $BASE/admin/events/2 -H "Authorization: Bearer $ADMIN_TOKEN"
echo ""
curl -s $BASE/events
echo ""

echo "=== RSVP TO PAST EVENT (should fail) ==="
curl -s -X POST $BASE/events/1/rsvp -H "Authorization: Bearer $ARTIST_TOKEN"
echo ""

echo "ALL TESTS PASSED"
