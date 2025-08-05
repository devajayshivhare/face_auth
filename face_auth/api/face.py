import frappe
import os
import face_recognition
import numpy as np
from PIL import Image, ImageOps, ExifTags
from frappe.utils.file_manager import save_file
import math
from datetime import datetime
# from frappe.desk.form.assign_to import delete_assignment
from frappe.desk.form.load import get_attachments

# print("Debug point 1")
# frappe.logger().debug("Debug data:")
# frappe.log_error("Debug info", "Custom Reference")

def get_employee_reference_image(employee_id):
    """
    Get the reference image path for an employee from their attachments
    Returns the physical file path or None if not found
    """
    # Find the most recent face reference image attachment
    reference_file = frappe.db.get_value("File", {
        "attached_to_doctype": "Employee",
        "attached_to_name": employee_id,
        "file_name": ["like", "face_reference_%"]
    }, ["file_url", "name"], order_by="creation desc")
    
    if not reference_file:
        frappe.log_error(f"No reference image found for employee {employee_id}", "Face Matching")
        return None, None  # Return tuple of Nones instead of single None
    
    file_url, file_docname = reference_file
    
    # Convert URL to physical path
    # URL format: /files/filename.jpg
    # Physical path: sites/{site}/public/files/filename.jpg
    file_path = os.path.join(frappe.get_site_path('public', 'files'), file_url[7:])
    
    return file_path, file_docname

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371  # Radius of earth in kilometers
    return c * r  # Distance in kilometers

def get_office_coordinates(employee_id):
    """Get office coordinates from Employee document"""
    try:
        # Assuming Employee doctype has fields: office_latitude, office_longitude, geofence_radius
        employee = frappe.get_doc("Employee", employee_id)
        office_lat = employee.get("office_latitude")
        office_long = employee.get("office_longitude")
        geofence_radius = employee.get("geofence_radius", 0.5)  # Default to 0.5 km if not set
         
        if not office_lat or not office_long:
            frappe.log_error(f"Office coordinates not set for employee {employee_id}", "Geofencing Error")
            return None, None, None
            
        return float(office_lat), float(office_long), float(geofence_radius)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Error fetching office coordinates for {employee_id}")
        return None, None, None

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

def delete_existing_attachments(employee_id):
    """
    Deletes all existing attachments for the given Employee.
    """
    try:
        # Get all attachments for the Employee
        attachments = get_attachments("Employee", employee_id)

        for attachment in attachments:
            # Delete the File document
            file_doc = frappe.get_doc("File", attachment["name"])
            file_doc.delete()

        frappe.db.commit()
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error Deleting Attachments")
        raise e
def get_employee_reference_image(employee_id):
    """
    Fetches the latest reference image attached to the Employee.
    Returns the File document or None if not found.
    """
    try:
        # Find the latest File document attached to the Employee
        file_doc = frappe.get_last_doc("File", filters={
            "attached_to_doctype": "Employee",
            "attached_to_name": employee_id
        })

        return file_doc

    except frappe.DoesNotExistError:
        return None
    
# @frappe.whitelist(allow_guest=True)
# def register_face():
#     user_id = frappe.form_dict.get('user_id')
#     if not user_id:
#         return {"message": "missing_user_id"}

#     # Verify Employee document exists
#     if not frappe.db.exists("Employee", user_id):
#         return {"message": "invalid_employee_id"}

#     file = frappe.request.files['image']
#     filename_without_ext, ext = os.path.splitext(file.filename)
#     new_filename = f"{filename_without_ext}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
#     save_path = os.path.join(frappe.get_site_path('public', 'files'), new_filename)
   
#     # Read file content once for reuse
#     file_content = file.read()
    
#     # Save the uploaded file to disk
#     with open(save_path, 'wb') as f:
#         f.write(file_content)
#     # return

#     # Correct EXIF orientation and resize
#     if not correct_image_orientation(save_path):
#         return {"message": "image_processing_failed"}

