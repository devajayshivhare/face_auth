import frappe
import os
import face_recognition

@frappe.whitelist(allow_guest=True)
def register_face():
    user_id = frappe.form_dict.get('user_id')
    if not user_id:
        return {"message": "missing_user_id"}

    file = frappe.request.files['image']
    filename = f'reference_{user_id}.jpg'
    save_path = os.path.join(frappe.get_site_path('public'), 'files', filename)

    with open(save_path, 'wb') as f:
        f.write(file.read())

    image = face_recognition.load_image_file(save_path)
    encodings = face_recognition.face_encodings(image)

    if not encodings:
        return {"message": "no_face_detected"}

    return {"message": "success"}

@frappe.whitelist(allow_guest=True)
def match_face():
    user_id = frappe.form_dict.get('user_id')
    # Get geofencing data from request
    # latitude = 20
    # longitude = 21
    # device_id = "redmi note 7S"  # Optional
    latitude = frappe.form_dict.get('latitude')
    longitude = frappe.form_dict.get('longitude')
    device_id = frappe.form_dict.get('device_id')  # Optional
    
    if not user_id:
        return {"message": {"matched": False, "reason": "missing_user_id"}}

    try:
        file = frappe.request.files['image']
        upload_path = os.path.join(frappe.get_site_path('public'), 'files', file.filename)

        with open(upload_path, 'wb') as f:
            f.write(file.read())

        uploaded_image = face_recognition.load_image_file(upload_path)
        uploaded_encodings = face_recognition.face_encodings(uploaded_image)

        if not uploaded_encodings:
            return {"message": {"matched": False, "reason": "no_face_in_uploaded_image"}}

        uploaded_encoding = uploaded_encodings[0]

        ref_filename = f'reference_{user_id}.jpg'
        ref_image_path = os.path.join(frappe.get_site_path('public'), 'files', ref_filename)

        if not os.path.exists(ref_image_path):
            return {"message": {"matched": False, "reason": "reference_image_missing"}}

        ref_image = face_recognition.load_image_file(ref_image_path)
        ref_encoding = face_recognition.face_encodings(ref_image)[0]

        result = face_recognition.compare_faces([ref_encoding], uploaded_encoding)
        match_result = bool(result[0])
        
        # If face match is successful, save geofencing data to Employee Checkin
        if match_result and latitude and longitude:
            try:
                # Create Employee Checkin record
                checkin_doc = frappe.get_doc({
                    "doctype": "Employee Checkin",
                    "employee": user_id,  # Assuming user_id is the employee ID
                    "time": frappe.utils.now_datetime(),
                    "device_id": device_id,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "skip_auto_attendance": 0,
                    "attendance": None
                })
                checkin_doc.insert(ignore_permissions=True)
                frappe.db.commit()
                
                return {
                    "message": {
                        "matched": True,
                        "checkin_saved": True,
                        "checkin_name": checkin_doc.name
                    }
                }
            
            except Exception as checkin_error:
                frappe.log_error(frappe.get_traceback(), "Employee Checkin Creation Error")
                return {
                    "message": {
                        "matched": True,
                        "checkin_saved": False,
                        "error": f"Checkin failed: {str(checkin_error)}"
                    }
                }
        
        return {"message": {"matched": match_result}}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Face Match Error")
        return {"message": {"matched": False, "error": str(e)}}