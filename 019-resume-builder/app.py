from flask import Flask, request, jsonify
import re

app = Flask(__name__)

# In-memory store
resume_data = None  # will become dict after first save
is_set_up = False

PASSWORD = "resume-editor-2025"

def trim_str(s):
    if isinstance(s, str):
        return s.strip()
    return s

def validate_section(data, fields_config, section_name):
    if not isinstance(data, list):
        return {"_error": f"{section_name} must be a list."}
    errors = []
    for entry_idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            errors.append({"index": entry_idx, "errors": {"_error": "Each entry must be a JSON object."}})
            continue
        entry_errors = {}
        for field, required, max_len in fields_config:
            val = trim_str(entry.get(field, ""))
            if required and not val:
                entry_errors[field] = f"{field.capitalize()} is required."
            elif max_len and len(val) > max_len:
                entry_errors[field] = f"{field.capitalize()} exceeds max length of {max_len}."
        if entry_errors:
            errors.append({"index": entry_idx, "errors": entry_errors})
    return errors

def validate_skills(skills):
    if not isinstance(skills, list):
        return "_error", "Skills must be a list."
    errors = []
    seen = set()
    for idx, skill in enumerate(skills):
        if not isinstance(skill, str):
            errors.append({"index": idx, "error": "Skill must be a string."})
            continue
        skill = trim_str(skill)
        if not skill:
            errors.append({"index": idx, "error": "Skill label cannot be empty."})
            continue
        if len(skill) > 50:
            errors.append({"index": idx, "error": f"Skill exceeds max length of 50 characters."})
            continue
        lower = skill.lower()
        if lower in seen:
            errors.append({"index": idx, "error": "Skill already added."})
        else:
            seen.add(lower)
    return errors

def validate_resume(data):
    errors = {}
    # Headline
    headline = trim_str(data.get("headline", ""))
    if not headline:
        errors["headline"] = "Headline is required."
    elif len(headline) > 100:
        errors["headline"] = "Headline exceeds max length of 100 characters."
    # Summary (optional)
    summary = trim_str(data.get("summary", ""))
    if summary and len(summary) > 500:
        errors["summary"] = "Summary exceeds max length of 500 characters."
    # Experience
    experience = data.get("experience", [])
    exp_errors = validate_section(experience, [
        ("title", True, 100),
        ("date_range", True, 100),
        ("description", True, 1000)
    ], "Experience")
    if exp_errors:
        if isinstance(exp_errors, dict):
            errors["experience"] = exp_errors["_error"]
        else:
            errors["experience"] = exp_errors
    # Education
    education = data.get("education", [])
    edu_errors = validate_section(education, [
        ("school_name", True, 100),
        ("program", True, 100),
        ("date_range", True, 100)
    ], "Education")
    if edu_errors:
        if isinstance(edu_errors, dict):
            errors["education"] = edu_errors["_error"]
        else:
            errors["education"] = edu_errors
    # Skills
    skills = data.get("skills", [])
    skill_errors = validate_skills(skills)
    if isinstance(skill_errors, tuple):
        _, msg = skill_errors
        errors["skills"] = msg
    elif skill_errors:
        errors["skills"] = skill_errors
    return errors

@app.route('/resume', methods=['GET'])
def get_resume():
    if not is_set_up:
        return jsonify({"message": "Resume not set up yet."}), 200
    response = {
        "headline": resume_data.get("headline"),
        "summary": resume_data.get("summary") or "No summary added yet.",
        "experience": resume_data.get("experience") or "No experience added yet.",
        "education": resume_data.get("education") or "No education added yet.",
        "skills": resume_data.get("skills") or "No skills added yet."
    }
    return jsonify(response)

@app.route('/resume', methods=['PUT'])
def save_resume():
    global resume_data, is_set_up
    # Password check
    password = request.headers.get("X-Password")
    if not password:
        return jsonify({"error": "Password is required."}), 401
    if password != PASSWORD:
        return jsonify({"error": "Wrong password."}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON."}), 400

    validation_errors = validate_resume(data)
    if validation_errors:
        return jsonify({"errors": validation_errors}), 400

    # Trim and store
    trimmed = {}
    trimmed["headline"] = trim_str(data["headline"])
    trimmed["summary"] = trim_str(data.get("summary", ""))
    # Experience
    trimmed["experience"] = []
    for entry in data.get("experience", []):
        trimmed["experience"].append({
            "title": trim_str(entry["title"]),
            "date_range": trim_str(entry["date_range"]),
            "description": trim_str(entry["description"])
        })
    # Education
    trimmed["education"] = []
    for entry in data.get("education", []):
        trimmed["education"].append({
            "school_name": trim_str(entry["school_name"]),
            "program": trim_str(entry["program"]),
            "date_range": trim_str(entry["date_range"])
        })
    # Skills
    trimmed["skills"] = [trim_str(s) for s in data.get("skills", [])]

    resume_data = trimmed
    is_set_up = True
    return jsonify({"message": "Resume saved successfully."})

if __name__ == '__main__':
    app.run(debug=True, port=5555)
