from flask import Flask, request, send_file
from flask_cors import CORS
import os
import tempfile
import uuid
import struct
import io

app = Flask(__name__)
CORS(app)

# Spherical Video Metadata Box (UUID)
SPHERICAL_UUID = bytes([
    0xFF, 0xE4, 0x81, 0x84, 0xAB, 0xA1, 0xD6, 0x46,
    0x24, 0xD8, 0x9F, 0xBD, 0xBA, 0xA2, 0x43, 0xF7
])

SPHERICAL_METADATA = b"""
<rdf:SphericalVideo xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <SphericalVideo>true</SphericalVideo>
  <Projection>equirectangular</Projection>
  <InitialViewHeadingDegrees>0</InitialViewHeadingDegrees>
  <InitialViewPitchDegrees>0</InitialViewPitchDegrees>
  <InitialViewRollDegrees>0</InitialViewRollDegrees>
  <stitched>true</stitched>
  <stitching_software>360VideoConverter</stitching_software>
  <stereo_mode>mono</stereo_mode>
  <source_count>1</source_count>
</rdf:SphericalVideo>
""".strip()

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'ok'}, 200

def inject_spherical_metadata(input_path, output_path):
    """Inject spherical video metadata into MP4 file"""
    try:
        with open(input_path, 'rb') as f:
            original_data = f.read()
        
        # Create UUID box with spherical metadata
        metadata = SPHERICAL_METADATA
        uuid_box_size = 8 + 16 + len(metadata)  # size + uuid + data
        
        uuid_box = struct.pack('>I', uuid_box_size)  # box size
        uuid_box += b'uuid'  # box type
        uuid_box += SPHERICAL_UUID  # UUID
        uuid_box += metadata  # metadata content
        
        # Find mdat box and insert metadata before it
        mdat_index = original_data.find(b'mdat')
        
        if mdat_index > 0:
            # Find the start of mdat box
            mdat_start = mdat_index - 4
            modified_data = original_data[:mdat_start] + uuid_box + original_data[mdat_start:]
        else:
            # If no mdat found, append to end
            modified_data = original_data + uuid_box
        
        # Write output
        with open(output_path, 'wb') as f:
            f.write(modified_data)
        
        return True
    except Exception as e:
        print(f"Error injecting metadata: {str(e)}")
        return False

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
        
        file_size = os.path.getsize(input_path)
        print(f"[{unique_id}] File size: {file_size / 1024 / 1024:.2f} MB")
        
        # Inject 360 metadata
        print(f"[{unique_id}] Starting metadata injection...")
        
        if not inject_spherical_metadata(input_path, output_path):
            return {'error': 'Failed to inject metadata'}, 500
        
        # Verify output exists
        if not os.path.exists(output_path):
            return {'error': 'Failed to create output file'}, 500
        
        output_size = os.path.getsize(output_path)
        print(f"[{unique_id}] Metadata injection complete! Output size: {output_size / 1024 / 1024:.2f} MB")
        
        # Read output file and send
        with open(output_path, 'rb') as f:
            file_data = f.read()
        
        response = send_file(
            io.BytesIO(file_data),
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'video_360_{unique_id}.mp4'
        )
        
        # Cleanup files
        try:
            os.remove(input_path)
            os.remove(output_path)
        except:
            pass
        
        return response
    
    except Exception as e:
        print(f"[{unique_id}] Exception: {str(e)}")
        return {'error': str(e)}, 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
