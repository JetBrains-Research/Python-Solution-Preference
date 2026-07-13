from flask import Flask, request, jsonify
import json
import os
import uuid

app = Flask(__name__)

DATA_FILE = 'data.json'
EDIT_PASSWORD = 'resume-editor-2025'

def load_data():
    """Load resume data from file."""
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def save_data(data):
    """Save resume data to file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def check_password():
    """Check if the password in request is correct."""
    password = request.headers.get('X-Resume-Password')
    if password != EDIT_PASSWORD:
        return False
    return True

def validate_headline(headline):
    """Validate headline field."""
    if headline is None:
        return False, "Headline is required"
    headline = headline.strip()
    if not headline:
        return False, "Headline is required"
    if len(headline) > 100:
        return False, "Headline must be 100 characters or less"
    return True, headline

def validate_summary(summary):
    """Validate summary field."""
    if summary is None:
        return True, ""
    summary = summary.strip()
    if len(summary) > 500:
        return False, "Summary must be 500 characters or less"
    return True, summary

def validate_experience_entry(entry):
    """Validate a single experience entry."""
    errors = []
    
    title = entry.get('title', '').strip() if entry.get('title') else ''
    if not title:
        errors.append("Experience title is required")
    elif len(title) > 100:
        errors.append("Experience title must be 100 characters or less")
    
    date_range = entry.get('date_range', '').strip() if entry.get('date_range') else ''
    if not date_range:
        errors.append("Experience date range is required")
    elif len(date_range) > 100:
        errors.append("Experience date range must be 100 characters or less")
    
    description = entry.get('description', '').strip() if entry.get('description') else ''
    if not description:
        errors.append("Experience description is required")
    elif len(description) > 1000:
        errors.append("Experience description must be 1000 characters or less")
    
    if errors:
        return False, errors
    
    return True, {
        'title': title,
        'date_range': date_range,
        'description': description
    }

def validate_education_entry(entry):
    """Validate a single education entry."""
    errors = []
    
    school_name = entry.get('school_name', '').strip() if entry.get('school_name') else ''
    if not school_name:
        errors.append("Education school name is required")
    elif len(school_name) > 100:
        errors.append("Education school name must be 100 characters or less")
    
    program = entry.get('program', '').strip() if entry.get('program') else ''
    if not program:
        errors.append("Education program is required")
    elif len(program) > 100:
        errors.append("Education program must be 100 characters or less")
    
    date_range = entry.get('date_range', '').strip() if entry.get('date_range') else ''
    if not date_range:
        errors.append("Education date range is required")
    elif len(date_range) > 100:
        errors.append("Education date range must be 100 characters or less")
    
    if errors:
        return False, errors
    
    return True, {
        'school_name': school_name,
        'program': program,
        'date_range': date_range
    }

def validate_skill(skill):
    """Validate a single skill."""
    if skill is None:
        return False, "Skill is required"
    skill = skill.strip()
    if not skill:
        return False, "Skill is required"
    if len(skill) > 50:
        return False, "Skill must be 50 characters or less"
    return True, skill

@app.route('/resume', methods=['GET'])
def get_resume():
    """Get the resume (public read-only)."""
    data = load_data()
    
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 200
    
    # Build response with sections in order
    response = {
        "headline": data.get('headline', ''),
        "summary": data.get('summary', ''),
        "experience": data.get('experience', []),
        "education": data.get('education', []),
        "skills": data.get('skills', [])
    }
    
    # Add empty state messages
    if not response['experience']:
        response['experience'] = []
    
    return jsonify(response)

@app.route('/resume', methods=['POST'])
def save_resume():
    """Save the resume (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "error": "Invalid JSON"
            }), 400
    except Exception:
        return jsonify({
            "error": "Invalid JSON"
        }), 400
    
    errors = []
    
    # Validate headline (required)
    headline_valid, headline_result = validate_headline(data.get('headline'))
    if not headline_valid:
        errors.append(headline_result)
        headline = None
    else:
        headline = headline_result
    
    # Validate summary (optional)
    summary_valid, summary = validate_summary(data.get('summary'))
    if not summary_valid:
        errors.append(summary)
    
    # Validate experience entries
    experience = []
    if 'experience' in data:
        for idx, entry in enumerate(data['experience']):
            exp_valid, exp_result = validate_experience_entry(entry)
            if not exp_valid:
                for err in exp_result:
                    errors.append(f"Experience {idx + 1}: {err}")
            else:
                experience.append(exp_result)
    
    # Validate education entries
    education = []
    if 'education' in data:
        for idx, entry in enumerate(data['education']):
            edu_valid, edu_result = validate_education_entry(entry)
            if not edu_valid:
                for err in edu_result:
                    errors.append(f"Education {idx + 1}: {err}")
            else:
                education.append(edu_result)
    
    # Validate skills
    skills = []
    if 'skills' in data:
        for idx, skill in enumerate(data['skills']):
            skill_valid, skill_result = validate_skill(skill)
            if not skill_valid:
                errors.append(f"Skill {idx + 1}: {skill_result}")
            else:
                # Check for duplicates (case-insensitive)
                skill_lower = skill_result.lower()
                if any(s.lower() == skill_lower for s in skills):
                    errors.append(f"Skill {idx + 1}: Skill already added.")
                else:
                    skills.append(skill_result)
    
    if errors:
        return jsonify({
            "error": "Validation failed",
            "errors": errors
        }), 400
    
    # Save the data
    resume_data = {
        'headline': headline,
        'summary': summary,
        'experience': experience,
        'education': education,
        'skills': skills
    }
    save_data(resume_data)
    
    return jsonify({
        "message": "Resume saved successfully"
    }), 200

