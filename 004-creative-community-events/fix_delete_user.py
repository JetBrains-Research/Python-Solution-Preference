with open('app.py', 'r') as f:
    content = f.read()

old = """    # Return reserved spots to event capacity (soft-delete attendances)
    attendances = Attendance.query.filter_by(user_id=user.id, deleted=False).all()
    for att in attendances:
        att.deleted = True
        # capacity is automatically restored since spots_remaining counts non-deleted attendances
    db.session.delete(user)"""

new = """    # Cascade will delete attendances, restoring capacity
    db.session.delete(user)"""

content = content.replace(old, new)
with open('app.py', 'w') as f:
    f.write(content)
print("Patched")
