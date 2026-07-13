from app import create_app
import os

app = create_app()

if __name__ == '__main__':
    # Ensure upload folder exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # Run on all interfaces for accessibility
    app.run(host='0.0.0.0', port=5000, debug=True)
