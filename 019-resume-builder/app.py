from flask import Flask, request, jsonify
from threading import Lock

app = Flask(__name__)

PASSWORD = "resume-editor-2025"

state = {
    "initialized": False,
    "headline": "",
    "summary": "",
    "experience": [],   # list of dicts with id, title, date_range, description
    "education": [],    # list of dicts with id, school, program, date_range
    "skills": [],       # list of strings
    "_next_exp_id": 1,
    "_next_edu_id": 1,
}
lock = Lock()


def check_password():
    pw = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        pw = data.get("password")
    if pw is None:
        pw = request.headers.get("X-Password")
    if pw is None:
        pw = request.args.get("password")
    if pw is None or pw == "":
        return False, ("Password required.", 401)
    if pw != PASSWORD:
        return False, ("Incorrect password.", 403)
    return True, None


def trim(v):
    if v is None:
        return ""
    if not isinstance(v, str):
        return None
    return v.strip()


def validate_required_text(value, field, max_len, errors, required=True):
    if value is None or not isinstance(value, str):
        # But we've already trimmed - trim returns None for non-str
        errors.append(f"{field} must be a string.")
        return None
    v = value.strip()
    if required and v == "":
        errors.append(f"{field} is required.")
        return None
    if len(v) > max_len:
        errors.append(f"{field} exceeds maximum length of {max_len}.")
        return None
    return v


@app.route("/resume", methods=["GET"])
def get_resume():
    with lock:
        if not state["initialized"]:
            return jsonify({"message": "Resume not set up yet."}), 200

        result = {}
        # Headline
        result["headline"] = state["headline"] if state["headline"] else "No headline added yet."
        # Summary
        result["summary"] = state["summary"] if state["summary"] else "No summary added yet."
        # Experience
        if state["experience"]:
            result["experience"] = [
                {"id": e["id"], "title": e["title"], "date_range": e["date_range"], "description": e["description"]}
                for e in state["experience"]
            ]
        else:
            result["experience"] = "No experience added yet."
        # Education
        if state["education"]:
            result["education"] = [
                {"id": e["id"], "school": e["school"], "program": e["program"], "date_range": e["date_range"]}
                for e in state["education"]
            ]
        else:
            result["education"] = "No education added yet."
        # Skills
        if state["skills"]:
            result["skills"] = list(state["skills"])
        else:
            result["skills"] = "No skills added yet."

        return jsonify(result), 200


