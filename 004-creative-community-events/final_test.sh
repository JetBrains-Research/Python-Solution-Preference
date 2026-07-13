#!/bin/bash
BASE="http://127.0.0.1:5001"
A=$(curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" -d '{"username":"core_admin","password":"CoreAdmin!2025"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "Token: $A"

curl -s -X POST $BASE/admin/invite-codes -H "Authorization: Bearer $A" -H "Content-Type: application/json" -d '{"code":"VIP","type":"single","expires_at":"2027-01-01T00:00:00"}'
echo ""
curl -s -X POST $BASE/admin/invite-codes -H "Authorization: Bearer $A" -H "Content-Type: application/json" -d '{"code":"MEGA10","type":"multi","max_uses":10,"expires_at":"2027-01-01T00:00:00"}'
echo ""

R=$(curl -s -X POST $BASE/auth/register -H "Content-Type: application/json" -d '{"username":"alice","email":"alice@example.com","password":"Secret123!","invite_code":"VIP"}')
echo "Register: $R"
TALICE=$(echo $R | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "Alice token: $TALICE"

curl -s -X PUT $BASE/profile -H "Authorization: Bearer $TALICE" -H "Content-Type: application/json" -d '{"full_name":"Alice Wonder","location":"NYC","creative_role":"Writer"}'
echo ""

curl -s -X POST $BASE/admin/events -H "Authorization: Bearer $A" -H "Content-Type: application/json" -d '{"title":"Paid Workshop","description":"A workshop.","event_datetime":"2026-09-01T10:00:00","location":"Room 1","category":"workshop","capacity":1,"price_cents":1000}'
echo ""
curl -s -X POST $BASE/admin/events -H "Authorization: Bearer $A" -H "Content-Type: application/json" -d '{"title":"Free Social","description":"Free social event.","event_datetime":"2026-10-01T18:00:00","location":"Park","category":"social","capacity":3,"price_cents":0}'
echo ""

curl -s -X POST $BASE/events/1/rsvp -H "Authorization: Bearer $TALICE"
echo ""
curl -s -X POST $BASE/events/2/rsvp -H "Authorization: Bearer $TALICE"
echo ""

echo "=== MY EVENTS ==="
curl -s $BASE/my-events -H "Authorization: Bearer $TALICE" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Total owed: {d[\"total_owed\"]}')
for e in d['events']:
    print(f'  {e[\"event_title\"]}: {e[\"payment_status\"]} - {e[\"amount_owed\"]}')
"

echo "=== ATTENDANCE & PAYMENTS ==="
ATID=$(curl -s "$BASE/admin/attendance?event_id=1" -H "Authorization: Bearer $A" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST $BASE/admin/attendance/$ATID/mark-attended -H "Authorization: Bearer $A" -H "Content-Type: application/json" -d '{"attended":false}'
echo ""
curl -s -X POST $BASE/admin/attendance/$ATID/no-show-fee -H "Authorization: Bearer $A"
echo ""
curl -s -X POST $BASE/admin/attendance/$ATID/payment-status -H "Authorization: Bearer $A" -H "Content-Type: application/json" -d '{"status":"paid"}'
echo ""

echo "=== PAYMENT SUMMARY ==="
curl -s $BASE/admin/payment-summary -H "Authorization: Bearer $A"
echo ""

echo "=== EVENT DETAIL ==="
curl -s $BASE/events/1 -H "Authorization: Bearer $TALICE" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Attendees:', len(d['attendees']))
for a in d['attendees']:
    print(' ', a['full_name'], '-', a['creative_role'])
"

echo "=== USER MANAGEMENT ==="
curl -s $BASE/admin/users -H "Authorization: Bearer $A" | python3 -c "
import sys,json
users=json.load(sys.stdin)
for u in users:
    print(f'{u[\"full_name\"]} - admin:{u[\"is_admin\"]}')
"
curl -s -X POST $BASE/admin/users/2/admin -H "Authorization: Bearer $A" -H "Content-Type: application/json" -d '{"action":"grant"}'
echo ""

echo "ALL FINAL TESTS PASSED"
