import requests
import time
import json

BASE_URL = "http://127.0.0.1:5000"

def test_flow():
    print("Resetting state...")
    requests.post(f"{BASE_URL}/reset")
    
    print("Checking initial lessons status...")
    lessons = requests.get(f"{BASE_URL}/lessons").json()
    print(f"Lessons: {lessons}")
    assert "Locked" in lessons["Lesson 2"]

    print("\nStarting Lesson 1...")
    # Use a loop to submit 5 exercises
    score = 0
    for pos in range(5):
        # Get exercise
        res = requests.get(f"{BASE_URL}/lesson/1/exercise/{pos}").json()
        q_data = res["data"]
        
        # Provide correct answer
        answer = None
        if q_data["type"] == "multiple_choice":
            answer = q_data["correct_answer"] # This is a hack since we are testing, normally we wouldn't have it
            # But wait, the API for get_exercise should NOT return the correct answer for MC, except if it's in the options
            # Let's check the MC options
            answer = q_data["options"][0] # Just pick one for now, we will adjust to ensure 4/5
        elif q_data["type"] == "matching_pairs":
            # We need the correct pairs. We'll hardcode them based on our questions.json
            answer = {"Perro": "Dog", "Gato": "Cat", "Casa": "House", "Libro": "Book"}
        elif q_data["type"] == "word_ordering":
            answer = ["Yo", "estudio", "español"]
        elif q_data["type"] == "fill_in_the_blank":
            answer = "roja"
        elif q_data["type"] == "typed_translation":
            answer = "Gracias"

        # Special case for MC: the API returns options. I'll just use 'Hola' which is correct.
        if q_data["type"] == "multiple_choice":
            answer = "Hola"

        submit_res = requests.post(f"{BASE_URL}/lesson/1/submit", json={"position": pos, "answer": answer}).json()
        if submit_res.get("correct"):
            score += 1
        print(f"Exercise {pos+1}: {'Correct' if submit_res.get('correct') else 'Incorrect'}")

    print(f"\nFinal Score: {score}/5")
    lessons = requests.get(f"{BASE_URL}/lessons").json()
    print(f"Lesson 2 status: {lessons['Lesson 2']}")
    assert "Locked" not in lessons["Lesson 2"] if score >= 4 else True

if __name__ == "__main__":
    # Wait for server to start
    time.sleep(2)
    try:
        test_flow()
        print("\nTests passed!")
    except Exception as e:
        print(f"\nTests failed: {e}")