@app.route("/resume", methods=["PUT"])
def save_resume():
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code

    data = request.get_json(silent=True) or {}
    errors = []

    # Headline required
    headline_raw = data.get("headline", "")
    if not isinstance(headline_raw, str):
        errors.append("Headline must be a string.")
        headline = ""
    else:
        headline = headline_raw.strip()
        if headline == "":
            errors.append("Headline is required.")
        elif len(headline) > 100:
            errors.append("Headline exceeds maximum length of 100.")

    # Summary optional
    summary_raw = data.get("summary", "")
    summary = ""
    if summary_raw is None:
        summary = ""
    elif not isinstance(summary_raw, str):
        errors.append("Summary must be a string.")
    else:
        summary = summary_raw.strip()
        if len(summary) > 500:
            errors.append("Summary exceeds maximum length of 500.")

    # Experience list
    experience_in = data.get("experience", [])
    experience_out = []
    if not isinstance(experience_in, list):
        errors.append("Experience must be a list.")
    else:
        for idx, entry in enumerate(experience_in):
            if not isinstance(entry, dict):
                errors.append(f"Experience[{idx}] must be an object.")
                continue
            t = entry.get("title", "")
            d = entry.get("date_range", "")
            desc = entry.get("description", "")
            entry_errs = []
            if not isinstance(t, str):
                entry_errs.append(f"Experience[{idx}].title must be a string.")
                t = ""
            else:
                t = t.strip()
                if t == "":
                    entry_errs.append(f"Experience[{idx}].title is required.")
                elif len(t) > 100:
                    entry_errs.append(f"Experience[{idx}].title exceeds maximum length of 100.")
            if not isinstance(d, str):
                entry_errs.append(f"Experience[{idx}].date_range must be a string.")
                d = ""
            else:
                d = d.strip()
                if d == "":
                    entry_errs.append(f"Experience[{idx}].date_range is required.")
                elif len(d) > 100:
                    entry_errs.append(f"Experience[{idx}].date_range exceeds maximum length of 100.")
            if not isinstance(desc, str):
                entry_errs.append(f"Experience[{idx}].description must be a string.")
                desc = ""
            else:
                desc = desc.strip()
                if desc == "":
                    entry_errs.append(f"Experience[{idx}].description is required.")
                elif len(desc) > 1000:
                    entry_errs.append(f"Experience[{idx}].description exceeds maximum length of 1000.")
            if entry_errs:
                errors.extend(entry_errs)
            else:
                experience_out.append({"title": t, "date_range": d, "description": desc})

    # Education list
    education_in = data.get("education", [])
    education_out = []
    if not isinstance(education_in, list):
        errors.append("Education must be a list.")
    else:
        for idx, entry in enumerate(education_in):
            if not isinstance(entry, dict):
                errors.append(f"Education[{idx}] must be an object.")
                continue
            s = entry.get("school", "")
            p = entry.get("program", "")
            d = entry.get("date_range", "")
            entry_errs = []
            if not isinstance(s, str):
                entry_errs.append(f"Education[{idx}].school must be a string.")
                s = ""
            else:
                s = s.strip()
                if s == "":
                    entry_errs.append(f"Education[{idx}].school is required.")
                elif len(s) > 100:
                    entry_errs.append(f"Education[{idx}].school exceeds maximum length of 100.")
            if not isinstance(p, str):
                entry_errs.append(f"Education[{idx}].program must be a string.")
                p = ""
            else:
                p = p.strip()
                if p == "":
                    entry_errs.append(f"Education[{idx}].program is required.")
                elif len(p) > 100:
                    entry_errs.append(f"Education[{idx}].program exceeds maximum length of 100.")
            if not isinstance(d, str):
                entry_errs.append(f"Education[{idx}].date_range must be a string.")
                d = ""
            else:
                d = d.strip()
                if d == "":
                    entry_errs.append(f"Education[{idx}].date_range is required.")
                elif len(d) > 100:
                    entry_errs.append(f"Education[{idx}].date_range exceeds maximum length of 100.")
            if entry_errs:
                errors.extend(entry_errs)
            else:
                education_out.append({"school": s, "program": p, "date_range": d})

    # Skills list
    skills_in = data.get("skills", [])
    skills_out = []
    if not isinstance(skills_in, list):
        errors.append("Skills must be a list.")
    else:
        seen_lower = set()
        for idx, sk in enumerate(skills_in):
            if not isinstance(sk, str):
                errors.append(f"Skills[{idx}] must be a string.")
                continue
            s = sk.strip()
            if s == "":
                errors.append(f"Skills[{idx}] cannot be empty.")
                continue
            if len(s) > 50:
                errors.append(f"Skills[{idx}] exceeds maximum length of 50.")
                continue
            if s.lower() in seen_lower:
                errors.append("Skill already added.")
                continue
            seen_lower.add(s.lower())
            skills_out.append(s)

    if errors:
        return jsonify({"error": "Validation failed.", "errors": errors}), 400

    with lock:
        state["initialized"] = True
        state["headline"] = headline
        state["summary"] = summary
        # assign ids
        state["experience"] = []
        for e in experience_out:
            state["experience"].append({"id": state["_next_exp_id"], **e})
            state["_next_exp_id"] += 1
        state["education"] = []
        for e in education_out:
            state["education"].append({"id": state["_next_edu_id"], **e})
            state["_next_edu_id"] += 1
        state["skills"] = skills_out

    return jsonify({"message": "Resume saved.", "success": True}), 200


