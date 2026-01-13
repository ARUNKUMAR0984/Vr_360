from flask import Flask, request, send_file
from flask_cors import CORS
import subprocess
import os
import tempfile
import uuid

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'ok'}, 200

@app.route('/convert-360', methods=['POST'])
def convert_360():
    temp_dir = tempfile.gettempdir()
    unique_id = str(uuid.uuid4())[:8]
    
    try:
        # Receive video file
        if 'video' not in request.files:
            return {'error': 'No video file provided'}, 400
        
        video_file = request.files['video']
        if video_file.filename == '':
            return {'error': 'No file selected'}, 400
        
        # Save input file
        input_path = os.path.join(temp_dir, f'input_{unique_id}.mp4')
        output_path = os.path.join(temp_dir, f'output_360_{unique_id}.mp4')
        
        video_file.save(input_path)
        print(f"[{unique_id}] Received video: {input_path}")
        
        # Check if file was saved
        if not os.path.exists(input_path):
            return {'error': 'Failed to save input file'}, 500
        
        # Inject 360 metadata using spatial-media
        print(f"[{unique_id}] Starting metadata injection...")
        cmd = ['python', '-m', 'spatial_media', '-i', input_path, '-o', output_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            print(f"[{unique_id}] Error: {result.stderr}")
            return {'error': f'Spatial media error: {result.stderr}'}, 500
        
        # Verify output exists
        if not os.path.exists(output_path):
            return {'error': 'Failed to create output file'}, 500
        
        print(f"[{unique_id}] Metadata injection complete!")
        
        # Send file back
        response = send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'video_360_{unique_id}.mp4'
        )
        
        # Cleanup input file
        try:
            os.remove(input_path)
        except:
            pass
        
        return response
    
    except subprocess.TimeoutExpired:
        return {'error': 'Processing timeout - video too large'}, 500
    except Exception as e:
        print(f"[{unique_id}] Exception: {str(e)}")
        return {'error': str(e)}, 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
