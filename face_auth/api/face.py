import frappe
import os
import face_recognition
import numpy as np
from PIL import Image, ExifTags
import math
from datetime import datetime
from frappe.desk.form.load import get_attachments

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
    if not correct_image_orientation(save_path):
        return {"message": "image_processing_failed"}
    with open(save_path, 'rb') as f:
        corrected_file_content = f.read()

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
    temp_files = []  # Track all temporary files for cleanup

    user_id = frappe.form_dict.get('user_id')
    office_latitude = frappe.form_dict.get('office_latitude')
    office_longitude = frappe.form_dict.get('office_longitude')
    first_name = frappe.form_dict.get('first_name')  # First Name
    middle_name = frappe.form_dict.get('middle_name')  # Middle Name
    last_name = frappe.form_dict.get('last_name')  # Last Name
    radius_meters = frappe.form_dict.get('radius_meters')  # Radius (Meters)
    date_of_joining = frappe.form_dict.get('date_of_joining')  # date_of_joining (Meters)

    if not user_id:
        return {"message": "missing_user_id"}

    if not frappe.db.exists("Employee", user_id):
        return {"message": "invalid_employee_id"}

    # Get reference image for face comparison (assumes this function exists)
    ref_file_doc = get_employee_reference_image(user_id)
    if not ref_file_doc:
        return {"message": {"matched": False, "reason": "reference_image_missing"}}

    upload_path_last = os.path.join(frappe.get_site_path('public', 'files'), ref_file_doc.file_name)
    temp_files.append(upload_path_last)

    # Handle uploaded image
    file = frappe.request.files.get('image')
    if not file:
        return {"message": "no_image_provided"}

    filename_without_ext, ext = os.path.splitext(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    new_filename = f"{filename_without_ext}_{timestamp}{ext}"

    site_path = frappe.get_site_path('public', 'files')
    os.makedirs(site_path, exist_ok=True)
    save_path = os.path.join(site_path, new_filename)

    file_content = file.read()
    with open(save_path, 'wb') as f:
        f.write(file_content)
    temp_files.append(save_path)

    # Optional: Correct image orientation
    if not correct_image_orientation(save_path):
        return {"message": "image_processing_failed"}

    with open(save_path, 'rb') as f:
        corrected_file_content = f.read()

    # Face encoding
    try:
        image = face_recognition.load_image_file(save_path)
        encodings = face_recognition.face_encodings(image, num_jitters=1, model="large")
        if not encodings:
            return {"message": "no_face_detected"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Face Encoding Error")
        return {"message": "face_encoding_failed"}

    # Remove old attachments
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

    # Save new face image
    try:
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": new_filename,
            "attached_to_doctype": "Employee",
            "attached_to_name": user_id,
            "folder": "Home",
            "is_private": 0,
            "content": corrected_file_content
        })
        file_doc.save(ignore_permissions=True)

        # ✅ Update Employee document
        employee = frappe.get_doc("Employee", user_id)

        # Update fields from form data
        employee.first_name = first_name
        # employee.middle_name = middle_name
        employee.last_name = last_name
        employee.office_latitude = office_latitude
        employee.office_longitude = office_longitude
        employee.gender = "Male"
        # employee.radius_meters = radius_meters
        employee.date_of_joining = "2025-06-17"  # Mark as registered
        employee.date_of_birth = "1998-09-17"  # Mark as registered
        employee.status = "Active"  # Mark as registered
        employee.designation = "Software Developer"  # Mark as registered
        employee.department = "Accounts"  # Mark as registered
        # employee.first_name = first_name
        # employee.middle_name = middle_name
        # employee.last_name = last_name
        # employee.office_latitude = office_latitude
        # employee.office_longitude = office_longitude
        # employee.radius_meters = radius_meters
        # employee.date_of_joining = "2025-06-17"  # Mark as registered
        employee.face_registered = 1  # Mark as registered
        
        # Save the Employee document
        employee.save(ignore_permissions=True)
        frappe.db.commit()

        # designation = frappe.get_doc({
        # "doctype": "Designation",
        # "designation_name": "Software Developer"
        # })
        # designation.designation_name = "Software Developer"
        # designation = frappe.get_doc("Designation", user_id)
        # designation.designation_name = "Software Developer"

        # designation.save(ignore_permissions=True)
        # frappe.db.commit()
        return {"message": "updated"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Save Failed")
        return {"message": "update_failed"}

    finally:
        # Clean up temporary files
        for file_path in temp_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    frappe.log(f"Deleted temporary file: {file_path}")
            except Exception as e:
                frappe.log_error(f"Failed to delete {file_path}: {str(e)}", "File Cleanup Error")
    
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
    
    frappe.db.commit()
    
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


        ref_file_doc = get_employee_reference_image(user_id)
        if not ref_file_doc:
            return {"message": {"matched": False, "reason": "reference_image_missing"}}
        ref_image_path = os.path.join(frappe.get_site_path('public', 'files'), ref_file_doc.file_name)

        # ✅ FIX: Properly validate ref_image_path before using os.path.exists()
        if not ref_image_path:
            frappe.log_error(f"Reference image path is None for {user_id}", "Face Matching")
            return {"message": {"matched": False, "reason": "reference_image_missing"}}
        
        if not os.path.exists(ref_image_path):
            frappe.log_error(f"Reference image file does not exist at path: {ref_image_path}", "Face Matching")
            return {"message": {"matched": False, "reason": "reference_image_file_not_found"}}

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
def track_location():
    # frappe.log("Tracking location for employee")
    """
    Track real-time GPS location of employee.
    Requires authentication.
    """
    # user = frappe.session.user  # Authenticated user
    employee_id = frappe.form_dict.get('employee_id')
    # frappe.log(f"Tracking location for employee: {employee_id}")
    latitude = frappe.form_dict.get('latitude')
    longitude = frappe.form_dict.get('longitude')
    # battery_level = frappe.form_dict.get('battery_level')
    # accuracy = frappe.form_dict.get('accuracy')  # GPS accuracy in meters
    # location_type = frappe.form_dict.get('location_type', 'Live Tracking')  # e.g., Check-in, Check-out

    # Validate
    if not employee_id:
        frappe.throw(_("Employee ID is required"))

    if not frappe.db.exists("Employee", employee_id):
        frappe.throw(_("Invalid Employee ID"))

    if not latitude or not longitude:
        frappe.throw(_("Latitude and Longitude are required"))

    try:
        # Create Location log
        location = frappe.get_doc({
            "doctype": "Location",
            "location_name": f"Track-{employee_id}-{frappe.utils.now()}",  # auto-naming
            "latitude": float(latitude),
            "longitude": float(longitude),
            "employee": employee_id,
            # "user": user,
            "custom_timestamp": frappe.utils.now_datetime(),
            # "battery_level": battery_level,
            # "accuracy": accuracy,
            # "location_type": location_type
        })
        location.insert(ignore_permissions=True)  # Bypass permission checks

        # Optional: Update Employee last known location
        # employee = frappe.get_doc("Employee", employee_id)
        # employee.last_known_latitude = latitude
        # employee.last_known_longitude = longitude
        # employee.last_location_update = frappe.utils.now_datetime()
        # employee.db_update()  # Only updates DB, skips full save

        frappe.db.commit()

        return {
            "message": "location_tracked",
            "location": location.name,
            "timestamp": location.custom_timestamp
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Location Tracking Failed")
        frappe.throw(_("Failed to track location"))

# @frappe.whitelist(allow_guest=True)
# def get_latest_locations():
#     # Get latest location for all employees
#     return frappe.db.sql("""
#         SELECT employee, latitude, longitude, timestamp
#         FROM `tabEmployee Location Log`
#         WHERE timestamp = (
#             SELECT MAX(timestamp) FROM `tabEmployee Location Log` AS sub
#             WHERE sub.employee = `tabEmployee Location Log`.employee
#         )
#     """, as_dict=True)

@frappe.whitelist(allow_guest=True)
def get_historical_path(employee, date):
    start = f"{date} 09:00:00"
    end = f"{date} 18:00:00"
    return frappe.get_all("Location",
        filters=[["employee", "=", employee], ["custom_timestamp", "between", [start, end]]],
        fields=["latitude", "longitude", "custom_timestamp"],
        order_by="custom_timestamp asc"
    )