# Experience CRUD
@app.route("/resume/experience", methods=["POST"])
def add_experience():
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(silent=True) or {}
    errors = []
    t = data.get("title", "")
    d = data.get("date_range", "")
    desc = data.get("description", "")
    if not isinstance(t, str):
        errors.append("title must be a string.")
        t = ""
    else:
        t = t.strip()
        if t == "":
            errors.append("title is required.")
        elif len(t) > 100:
            errors.append("title exceeds maximum length of 100.")
    if not isinstance(d, str):
        errors.append("date_range must be a string.")
        d = ""
    else:
        d = d.strip()
        if d == "":
            errors.append("date_range is required.")
        elif len(d) > 100:
            errors.append("date_range exceeds maximum length of 100.")
    if not isinstance(desc, str):
        errors.append("description must be a string.")
        desc = ""
    else:
        desc = desc.strip()
        if desc == "":
            errors.append("description is required.")
        elif len(desc) > 1000:
            errors.append("description exceeds maximum length of 1000.")
    if errors:
        return jsonify({"error": "Validation failed.", "errors": errors}), 400
    with lock:
        state["initialized"] = True
        entry = {"id": state["_next_exp_id"], "title": t, "date_range": d, "description": desc}
        state["_next_exp_id"] += 1
        state["experience"].append(entry)
    return jsonify({"message": "Experience added.", "entry": entry}), 201


@app.route("/resume/experience/<int:eid>", methods=["PUT"])
def edit_experience(eid):
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(silent=True) or {}
    errors = []
    t = data.get("title", "")
    d = data.get("date_range", "")
    desc = data.get("description", "")
    if not isinstance(t, str):
        errors.append("title must be a string.")
    else:
        t = t.strip()
        if t == "":
            errors.append("title is required.")
        elif len(t) > 100:
            errors.append("title exceeds maximum length of 100.")
    if not isinstance(d, str):
        errors.append("date_range must be a string.")
    else:
        d = d.strip()
        if d == "":
            errors.append("date_range is required.")
        elif len(d) > 100:
            errors.append("date_range exceeds maximum length of 100.")
    if not isinstance(desc, str):
        errors.append("description must be a string.")
    else:
        desc = desc.strip()
        if desc == "":
            errors.append("description is required.")
        elif len(desc) > 1000:
            errors.append("description exceeds maximum length of 1000.")
    if errors:
        return jsonify({"error": "Validation failed.", "errors": errors}), 400
    with lock:
        for e in state["experience"]:
            if e["id"] == eid:
                e["title"] = t
                e["date_range"] = d
                e["description"] = desc
                return jsonify({"message": "Experience updated.", "entry": e}), 200
    return jsonify({"error": "Experience not found."}), 404


@app.route("/resume/experience/<int:eid>", methods=["DELETE"])
def delete_experience(eid):
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    with lock:
        for i, e in enumerate(state["experience"]):
            if e["id"] == eid:
                state["experience"].pop(i)
                return jsonify({"message": "Experience removed."}), 200
    return jsonify({"error": "Experience not found."}), 404


# Education CRUD
@app.route("/resume/education", methods=["POST"])
def add_education():
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(silent=True) or {}
    errors = []
    s = data.get("school", "")
    p = data.get("program", "")
    d = data.get("date_range", "")
    if not isinstance(s, str):
        errors.append("school must be a string.")
        s = ""
    else:
        s = s.strip()
        if s == "":
            errors.append("school is required.")
        elif len(s) > 100:
            errors.append("school exceeds maximum length of 100.")
    if not isinstance(p, str):
        errors.append("program must be a string.")
        p = ""
    else:
        p = p.strip()
        if p == "":
            errors.append("program is required.")
        elif len(p) > 100:
            errors.append("program exceeds maximum length of 100.")
    if not isinstance(d, str):
        errors.append("date_range must be a string.")
        d = ""
    else:
        d = d.strip()
        if d == "":
            errors.append("date_range is required.")
        elif len(d) > 100:
            errors.append("date_range exceeds maximum length of 100.")
    if errors:
        return jsonify({"error": "Validation failed.", "errors": errors}), 400
    with lock:
        state["initialized"] = True
        entry = {"id": state["_next_edu_id"], "school": s, "program": p, "date_range": d}
        state["_next_edu_id"] += 1
        state["education"].append(entry)
    return jsonify({"message": "Education added.", "entry": entry}), 201