@app.route('/resume/experience', methods=['GET'])
def get_experience():
    """Get experience entries."""
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 200
    return jsonify({
        "experience": data.get('experience', [])
    })

@app.route('/resume/experience', methods=['POST'])
def add_experience():
    """Add an experience entry (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    try:
        entry = request.get_json()
        if entry is None:
            return jsonify({
                "error": "Invalid JSON"
            }), 400
    except Exception:
        return jsonify({
            "error": "Invalid JSON"
        }), 400
    
    valid, result = validate_experience_entry(entry)
    if not valid:
        return jsonify({
            "error": "Validation failed",
            "errors": result
        }), 400
    
    data = load_data() or {
        'headline': '',
        'summary': '',
        'experience': [],
        'education': [],
        'skills': []
    }
    
    data['experience'].append(result)
    save_data(data)
    
    return jsonify({
        "message": "Experience added successfully",
        "experience": result
    }), 201

@app.route('/resume/experience/<int:index>', methods=['PUT'])
def update_experience(index):
    """Update an experience entry (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 400
    
    experience = data.get('experience', [])
    if index < 0 or index >= len(experience):
        return jsonify({
            "error": "Experience entry not found"
        }), 404
    
    try:
        entry = request.get_json()
        if entry is None:
            return jsonify({
                "error": "Invalid JSON"
            }), 400
    except Exception:
        return jsonify({
            "error": "Invalid JSON"
        }), 400
    
    valid, result = validate_experience_entry(entry)
    if not valid:
        return jsonify({
            "error": "Validation failed",
            "errors": result
        }), 400
    
    data['experience'][index] = result
    save_data(data)
    
    return jsonify({
        "message": "Experience updated successfully",
        "experience": result
    }), 200

@app.route('/resume/experience/<int:index>', methods=['DELETE'])
def delete_experience(index):
    """Delete an experience entry (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 400
    
    experience = data.get('experience', [])
    if index < 0 or index >= len(experience):
        return jsonify({
            "error": "Experience entry not found"
        }), 404
    
    deleted = data['experience'].pop(index)
    save_data(data)
    
    return jsonify({
        "message": "Experience deleted successfully"
    }), 200

@app.route('/resume/education', methods=['GET'])
def get_education():
    """Get education entries."""
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 200
    return jsonify({
        "education": data.get('education', [])
    })

@app.route('/resume/education', methods=['POST'])
def add_education():
    """Add an education entry (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    try:
        entry = request.get_json()
        if entry is None:
            return jsonify({
                "error": "Invalid JSON"
            }), 400
    except Exception:
        return jsonify({
            "error": "Invalid JSON"
        }), 400
    
    valid, result = validate_education_entry(entry)
    if not valid:
        return jsonify({
            "error": "Validation failed",
            "errors": result
        }), 400
    
    data = load_data() or {
        'headline': '',
        'summary': '',
        'experience': [],
        'education': [],
        'skills': []
    }
    
    data['education'].append(result)
    save_data(data)
    
    return jsonify({
        "message": "Education added successfully",
        "education": result
    }), 201

@app.route('/resume/education/<int:index>', methods=['PUT'])
def update_education(index):
    """Update an education entry (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 400
    
    education = data.get('education', [])
    if index < 0 or index >= len(education):
        return jsonify({
            "error": "Education entry not found"
        }), 404
    
    try:
        entry = request.get_json()
        if entry is None:
            return jsonify({
                "error": "Invalid JSON"
            }), 400
    except Exception:
        return jsonify({
            "error": "Invalid JSON"
        }), 400
    
    valid, result = validate_education_entry(entry)
    if not valid:
        return jsonify({
            "error": "Validation failed",
            "errors": result
        }), 400
    
    data['education'][index] = result
    save_data(data)
    
    return jsonify({
        "message": "Education updated successfully",
        "education": result
    }), 200

@app.route('/resume/education/<int:index>', methods=['DELETE'])
def delete_education(index):
    """Delete an education entry (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 400
    
    education = data.get('education', [])
    if index < 0 or index >= len(education):
        return jsonify({
            "error": "Education entry not found"
        }), 404
    
    data['education'].pop(index)
    save_data(data)
    
    return jsonify({
        "message": "Education deleted successfully"
    }), 200

@app.route('/resume/skills', methods=['GET'])
def get_skills():
    """Get skills list."""
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 200
    return jsonify({
        "skills": data.get('skills', [])
    })

@app.route('/resume/skills', methods=['POST'])
def add_skill():
    """Add a skill (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    try:
        data = request.get_json()
        if data is None:
            return jsonify({
                "error": "Invalid JSON"
            }), 400
    except Exception:
        return jsonify({
            "error": "Invalid JSON"
        }), 400
    
    skill = data.get('skill', '')
    valid, result = validate_skill(skill)
    if not valid:
        return jsonify({
            "error": "Validation failed",
            "errors": [result]
        }), 400
    
    db_data = load_data() or {
        'headline': '',
        'summary': '',
        'experience': [],
        'education': [],
        'skills': []
    }
    
    # Check for duplicates (case-insensitive)
    for existing_skill in db_data.get('skills', []):
        if existing_skill.lower() == result.lower():
            return jsonify({
                "error": "Skill already added."
            }), 400
    
    db_data['skills'].append(result)
    save_data(db_data)
    
    return jsonify({
        "message": "Skill added successfully",
        "skill": result
    }), 201

@app.route('/resume/skills/<int:index>', methods=['DELETE'])
def delete_skill(index):
    """Delete a skill (requires password)."""
    if not check_password():
        return jsonify({
            "error": "Password required"
        }), 401
    
    data = load_data()
    if data is None:
        return jsonify({
            "error": "Resume not set up yet."
        }), 400
    
    skills = data.get('skills', [])
    if index < 0 or index >= len(skills):
        return jsonify({
            "error": "Skill not found"
        }), 404
    
    data['skills'].pop(index)
    save_data(data)
    
    return jsonify({
        "message": "Skill deleted successfully"
    }), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
