import os
from flask import current_app
from werkzeug.utils import secure_filename
from PIL import Image
import uuid

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image_file(file_storage):
    """Save an uploaded image file and return its path"""
    if not file_storage or file_storage.filename == '':
        raise ValueError('No file provided')

    if not allowed_file(file_storage.filename):
        raise ValueError(f'Invalid file type. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}')

    # Generate unique filename
    filename = file_storage.filename
    ext = filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    secure_name = secure_filename(unique_filename)

    # Save file
    upload_folder = current_app.config['UPLOAD_FOLDER']
    filepath = os.path.join(upload_folder, secure_name)

    # Save the file temporarily
    file_storage.save(filepath)

    # Verify it's a valid image
    try:
        with Image.open(filepath) as img:
            img.verify()
    except Exception as e:
        # Remove the file if it's not a valid image
        if os.path.exists(filepath):
            os.remove(filepath)
        raise ValueError(f'Invalid image file: {str(e)}')

    # Return the relative path for storage in DB
    return os.path.join('uploads', secure_name)
