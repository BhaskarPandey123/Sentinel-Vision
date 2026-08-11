import os
from flask import Flask, render_template, request, jsonify
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
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.jpg', '.jpeg', '.png']:
        report = analyze_image(filepath)
    else:
        report = analyze_video(filepath)

    return render_template('dashboard.html', report=report, filename=filename)

if __name__ == '__main__':
    app.run(debug=True)
