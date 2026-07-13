#!/bin/bash
set -e
BASE="http://localhost:5001"

# 1. Invalid login
echo "=== Invalid login ==="
curl -s -X POST "$BASE/login" -H "Content-Type: application/json" -d '{"username":"alice","password":"wrong"}' && echo ""

# 2. Login as alice
echo "=== Login as alice ==="
ALICE=$(curl -s -X POST "$BASE/login" -H "Content-Type: application/json" -d '{"username":"alice","password":"password-alice"}')
ALICE_TOKEN=$(echo "$ALICE" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "Alice token: $ALICE_TOKEN"

# 3. Login as bob
echo "=== Login as bob ==="
BOB=$(curl -s -X POST "$BASE/login" -H "Content-Type: application/json" -d '{"username":"bob","password":"password-bob"}')
BOB_TOKEN=$(echo "$BOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "Bob token: $BOB_TOKEN"

# 4. Unauthorized access
echo "=== Unauthorized ==="
curl -s "$BASE/channels/general/messages"

# 5. Post to #general as alice
echo "=== Post to #general as alice ==="
curl -s -X POST "$BASE/channels/general/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"text":"Hello everyone!"}'

# 6. Post to #general as bob
echo "=== Post to #general as bob ==="
curl -s -X POST "$BASE/channels/general/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $BOB_TOKEN" -d '{"text":"Hi Alice."}'

# 7. Get #general messages (should be oldest first)
echo "=== Get #general messages ==="
curl -s "$BASE/channels/general/messages" -H "Authorization: Bearer $ALICE_TOKEN"

# 8. User search
echo "=== User search 'bo' ==="
curl -s -X POST "$BASE/users/search" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"query":"bo"}'

# 9. User search case-insensitive
echo "=== User search 'LEE' ==="
curl -s -X POST "$BASE/users/search" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"query":"LEE"}'

# 10. User search excludes self
echo "=== User search 'alice' (should exclude self) ==="
curl -s -X POST "$BASE/users/search" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"query":"alice"}'

# 11. DM from alice to bob
echo "=== DM alice->bob ==="
curl -s -X POST "$BASE/dms/bob/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"text":"Hey Bob, private message!"}'

# 12. DM from bob to alice (same thread)
echo "=== DM bob->alice ==="
curl -s -X POST "$BASE/dms/alice/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $BOB_TOKEN" -d '{"text":"Got it, Alice."}'

# 13. Get DM thread from alice perspective
echo "=== Get DM alice views bob ==="
curl -s "$BASE/dms/bob/messages" -H "Authorization: Bearer $ALICE_TOKEN"

# 14. DM to self (should fail)
echo "=== DM to self ==="
curl -s -X POST "$BASE/dms/alice/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"text":"self"}'

# 15. Empty message (should fail)
echo "=== Empty message ==="
curl -s -X POST "$BASE/channels/general/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"text":"   "}'

# 16. Whitespace-only message (should fail)
echo "=== Whitespace-only ==="
curl -s -X POST "$BASE/channels/general/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"text":"     "}'

# 17. DM to nonexistent user (should fail)
echo "=== DM to unknown user ==="
curl -s -X POST "$BASE/dms/zebra/messages" -H "Content-Type: application/json" -H "Authorization: Bearer $ALICE_TOKEN" -d '{"text":"hello"}'

# 18. Conversations list
echo "=== Conversations for alice ==="
curl -s "$BASE/conversations" -H "Authorization: Bearer $ALICE_TOKEN"

# 19. Conversations for bob (should not have DMs with carol)
echo "=== Conversations for bob ==="
curl -s "$BASE/conversations" -H "Authorization: Bearer $BOB_TOKEN"

# 20. Search general and own DMs
echo "=== Search alice 'hello' ==="
curl -s "$BASE/search?q=hello" -H "Authorization: Bearer $ALICE_TOKEN"

# 21. Search case-insensitive
echo "=== Search alice 'EVERYONE' ==="
curl -s "$BASE/search?q=EVERYONE" -H "Authorization: Bearer $ALICE_TOKEN"

# 22. Bob search should not see alice DM with carol (does not exist, but verify)
echo "=== Search bob 'private' ==="
curl -s "$BASE/search?q=private" -H "Authorization: Bearer $BOB_TOKEN"

# 23. Logout
echo "=== Logout alice ==="
curl -s -X POST "$BASE/logout" -H "Authorization: Bearer $ALICE_TOKEN"
echo ""
echo "=== Verify logout ==="
curl -s "$BASE/channels/general/messages" -H "Authorization: Bearer $ALICE_TOKEN"
echo "DONE"
