import frappe
import os
import face_recognition
import numpy as np
from PIL import Image, ImageOps, ExifTags
from frappe.utils.file_manager import save_file

def correct_image_orientation(image_path):
    """Correct image orientation using EXIF data and resize for optimal face detection"""
    try:
        img = Image.open(image_path)
        
        # Handle EXIF orientation
        if hasattr(img, '_getexif'):
            exif = img._getexif()
            if exif:
                for tag, value in ExifTags.TAGS.items():
                    if value == 'Orientation':
                        orientation = exif.get(tag)
                        break
                else:
                    orientation = None

                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)
        
        # Resize large mobile images
        max_size = 1200
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Save corrected image back to original path
        img.save(image_path, "JPEG", quality=95, optimize=True)
        return True
    except Exception as e:
        frappe.log_error(f"EXIF correction failed: {str(e)}", "Image Correction Error")
        return False

@frappe.whitelist(allow_guest=True)
def register_face():
    user_id = frappe.form_dict.get('user_id')
    if not user_id:
        return {"message": "missing_user_id"}

    file = frappe.request.files['image']
    filename = f'reference_{user_id}.jpg'
    save_path = os.path.join(frappe.get_site_path('public', 'files'), filename)

    # Save the uploaded file
    with open(save_path, 'wb') as f:
        f.write(file.read())

    # Correct EXIF orientation and resize
    if not correct_image_orientation(save_path):
        return {"message": "image_processing_failed"}

    # Load and process image
    try:
        image = face_recognition.load_image_file(save_path)
        encodings = face_recognition.face_encodings(image, num_jitters=1, model="large")
        
        if not encodings:
            return {"message": "no_face_detected"}
            
        return {"message": "success"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Face Encoding Error")
        return {"message": "face_encoding_failed"}

@frappe.whitelist(allow_guest=True)
def match_face():
    user_id = frappe.form_dict.get('user_id')
    latitude = frappe.form_dict.get('latitude')
    longitude = frappe.form_dict.get('longitude')
    device_id = frappe.form_dict.get('device_id')

    if not user_id:
        return {"message": {"matched": False, "reason": "missing_user_id"}}

    try:
        file = frappe.request.files['image']
        filename = f'upload_{user_id}_{frappe.generate_hash(length=8)}.jpg'
        upload_path = os.path.join(frappe.get_site_path('public', 'files'), filename)

        # Save the uploaded file
        with open(upload_path, 'wb') as f:
            f.write(file.read())

         # Read file content once and save it to disk
        # file_content = file.read()  # Read file content only once
        # with open(upload_path, 'wb') as f:
            # f.write(file_content)  # Save to disk

        # Correct EXIF orientation and resize
        if not correct_image_orientation(upload_path):
            return {"message": {"matched": False, "reason": "image_processing_failed"}}

        # Process uploaded image
        uploaded_image = face_recognition.load_image_file(upload_path)
        uploaded_encodings = face_recognition.face_encodings(
            uploaded_image, 
            num_jitters=1,
            model="large"
        )

        if not uploaded_encodings:
            return {"message": {"matched": False, "reason": "no_face_in_uploaded_image"}}

        uploaded_encoding = uploaded_encodings[0]

        # Process reference image
        ref_filename = f'reference_{user_id}.jpg'
        ref_image_path = os.path.join(frappe.get_site_path('public', 'files'), ref_filename)

        if not os.path.exists(ref_image_path):
            return {"message": {"matched": False, "reason": "reference_image_missing"}}

        # Correct reference image if needed
        if not correct_image_orientation(ref_image_path):
            return {"message": {"matched": False, "reason": "reference_image_corruption"}}

        ref_image = face_recognition.load_image_file(ref_image_path)
        ref_encodings = face_recognition.face_encodings(
            ref_image,
            num_jitters=1,
            model="large"
        )
        
        if not ref_encodings:
            return {"message": {"matched": False, "reason": "reference_image_has_no_face"}}

        ref_encoding = ref_encodings[0]

        # Calculate match confidence
        distance = face_recognition.face_distance([ref_encoding], uploaded_encoding)[0]
        confidence = max(0, min(100, (1.0 - distance) * 100))
        match_result = distance <= 0.5

        # If face match is successful, save geofencing data
        if match_result and latitude and longitude:
            try:
                checkin_doc = frappe.get_doc({
                    "doctype": "Employee Checkin",
                    "employee": user_id,
                    "time": frappe.utils.now_datetime(),
                    "device_id": device_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "skip_auto_attendance": 0,
                    "attendance": None
                })
                checkin_doc.insert(ignore_permissions=True)
                frappe.db.commit()

                # ✅ FIX: Read file content as bytes for save_file()
                with open(upload_path, 'rb') as f:
                    file_content = f.read()  # Get actual bytes content

                # 📎 Save photo as attachment
                save_file(
                    filename,
                    file_content,  # Read saved image from disk
                    "Employee Checkin",       # DocType
                    checkin_doc.name,          # Document Name
                    folder="Home",             # Optional folder
                    is_private=0               # Publicly accessible
                )
                frappe.db.commit()

                return {
                    "message": {
                        "matched": True,
                        "distance": round(float(distance), 4),
                        "confidence": round(confidence, 1),
                        "checkin_saved": True,
                        "checkin_name": checkin_doc.name
                    }
                }
            
            except Exception as checkin_error:
                frappe.log_error(frappe.get_traceback(), "Checkin Creation Error")
                return {
                    "message": {
                        "matched": True,
                        "distance": round(float(distance), 4),
                        "confidence": round(confidence, 1),
                        "checkin_saved": False,
                        "error": f"Checkin failed: {str(checkin_error)}"
                    }
                }
        
        return {
            "message": {
                "matched": match_result,
                "distance": round(float(distance), 4),
                "confidence": round(confidence, 1),
                "reason": "face_not_matching" if not match_result else None
            }
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Face Match Error")
        return {"message": {"matched": False, "error": str(e)}}

@frappe.whitelist(allow_guest=True)
def get_test_doc():
    try:
        doc = frappe.get_last_doc("ToDo")
        return {"name": doc.name, "description": doc.description}
    except:
        return {"error": "No ToDo documents found"}