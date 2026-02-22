# attendance/ai_service.py
"""
AI Face Recognition Service
────────────────────────────
Uses the `face_recognition` library (built on dlib) to:
1. Encode known student faces from their stored photos
2. Compare uploaded class photo against known encodings
3. Return list of recognized student IDs

Theory (for viva):
- face_recognition uses a 128-dimension face embedding (vector)
- Each face is converted to a point in 128D space
- Two faces are "the same" if their Euclidean distance < threshold (0.6)
- This is called a face descriptor / face embedding
"""

import face_recognition
import numpy as np
from PIL import Image
import io
import os


def encode_student_face(photo_file):
    """
    Takes a student's saved photo file path.
    Returns a 128-d numpy array (face encoding) or None.

    Called when a student uploads their profile photo.
    We store this encoding to compare later.
    """
    try:
        image  = face_recognition.load_image_file(photo_file)
        encodings = face_recognition.face_encodings(image)

        if len(encodings) == 0:
            return None  # No face found in photo

        # Take the first (and ideally only) face
        return encodings[0]

    except Exception as e:
        print(f"[AI] Error encoding face: {e}")
        return None


def recognize_faces_in_image(uploaded_image_file, known_encodings_map):
    """
    Main recognition function.

    Parameters:
    ─────────────
    uploaded_image_file : InMemoryUploadedFile
        The class photo uploaded by faculty

    known_encodings_map : dict
        { student_id: numpy_array_128d }
        Built from all enrolled students' stored encodings

    Returns:
    ─────────
    dict with:
        recognized_ids   : list of student IDs detected
        unrecognized     : int count of unknown faces
        total_faces      : int total faces found in image
        confidence_map   : { student_id: confidence_score }
    """
    try:
        # Load the uploaded image
        image_data = uploaded_image_file.read()
        image      = face_recognition.load_image_file(io.BytesIO(image_data))

        # Find all faces and their encodings in the uploaded photo
        face_locations = face_recognition.face_locations(image, model='hog')
        face_encodings = face_recognition.face_encodings(image, face_locations)

        if not face_encodings:
            return {
                'recognized_ids':  [],
                'unrecognized':    0,
                'total_faces':     0,
                'confidence_map':  {},
                'error':           'No faces detected in uploaded image'
            }

        recognized_ids = []
        confidence_map = {}
        unrecognized   = 0

        # Prepare known encodings as parallel lists for comparison
        student_ids = list(known_encodings_map.keys())
        known_list  = [known_encodings_map[sid] for sid in student_ids]

        for face_enc in face_encodings:
            # Compare this face against all known faces
            # Returns list of True/False
            matches   = face_recognition.compare_faces(known_list, face_enc, tolerance=0.6)

            # Get distance to each known face (lower = more similar)
            distances = face_recognition.face_distance(known_list, face_enc)

            if True in matches:
                # Find the closest match
                best_idx    = int(np.argmin(distances))
                best_id     = student_ids[best_idx]
                confidence  = round((1 - distances[best_idx]) * 100, 1)

                recognized_ids.append(best_id)
                confidence_map[best_id] = confidence
            else:
                unrecognized += 1

        return {
            'recognized_ids': list(set(recognized_ids)),  # deduplicate
            'unrecognized':   unrecognized,
            'total_faces':    len(face_encodings),
            'confidence_map': confidence_map,
        }

    except Exception as e:
        print(f"[AI] Recognition error: {e}")
        return {
            'recognized_ids': [],
            'unrecognized':   0,
            'total_faces':    0,
            'confidence_map': {},
            'error':          str(e)
        }


def get_known_encodings(students_queryset):
    """
    Builds the known_encodings_map from a queryset of Student objects.
    Only includes students who have uploaded a photo.

    Returns: { student_id: numpy_array } or {}
    """
    encodings_map = {}

    for student in students_queryset:
        if not student.photo:
            continue

        photo_path = student.photo.path  # absolute filesystem path

        if not os.path.exists(photo_path):
            continue

        encoding = encode_student_face(photo_path)
        if encoding is not None:
            encodings_map[student.id] = encoding

    return encodings_map