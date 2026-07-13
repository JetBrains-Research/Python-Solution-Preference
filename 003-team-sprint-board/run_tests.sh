pip install -r requirements.txt
python3 app.py > app.log 2>&1 &
APP_PID=$!
sleep 2
python3 test_api.py
RESULT=$?
kill $APP_PID
exit $RESULT
