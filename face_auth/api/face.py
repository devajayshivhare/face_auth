import frappe
import os
import face_recognition

@frappe.whitelist(allow_guest=True)
def register_face():
    user_id = frappe.form_dict.get('user_id')
    # user_id = "ajay001"
    # print(f"User ID: {user_id}")
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
        # return {"message": {"matched": result[0]}}
        return {"message": {"matched": bool(result[0])}}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Face Match Error")
        return {"message": {"matched": False, "error": str(e)}}
