import json
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

DATA_FILE = "resume_data.json"
PASSWORD = "resume-editor-2025"

MAX_HEADLINE = 100
MAX_SUMMARY = 500
MAX_EXP_TITLE = 100
MAX_EXP_DATE = 100
MAX_EXP_DESC = 1000
MAX_EDU_SCHOOL = 100
MAX_EDU_PROGRAM = 100
MAX_EDU_DATE = 100
MAX_SKILL = 50


def load_resume():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return None


def save_resume(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def trim(val):
    if val is None:
        return ""
    return str(val).strip()


@app.route("/resume", methods=["GET"])
def get_resume():
    resume = load_resume()
    if resume is None:
        return jsonify({"message": "Resume not set up yet."}), 200

    def section_value(key, message, transform=None):
        val = resume.get(key, [])
        if isinstance(val, str):
            val = val.strip()
        if val == "" or (isinstance(val, list) and len(val) == 0):
            return {"message": message}
        return {"value": val if transform is None else transform(val)}

    result = {
        "headline": section_value("headline", "No headline added yet."),
        "summary": section_value("summary", "No summary added yet."),
        "experience": section_value("experience", "No experience added yet."),
        "education": section_value("education", "No education added yet."),
        "skills": section_value("skills", "No skills added yet."),
    }
    return jsonify(result), 200


@app.route("/resume", methods=["POST", "PUT"])
def save_endpoint():
    pw = request.headers.get("X-Resume-Password")
    if pw is None:
        return jsonify({"error": "Password is required."}), 403
    if pw != PASSWORD:
        return jsonify({"error": "Invalid password."}), 403

    payload = request.get_json(force=True, silent=True) or {}
    errors = {}

    headline = trim(payload.get("headline"))
    if headline == "":
        errors["headline"] = "Headline is required."
    elif len(headline) > MAX_HEADLINE:
        errors["headline"] = f"Headline must be at most {MAX_HEADLINE} characters."

    summary = trim(payload.get("summary", ""))
    if len(summary) > MAX_SUMMARY:
        errors["summary"] = f"Summary must be at most {MAX_SUMMARY} characters."

    # Experience
    experience = []
    exp_input = payload.get("experience", [])
    if not isinstance(exp_input, list):
        errors["experience"] = "Experience must be a list."
    else:
        exp_errors = []
        for entry in exp_input:
            ee = {}
            title = trim(entry.get("title"))
            dr = trim(entry.get("date_range"))
            desc = trim(entry.get("description"))
            if title == "":
                ee["title"] = "Title is required."
            elif len(title) > MAX_EXP_TITLE:
                ee["title"] = f"Title must be at most {MAX_EXP_TITLE} characters."
            if dr == "":
                ee["date_range"] = "Date range is required."
            elif len(dr) > MAX_EXP_DATE:
                ee["date_range"] = f"Date range must be at most {MAX_EXP_DATE} characters."
            if desc == "":
                ee["description"] = "Description is required."
            elif len(desc) > MAX_EXP_DESC:
                ee["description"] = f"Description must be at most {MAX_EXP_DESC} characters."
            exp_errors.append(ee if ee else None)
            if not ee:
                experience.append({"title": title, "date_range": dr, "description": desc})
        if any(e is not None for e in exp_errors):
            errors["experience"] = [e for e in exp_errors if e is not None]

    # Education
    education = []
    edu_input = payload.get("education", [])
    if not isinstance(edu_input, list):
        errors["education"] = "Education must be a list."
    else:
        edu_errors = []
        for entry in edu_input:
            ee = {}
            school = trim(entry.get("school_name"))
            program = trim(entry.get("program"))
            dr = trim(entry.get("date_range"))
            if school == "":
                ee["school_name"] = "School name is required."
            elif len(school) > MAX_EDU_SCHOOL:
                ee["school_name"] = f"School name must be at most {MAX_EDU_SCHOOL} characters."
            if program == "":
                ee["program"] = "Program is required."
            elif len(program) > MAX_EDU_PROGRAM:
                ee["program"] = f"Program must be at most {MAX_EDU_PROGRAM} characters."
            if dr == "":
                ee["date_range"] = "Date range is required."
            elif len(dr) > MAX_EDU_DATE:
                ee["date_range"] = f"Date range must be at most {MAX_EDU_DATE} characters."
            edu_errors.append(ee if ee else None)
            if not ee:
                education.append({"school_name": school, "program": program, "date_range": dr})
        if any(e is not None for e in edu_errors):
            errors["education"] = [e for e in edu_errors if e is not None]

    # Skills
    skills_final = []
    skills_input = payload.get("skills", [])
    if not isinstance(skills_input, list):
        errors["skills"] = "Skills must be a list."
    else:
        skill_err = None
        for s in skills_input:
            t = trim(s)
            if t == "":
                continue
            if len(t) > MAX_SKILL:
                skill_err = f"Each skill must be at most {MAX_SKILL} characters."
                break
            if any(existing.lower() == t.lower() for existing in skills_final):
                skill_err = "Skill already added."
                break
            skills_final.append(t)
        if skill_err:
            errors["skills"] = skill_err

    if errors:
        return jsonify({"errors": errors}), 400

    stored = {
        "headline": headline,
        "summary": summary,
        "experience": experience,
        "education": education,
        "skills": skills_final,
    }
    save_resume(stored)
    return jsonify({"message": "Resume saved successfully."}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
