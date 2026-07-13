import re

with open('app.py', 'r') as f:
    content = f.read()

old = '''    # Create user
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)

    # Record code usage
    code_obj.current_uses += 1
    usage = CodeUsage(invite_code=code_obj, user_id=user.id)
    db.session.add(usage)

    db.session.commit()'''

new = '''    # Create user
    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    # Record code usage
    code_obj.current_uses += 1
    usage = CodeUsage(invite_code_id=code_obj.id, user_id=user.id)
    db.session.add(usage)
    db.session.commit()'''

if old in content:
    content = content.replace(old, new)
else:
    print("OLD NOT FOUND")
    # Try to find the problematic part
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if 'CodeUsage(invite_code=code_obj, user=user)' in line:
            print(f"Found at line {i+1}: {line}")
            break
    else:
        print("Could not find")
    exit(1)

with open('app.py', 'w') as f:
    f.write(content)
print("Patched")
