with open('app.py', 'r') as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if "@app.route('/admin/events/<int:event_id>', methods=['DELETE'])" in line:
        if not skip:
            new_lines.append(line)  # keep first occurrence
            skip = True
        # skip subsequent duplicates
    elif skip and not line.strip():
        continue  # skip empty lines in the duplicate area
    elif skip and "def delete_event(" in line:
        new_lines.append(line)
        skip = False  # now in function body, accept all
    else:
        new_lines.append(line)

# Remove extra trailing return after function
content = ''.join(new_lines)
# Clean the function body
old_func = """def delete_event(user, event_id):
    event = db.session.get(Event, event_id)
    if not event or event.deleted:
        return jsonify({'error': 'Event not found'}), 404
    db.session.delete(event)
    db.session.commit()

    return jsonify({'message': 'Event deleted'})

    return jsonify({'message': 'Event deleted'})"""

new_func = """def delete_event(user, event_id):
    event = db.session.get(Event, event_id)
    if not event or event.deleted:
        return jsonify({'error': 'Event not found'}), 404

    db.session.delete(event)
    db.session.commit()

    return jsonify({'message': 'Event deleted'})"""

if old_func in content:
    content = content.replace(old_func, new_func)
else:
    print("Could not find old_func")
    # Find and replace manually
    # Let's just rebuild the file from scratch? No, try to find it.
    import re
    pattern = r"def delete_event\(user, event_id\):.*?return jsonify\(\{'message': 'Event deleted'\}\)\s*return jsonify\(\{'message': 'Event deleted'\}\)"
    content = re.sub(pattern, new_func, content, flags=re.DOTALL)

with open('app.py', 'w') as f:
    f.write(content)
print("Patched")