@app.route("/resume/education/<int:eid>", methods=["PUT"])
def edit_education(eid):
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(silent=True) or {}
    errors = []
    s = data.get("school", "")
    p = data.get("program", "")
    d = data.get("date_range", "")
    if not isinstance(s, str):
        errors.append("school must be a string.")
    else:
        s = s.strip()
        if s == "":
            errors.append("school is required.")
        elif len(s) > 100:
            errors.append("school exceeds maximum length of 100.")
    if not isinstance(p, str):
        errors.append("program must be a string.")
    else:
        p = p.strip()
        if p == "":
            errors.append("program is required.")
        elif len(p) > 100:
            errors.append("program exceeds maximum length of 100.")
    if not isinstance(d, str):
        errors.append("date_range must be a string.")
    else:
        d = d.strip()
        if d == "":
            errors.append("date_range is required.")
        elif len(d) > 100:
            errors.append("date_range exceeds maximum length of 100.")
    if errors:
        return jsonify({"error": "Validation failed.", "errors": errors}), 400
    with lock:
        for e in state["education"]:
            if e["id"] == eid:
                e["school"] = s
                e["program"] = p
                e["date_range"] = d
                return jsonify({"message": "Education updated.", "entry": e}), 200
    return jsonify({"error": "Education not found."}), 404


@app.route("/resume/education/<int:eid>", methods=["DELETE"])
def delete_education(eid):
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    with lock:
        for i, e in enumerate(state["education"]):
            if e["id"] == eid:
                state["education"].pop(i)
                return jsonify({"message": "Education removed."}), 200
    return jsonify({"error": "Education not found."}), 404


# Skills
@app.route("/resume/skills", methods=["POST"])
def add_skill():
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(silent=True) or {}
    sk = data.get("skill", "")
    if not isinstance(sk, str):
        return jsonify({"error": "skill must be a string."}), 400
    s = sk.strip()
    if s == "":
        return jsonify({"error": "skill is required."}), 400
    if len(s) > 50:
        return jsonify({"error": "skill exceeds maximum length of 50."}), 400
    with lock:
        for existing in state["skills"]:
            if existing.lower() == s.lower():
                return jsonify({"error": "Skill already added."}), 400
        state["initialized"] = True
        state["skills"].append(s)
    return jsonify({"message": "Skill added.", "skill": s}), 201


@app.route("/resume/skills/<path:skill>", methods=["DELETE"])
def delete_skill(skill):
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    target = skill.strip().lower()
    with lock:
        for i, sk in enumerate(state["skills"]):
            if sk.lower() == target:
                state["skills"].pop(i)
                return jsonify({"message": "Skill removed."}), 200
    return jsonify({"error": "Skill not found."}), 404


# Headline & Summary individual updates
@app.route("/resume/headline", methods=["PUT"])
def update_headline():
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(silent=True) or {}
    h = data.get("headline", "")
    if not isinstance(h, str):
        return jsonify({"error": "headline must be a string."}), 400
    h = h.strip()
    if h == "":
        return jsonify({"error": "Headline is required."}), 400
    if len(h) > 100:
        return jsonify({"error": "Headline exceeds maximum length of 100."}), 400
    with lock:
        state["initialized"] = True
        state["headline"] = h
    return jsonify({"message": "Headline updated.", "headline": h}), 200


@app.route("/resume/summary", methods=["PUT"])
def update_summary():
    ok, err = check_password()
    if not ok:
        msg, code = err
        return jsonify({"error": msg}), code
    data = request.get_json(silent=True) or {}
    s = data.get("summary", "")
    if s is None:
        s = ""
    if not isinstance(s, str):
        return jsonify({"error": "summary must be a string."}), 400
    s = s.strip()
    if len(s) > 500:
        return jsonify({"error": "Summary exceeds maximum length of 500."}), 400
    with lock:
        state["initialized"] = True
        state["summary"] = s
    return jsonify({"message": "Summary updated.", "summary": s}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
