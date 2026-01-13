from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import tempfile
import uuid
import struct
import io
import sys

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Spherical Video Metadata Box (UUID)
SPHERICAL_UUID = bytes([
    0xFF, 0xE4, 0x81, 0x84, 0xAB, 0xA1, 0xD6, 0x46,
    0x24, 0xD8, 0x9F, 0xBD, 0xBA, 0xA2, 0x43, 0xF7
])

SPHERICAL_METADATA = b"""<rdf:SphericalVideo xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><SphericalVideo>true</SphericalVideo><Projection>equirectangular</Projection><InitialViewHeadingDegrees>0</InitialViewHeadingDegrees><InitialViewPitchDegrees>0</InitialViewPitchDegrees><InitialViewRollDegrees>0</InitialViewRollDegrees><stitched>true</stitched><stitching_software>360VideoConverter</stitching_software><stereo_mode>mono</stereo_mode><source_count>1</source_count></rdf:SphericalVideo>"""

@app.route('/health', methods=['GET', 'HEAD'])
def health():
    return jsonify({"status": "ok"}), 200

@app.route('/convert-360', methods=['POST', 'OPTIONS'])
def convert_360():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    
    temp_dir = tempfile.gettempdir()
    unique_id = str(uuid.uuid4())[:8]
    input_path = None
    output_path = None
    
    try:
        print(f"[{unique_id}] POST request received to /convert-360", file=sys.stderr, flush=True)
        
        # Receive video file
        if 'video' not in request.files:
            print(f"[{unique_id}] ERROR: No video file in request", file=sys.stderr, flush=True)
            return jsonify({'error': 'No video file provided'}), 400
        
        video_file = request.files['video']
        if video_file.filename == '':
            print(f"[{unique_id}] ERROR: Empty filename", file=sys.stderr, flush=True)
            return jsonify({'error': 'No file selected'}), 400
        
        # Save input file
        input_path = os.path.join(temp_dir, f'input_{unique_id}.mp4')
        output_path = os.path.join(temp_dir, f'output_360_{unique_id}.mp4')
        
        video_file.save(input_path)
        print(f"[{unique_id}] ✓ Video saved: {input_path}", file=sys.stderr, flush=True)
        
        # Check if file was saved
        if not os.path.exists(input_path):
            print(f"[{unique_id}] ERROR: File not saved", file=sys.stderr, flush=True)
            return jsonify({'error': 'Failed to save input file'}), 500
        
        file_size = os.path.getsize(input_path)
        print(f"[{unique_id}] File size: {file_size / 1024 / 1024:.2f} MB", file=sys.stderr, flush=True)
        
        # Inject 360 metadata
        print(f"[{unique_id}] Starting metadata injection...", file=sys.stderr, flush=True)
        
        if not inject_spherical_metadata(input_path, output_path, unique_id):
            print(f"[{unique_id}] ERROR: Metadata injection failed", file=sys.stderr, flush=True)
            return jsonify({'error': 'Failed to inject metadata'}), 500
        
        # Verify output exists
        if not os.path.exists(output_path):
            print(f"[{unique_id}] ERROR: Output file not created", file=sys.stderr, flush=True)
            return jsonify({'error': 'Failed to create output file'}), 500
        
        output_size = os.path.getsize(output_path)
        print(f"[{unique_id}] ✓ Metadata injection complete! Output: {output_size / 1024 / 1024:.2f} MB", file=sys.stderr, flush=True)
        
        # Read output file and send
        with open(output_path, 'rb') as f:
            file_data = f.read()
        
        print(f"[{unique_id}] ✓ Sending response ({len(file_data) / 1024 / 1024:.2f} MB)", file=sys.stderr, flush=True)
        
        response = send_file(
            io.BytesIO(file_data),
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'video_360_{unique_id}.mp4'
        )
        
        # Cleanup files after sending
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)
            print(f"[{unique_id}] ✓ Cleanup complete", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[{unique_id}] Warning: Cleanup error: {str(e)}", file=sys.stderr, flush=True)
        
        return response
    
    except Exception as e:
        print(f"[{unique_id}] ❌ Exception: {str(e)}", file=sys.stderr, flush=True)
        
        # Cleanup on error
        try:
            if input_path and os.path.exists(input_path):
                os.remove(input_path)
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
        except:
            pass
        
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def inject_spherical_metadata(input_path, output_path, unique_id):
    """Inject spherical video metadata into MP4 file - Optimized"""
    try:
        print(f"[{unique_id}] Reading input file...", file=sys.stderr, flush=True)
        with open(input_path, 'rb') as f:
            original_data = f.read()
        
        # Create UUID box with spherical metadata
        metadata = SPHERICAL_METADATA
        uuid_box_size = 8 + 16 + len(metadata)
        
        uuid_box = struct.pack('>I', uuid_box_size)
        uuid_box += b'uuid'
        uuid_box += SPHERICAL_UUID
        uuid_box += metadata
        
        print(f"[{unique_id}] UUID box created (size: {len(uuid_box)} bytes)", file=sys.stderr, flush=True)
        
        # Find mdat box and insert metadata before it
        mdat_index = original_data.find(b'mdat')
        
        if mdat_index > 0:
            mdat_start = mdat_index - 4
            modified_data = original_data[:mdat_start] + uuid_box + original_data[mdat_start:]
            print(f"[{unique_id}] Inserted UUID before mdat box", file=sys.stderr, flush=True)
        else:
            modified_data = original_data + uuid_box
            print(f"[{unique_id}] Appended UUID box at end", file=sys.stderr, flush=True)
        
        # Write output
        print(f"[{unique_id}] Writing output file...", file=sys.stderr, flush=True)
        with open(output_path, 'wb') as f:
            f.write(modified_data)
        
        print(f"[{unique_id}] Output file written successfully", file=sys.stderr, flush=True)
        return True
    except Exception as e:
        print(f"[{unique_id}] Error in inject_spherical_metadata: {str(e)}", file=sys.stderr, flush=True)
        return False

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask app on port {port}", file=sys.stderr, flush=True)
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