#     # Load and process image
#     try:
#         image = face_recognition.load_image_file(save_path)
#         encodings = face_recognition.face_encodings(image, num_jitters=1, model="large")
        
#         if not encodings:
#             return {"message": "no_face_detected"}
        
#         # Save as attachment to Employee document
#         try:
#             # Create unique filename with timestamp to prevent overwrites
#             # attachment_filename = f"face_reference_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            
#             # Save file as attachment to Employee document
#             file_doc = save_file(
#                 # attachment_filename,
#                 new_filename,
#                 file_content,
#                 "Employee",
#                 user_id,
#                 folder="Home",
#                 is_private=0
#             )
#             frappe.db.commit()
            
#             # Optional: Store file URL in Employee custom field
#             # frappe.db.set_value("Employee", user_id, "face_reference_image", file_doc.file_url)
            
#             # Log successful attachment
#             # frappe.log_info(
#             #     f"Face reference image attached to Employee {user_id}",
#             #     "Face Registration"
#             # )
            
#         except Exception as e:
#             frappe.log_error(frappe.get_traceback(), "Employee Attachment Error")
#             return {"message": "attachment_save_failed"}
        
#         return {"message": "success"}
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Face Encoding Error")
#         return {"message": "face_encoding_failed"}

@frappe.whitelist(allow_guest=True)
def register_face():
    temp_files = []  # Track all temporary files

    user_id = frappe.form_dict.get('user_id')
    if not user_id:
        return {"message": "missing_user_id"}

    # Verify Employee document exists
    if not frappe.db.exists("Employee", user_id):
        return {"message": "invalid_employee_id"}
    
    # Check if already registered
    if frappe.db.get_value("Employee", user_id, "face_registered"):
        return {"message": "already_registered"}

    file = frappe.request.files.get('image')
    if not file:
        return {"message": "no_image_provided"}

    # Split filename and extension
    filename_without_ext, ext = os.path.splitext(file.filename)

    # Create timestamped filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_filename = f"{filename_without_ext}_{timestamp}{ext}"  # Only one .jpg at end

    site_path = frappe.get_site_path('public', 'files')
    os.makedirs(site_path, exist_ok=True)

    save_path = os.path.join(site_path, new_filename)

    # Read file content once for reuse
    file_content = file.read()

    # Save the uploaded file to disk
    with open(save_path, 'wb') as f:
        f.write(file_content)
    temp_files.append(save_path)  # Track this temporary file
    # Correct EXIF orientation and resize
    # return
    if not correct_image_orientation(save_path):
        return {"message": "image_processing_failed"}
    # <<< CHANGE START >>>
    # Now, load the *corrected* image to check for faces and for saving
    with open(save_path, 'rb') as f:
        corrected_file_content = f.read()
        # <<< CHANGE END >>>
    # Load and process image
    # Face encoding check (assume function exists)
    try:
        image = face_recognition.load_image_file(save_path)
        encodings = face_recognition.face_encodings(image, num_jitters=1, model="large")
        if not encodings:
            return {"message": "no_face_detected"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Face Encoding Error")
        return {"message": "face_encoding_failed"}

    # Save attachment (ignore permissions for guest)
    try:
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": new_filename,
            "attached_to_doctype": "Employee",
            "attached_to_name": user_id,
            "folder": "Home",
            "is_private": 0,
            # "content": file_content
            "content": corrected_file_content 
        })
        file_doc.save(ignore_permissions=True)

        # Mark employee as face-registered
        frappe.db.set_value("Employee", user_id, "face_registered", 1)
        frappe.db.commit()

        return {"message": "success"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Attachment Save Failed")
        return {"message": "attachment_save_failed"}
    finally:
        # 🧹 Clean up ALL temporary files
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    frappe.log(f"Deleted temporary file: {file_path}")
            except Exception as e:
                frappe.log_error(f"Failed to delete {file_path}: {str(e)}", "File Cleanup Error")
    
@frappe.whitelist(allow_guest=True)
def update_face():
    temp_files = []  # Track all temporary files
    """
    Update face image for an already registered employee.
    Only allowed if already registered.
    """
    user_id = frappe.form_dict.get('user_id')
    if not user_id:
        return {"message": "missing_user_id"}

    if not frappe.db.exists("Employee", user_id):
        return {"message": "invalid_employee_id"}

    # Unlike register, we allow update even if not registered yet
    # Or require already registered? Your choice.
    # Let's allow both: new and update

     # Step 2: Fetch reference image from File doctype
    ref_file_doc = get_employee_reference_image(user_id)
    if not ref_file_doc:
            return {"message": {"matched": False, "reason": "reference_image_missing"}}
    upload_path_last = os.path.join(frappe.get_site_path('public', 'files'), ref_file_doc.file_name)
    temp_files.append(upload_path_last)  # ← Track it
    # frappe.log(ref_file_doc.file_name)
    # return
    if not ref_file_doc:
        return {"message": {"matched": False, "reason": "reference_image_missing"}}
    # ref_image_path = os.path.join(frappe.get_site_path('public', 'files'), ref_file_doc.file_name)

    file = frappe.request.files.get('image')
    if not file:
        return {"message": "no_image_provided"}


    # filename = secure_filename(file.filename)
    filename_without_ext, ext = os.path.splitext(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_filename = f"{filename_without_ext}_{timestamp}{ext}"

    site_path = frappe.get_site_path('public', 'files')
    os.makedirs(site_path, exist_ok=True)
    save_path = os.path.join(site_path, new_filename)

    file_content = file.read()
    with open(save_path, 'wb') as f:
        f.write(file_content)
    temp_files.append(save_path)  # Track this temporary file

    if not correct_image_orientation(save_path):
        return {"message": "image_processing_failed"}

    with open(save_path, 'rb') as f:
        corrected_file_content = f.read()

    try:
        # Load and process image
        image = face_recognition.load_image_file(save_path)
        encodings = face_recognition.face_encodings(image, num_jitters=1, model="large")
        if not encodings:
            return {"message": "no_face_detected"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Face Encoding Error")
        return {"message": "face_encoding_failed"}

    # -----------------------------
    # Delete old attachments
    # -----------------------------
    try:
        attachments = frappe.get_all("File", {
            "attached_to_doctype": "Employee",
            "attached_to_name": user_id
        })
        for attach in attachments:
            doc = frappe.get_doc("File", attach.name)
            doc.delete(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Cleanup Failed")
        return {"message": "cleanup_failed"}

    # -----------------------------
    # Save new file
    # -----------------------------
    try:
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": new_filename,
            "attached_to_doctype": "Employee",
            "attached_to_name": user_id,
            "folder": "Home",
            "is_private": 0,
            # "content": file_content
            "content": corrected_file_content
        })
        file_doc.save(ignore_permissions=True)

        # Mark as registered (in case not already)
        frappe.db.set_value("Employee", user_id, "face_registered", 1)
        frappe.db.commit()

        return {"message": "updated"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Save Failed")
        return {"message": "update_failed"}
    finally:
        # 🧹 Clean up ALL temporary files
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    frappe.log(f"Deleted temporary file: {file_path}")
            except Exception as e:
                frappe.log_error(f"Failed to delete {file_path}: {str(e)}", "File Cleanup Error")
    
# @frappe.whitelist(allow_guest=True)
# def reset_face_registration(user_id):
#     ref_file_doc = get_employee_reference_image(user_id)
#     if not ref_file_doc:
#             return {"message": {"matched": False, "reason": "reference_image_missing"}}
#     upload_path_last = os.path.join(frappe.get_site_path('public', 'files'), ref_file_doc.file_name)

#     if not frappe.db.exists("Employee", user_id):
#         return {"message": "invalid_employee_id"}

#     frappe.db.set_value("Employee", user_id, "face_registered", 0)

#     # Optionally delete attachments
#     attachments = frappe.get_all("File", {
#         "attached_to_doctype": "Employee",
#         "attached_to_name": user_id
#     })
#     for a in attachments:
#         frappe.delete_doc("File", a.name, ignore_permissions=True)

#     frappe.db.commit()
#     os.remove(upload_path_last)  # Remove the last uploaded file
#     return {"message": "reset"}

@frappe.whitelist(allow_guest=True)
def reset_face_registration(user_id):
    """
    Resets the face registration for an employee by setting the flag to 0
    and deleting all associated face registration file attachments.
    """
    if not frappe.db.exists("Employee", user_id):
        return {"status": "error", "message": "invalid_employee_id"}

    # Set the registration flag to 0 (unregistered)
    frappe.db.set_value("Employee", user_id, "face_registered", 0)

    # Find all 'File' documents attached to this employee
    attachments = frappe.get_all("File", filters={
        "attached_to_doctype": "Employee",
        "attached_to_name": user_id
    }, fields=["name", "file_name"])

    if not attachments:
        frappe.db.commit()
        return {"status": "success", "message": "reset_but_no_attachments_found"}

    # Loop through and delete them using the Frappe API
    # This also handles deleting the physical file from the disk.
    for att in attachments:
        try:
            frappe.delete_doc("File", att.name, ignore_permissions=True, force=True)
            frappe.log_info(f"Deleted attachment {att.file_name} for employee {user_id}", "Face Registration Reset")
        except Exception as e:
            frappe.log_error(f"Failed to delete file doc {att.name}: {e}", "Face Registration Reset Error")
    
    # Commit all changes to the database
    frappe.db.commit()

    # <<< CHANGE >>>
    # The 'os.remove()' call has been removed as it is redundant and causes the error.
    # frappe.delete_doc() already handled the file deletion.
    
    return {"status": "success", "message": "face_registration_reset_successfully"}


@frappe.whitelist(allow_guest=True)
def match_face():
    temp_files = []  # Track all temporary files

    user_id = frappe.form_dict.get('user_id')
    latitude = frappe.form_dict.get('latitude')
    longitude = frappe.form_dict.get('longitude')
    device_id = frappe.form_dict.get('device_id')
    if not user_id:
        return {"message": {"matched": False, "reason": "missing_user_id"}}

    try:
        file = frappe.request.files['image']
        # filename = f'upload_{user_id}_{frappe.generate_hash(length=8)}.jpg'
        upload_path = os.path.join(frappe.get_site_path('public', 'files'), file.filename)

        # Read file content once and save it to disk
        file_content = file.read()
        with open(upload_path, 'wb') as f:
            f.write(file_content)
        temp_files.append(upload_path)  # Track this temporary file
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
        # ref_filename = f'reference_{user_id}.jpg'

        # Step 2: Fetch reference image from File doctype
        ref_file_doc = get_employee_reference_image(user_id)
        # frappe.log(ref_file_doc.file_name)
        # return
        if not ref_file_doc:
            return {"message": {"matched": False, "reason": "reference_image_missing"}}
        ref_image_path = os.path.join(frappe.get_site_path('public', 'files'), ref_file_doc.file_name)

        # if not correct_image_orientation(ref_image_path):
        #     return {"message": "image_processing_failed"}
        # return
         # ====== GET REFERENCE IMAGE FROM EMPLOYEE DOCTYPE ======
        # ref_image_path, ref_file_docname = get_employee_reference_image(user_id)

        # ✅ FIX: Properly validate ref_image_path before using os.path.exists()
        if not ref_image_path:
            frappe.log_error(f"Reference image path is None for {user_id}", "Face Matching")
            return {"message": {"matched": False, "reason": "reference_image_missing"}}
        
        if not os.path.exists(ref_image_path):
            frappe.log_error(f"Reference image file does not exist at path: {ref_image_path}", "Face Matching")
            return {"message": {"matched": False, "reason": "reference_image_file_not_found"}}

        # if not os.path.exists(ref_image_path):
        #     # This can happen if the file was manually deleted from the server
        #     # Attempt to regenerate it from the File doc content
        #     try:
        #         with open(ref_image_path, 'wb') as f:
        #             f.write(ref_file_doc.get_content())
        #         frappe.log_error(f"Reference image file was missing, regenerated at: {ref_image_path}", "Face Matching")
        #     except Exception as regen_e:
        #         frappe.log_error(f"Reference image file does not exist and could not be regenerated: {ref_image_path}, Error: {regen_e}", "Face Matching")
        #         return {"message": {"matched": False, "reason": "reference_image_file_not_found"}}
        
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
        if not match_result:
            # If face match fails, return early with confidence
            return {
                "message": {
                    "matched": False,
                    "distance": round(float(distance), 4),
                    "confidence": round(confidence, 1),
                    "reason": "face_not_matching"
                }
            }

        # If face match is successful, validate geofencing before saving
        if match_result and latitude and longitude:
            try:
                # Convert to floats
                latitude = float(latitude)
                longitude = float(longitude)
                
                # Get office coordinates from Employee document
                office_lat, office_long, geofence_radius = get_office_coordinates(user_id)
                
                # Check if coordinates are valid
                if not office_lat or not office_long:
                    return {
                        "message": {
                            "matched": True,
                            "distance": round(float(distance), 4),
                            "confidence": round(confidence, 1),
                            "checkin_saved": False,
                            "error": "office_coordinates_not_set"
                        }
                    }
                
                # Calculate distance from office
                distance_from_office = calculate_distance(
                    latitude, longitude, 
                    office_lat, office_long
                )
                
                # Check if within geofence radius
                if distance_from_office > geofence_radius:
                    return {
                        "message": {
                            "matched": True,
                            "distance": round(float(distance), 4),
                            "confidence": round(confidence, 1),
                            "checkin_saved": False,
                            "error": f"outside_geofence_radius",
                            "distance_from_office": round(distance_from_office, 3),
                            "geofence_radius": geofence_radius
                        }
                    }
                
                # Create checkin record (only if within geofence)
                checkin_doc = frappe.get_doc({
                    "doctype": "Employee Checkin",
                    "employee": user_id,
                    "time": frappe.utils.now_datetime(),
                    "device_id": device_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "location": f"{latitude}, {longitude}",
                    "skip_auto_attendance": 0,
                    "attendance": None,
                    "distance_from_office": round(distance_from_office, 3),
                    "confidence": round(confidence, 1)
                })
                checkin_doc.insert(ignore_permissions=True)
                frappe.db.commit()

                # Link the existing file to the Employee Checkin document
                # save_file(
                #     filename,
                #     file_content,
                #     "Employee Checkin",
                #     checkin_doc.name,
                #     folder="Home",
                #     is_private=0
                # )
                # frappe.db.commit()

                return {
                    "message": {
                        "matched": True,
                        "distance": round(float(distance), 4),
                        "confidence": round(confidence, 1),
                        "checkin_saved": True,
                        "checkin_name": checkin_doc.name,
                        "distance_from_office": round(distance_from_office, 3),
                        "geofence_radius": geofence_radius,
                        # "reference_image": ref_file_docname  # Return reference image doc name
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
        
        # Return confidence even when match fails (for debugging)
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
    finally:
        # 🧹 Clean up ALL temporary files
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    frappe.log(f"Deleted temporary file: {file_path}")
            except Exception as e:
                frappe.log_error(f"Failed to delete {file_path}: {str(e)}", "File Cleanup Error")

@frappe.whitelist(allow_guest=True)
def get_test_doc():
    try:
        doc = frappe.get_last_doc("ToDo")
        return {"name": doc.name, "description": doc.description}
    except:
        return {"error": "No ToDo documents found"}