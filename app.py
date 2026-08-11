import os
import traceback
from pathlib import Path
from flask import Flask, render_template, request
from werkzeug.utils import secure_filename

from layers.layer1_metadata import analyze_image, analyze_video

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files:
        return "No file uploaded", 400
    
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        path_obj = Path(filepath)
        ext = path_obj.suffix.lower()

        if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp']:
            report = analyze_image(path_obj)
        elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm']:
            report = analyze_video(path_obj)
        else:
            report = f"Unsupported file extension: {ext}"

        return render_template('dashboard.html', report=report, filename=filename)

    except Exception as e:
        error_details = traceback.format_exc()
        return f"<h2>Analysis Error Traceback:</h2><pre>{error_details}</pre>", 500

if __name__ == '__main__':
    app.run(debug=True)
