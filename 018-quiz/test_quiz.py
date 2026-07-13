import requests
import json

BASE_URL = "http://127.0.0.1:5001"

def test_quiz():
    # 1. List Categories
    print("Testing /categories...")
    resp = requests.get(f"{BASE_URL}/categories")
    categories = resp.json().get("categories")
    print(f"Categories: {categories}")
    assert "Surprise Me!" in categories

    # 2. Start Game - Surprise Me!
    print("\nTesting /start with Surprise Me!...")
    resp = requests.post(f"{BASE_URL}/start", json={"category": "Surprise Me!"})
    data = resp.json()
    session_id = data["session_id"]
    category = data["category"]
    print(f"Started game in category: {category}")
    
    # 3. Answer questions
    current_q = data["first_question"]
    total_q = data["total_questions"]
    
    # We'll answer everything correctly to test achievements
    # We need the correct option from the CSV for each question in the session.
    # Since we don't have the CSV in the test script, we'll just use the answer 
    # returned by the server in a smart way or just simulate.
    # Actually, since the mock CSV I made has mostly 'A' as correct, I'll try 'A'.
    
    for i in range(total_q):
        print(f"Answering Question {i+1}...")
        # For simplicity in this test, we'll justsubmit 'A' and then 'B' etc.
        # But since we want to test achievements, let's just observe the feedback.
        # To actually get achievements, we need to know the correct answer.
        # The server returns the correct answer after submission.
        # Let's just use 'A' for now as I set most to 'A' in my CSV.
        resp = requests.post(f"{BASE_URL}/answer", json={
            "session_id": session_id,
            "answer": "A" 
        })
        res_data = resp.json()
        print(f"Feedback: {res_data['feedback']}")
        
        if res_data.get("game_over"):
            print("\nGame Over!")
            print(f"Results: {res_data['results']}")
            break
        else:
            current_q = res_data["next_question"]

    # 4. Test Category with warning
    print("\nTesting /start with Math (small category)...")
    resp = requests.post(f"{BASE_URL}/start", json={"category": "Math"})
    data = resp.json()
    print(f"Warning: {data.get('warning')}")
    assert data.get('warning') == "Not enough questions in this category for all accomplishments"

if __name__ == "__main__":
    test_quiz()
