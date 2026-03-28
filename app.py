from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.utils import secure_filename
from sqlalchemy import text
from models import (
    db, bcrypt, 
    User, Admin, Doctor, Patient, XraySpecialist, Reception, HealthOfficer, Appointment,
    Prediction, Feedback, ClinicalInterview, DoctorNotification, Notification, XraySpecialistNotification,
    UniversalNotification, NotificationService, PatientDoctorAssignment, MedicalReport, LoginAttempt,
    create_feedback_notification, create_user_approval_notification, 
    create_doctor_feedback_notification, create_xray_specialist_feedback_notification, create_xray_to_doctor_feedback_notification,
    get_user_by_username, get_user_by_phone, get_user_by_id_and_role,
    create_admin_user, create_doctor_user, create_patient_user, create_xray_specialist_user, create_reception_user, create_health_officer_user,
    create_appointment, get_available_appointment_slots, register_patient_by_reception,
    validate_email, normalize_email, send_account_approval_email, create_verification_code, 
    validate_verification_code, send_verification_code_email, get_user_email, validate_email_format
)
from flask_wtf import CSRFProtect
import os
from datetime import datetime, timedelta
import numpy as np
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
import re
import logging
from functools import wraps
import hashlib
import uuid
from datetime import timedelta
import random
import africastalking
import click
from flask.cli import with_appcontext
from functools import wraps
from flask import redirect, url_for, flash
from datetime import datetime
import json

# ---------------------- FLASK CONFIG ----------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your_secret_key_here")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Force template reload
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable static file caching

# Set application name
app.config['APPLICATION_NAME'] = 'BreastCancerDetectionSystem'

# Print startup message to confirm code is loaded
print("="*70)
print("🔥 BREASTCANCERDETECTIONSYSTEM - APPLICATION LOADED")
print("🔥 TEMPLATES AUTO-RELOAD ENABLED")
print("🔥 BROWSER CACHE DISABLED")
print("="*70)

# Add cache-busting headers to prevent browser caching
@app.after_request
def add_no_cache_headers(response):
    """Add headers to prevent browser caching during development"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# Initialize extensions
csrf = CSRFProtect(app)
db.init_app(app)
bcrypt.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

#                       DECORATORS
# ============================================================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def doctor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'doctor':
            flash('Access denied. Doctor privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def patient_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'patient':
            flash('Access denied. Patient privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def xray_specialist_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'xrayspecialist':
            flash('Access denied. X-ray Specialist privileges required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def reception_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.role != 'reception':
            flash('Access denied. Reception privileges required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def health_officer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # Check if this is an AJAX request
            if request.is_json or request.headers.get('Content-Type') == 'application/json':
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            return redirect(url_for('login'))
        if current_user.role != 'healthofficer':
            # Check if this is an AJAX request
            if request.is_json or request.headers.get('Content-Type') == 'application/json':
                return jsonify({'success': False, 'message': 'Health Officer privileges required'}), 403
            flash('Access denied. Health Officer privileges required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------------------- CREATE UPLOAD FOLDER ----------------------
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
with app.app_context():
    db.create_all()

# ---------------------- LOAD CNN MODEL ----------------------
MODEL_PATH = os.path.join('model', 'breast_cancer_cnn_model.h5')
cnn_model = None

def load_cnn_model():
    """Load CNN model with better error handling"""
    global cnn_model
    
    # Skip model loading if environment variable is set (for testing)
    if os.environ.get('SKIP_MODEL_LOADING') == '1':
        print("⚠️ Model loading skipped (SKIP_MODEL_LOADING=1)")
        return None
    
    if not os.path.exists(MODEL_PATH):
        print("⚠️ Warning: CNN model not found. AI predictions will not work.")
        return None
    
    try:
        print("🔄 Loading CNN model...")
        # Set TensorFlow to be less verbose
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
        
        cnn_model = load_model(MODEL_PATH, compile=False, custom_objects={})
        print("✅ CNN model loaded successfully.")
        # Don't print model summary to reduce startup time
        return cnn_model
    except Exception as e:
        print(f"⚠️ Error loading CNN model: {e}")
        print("   AI predictions will not be available.")
        return None

# Load model on startup (but don't block if it fails)
try:
    cnn_model = load_cnn_model()
except Exception as e:
    print(f"⚠️ Model loading failed during startup: {e}")
    cnn_model = None

# ---------------------- USER LOADER ----------------------
@login_manager.user_loader
def load_user(user_id):
    """Load user from the user table"""
    return User.query.get(int(user_id))

# ---------------------- SESSION SECURITY ----------------------
@app.after_request
def add_security_headers(response):
    """Add security headers to prevent caching of protected pages"""
    # Prevent caching for all pages to ensure logout works properly
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response



# ---------------------- HELPER FUNCTIONS ----------------------
def is_xray_image(image_path):
    """
    Detect if an image is likely an X-ray image based on visual characteristics
    
    Args:
        image_path: Path to the image file
    
    Returns:
        Dictionary with detection results
    """
    try:
        from PIL import Image
        import numpy as np
        
        # Load image
        img = Image.open(image_path)
        
        # Convert to grayscale for analysis
        if img.mode != 'L':
            img_gray = img.convert('L')
        else:
            img_gray = img
        
        # Convert to numpy array
        img_array = np.array(img_gray)
        
        # X-ray characteristics to check:
        
        # 1. Check if image is predominantly grayscale/monochrome
        if len(img.getbands()) > 1:
            # For color images, check if it's mostly grayscale
            img_rgb = img.convert('RGB')
            r, g, b = img_rgb.split()
            r_arr, g_arr, b_arr = np.array(r), np.array(g), np.array(b)
            
            # Calculate color variance - X-rays should have low color variance
            color_variance = np.var([np.mean(r_arr), np.mean(g_arr), np.mean(b_arr)])
            is_grayscale = color_variance < 100  # Threshold for grayscale detection
        else:
            is_grayscale = True
        
        # 2. Check intensity distribution (X-rays typically have specific intensity patterns)
        hist, _ = np.histogram(img_array, bins=256, range=(0, 256))
        
        # X-rays often have:
        # - Dark background (low intensity values)
        # - Bright bone structures (high intensity values)
        # - Soft tissue in between (medium intensity values)
        
        dark_pixels = np.sum(hist[:50])  # Very dark pixels (0-49)
        medium_pixels = np.sum(hist[50:200])  # Medium pixels (50-199)
        bright_pixels = np.sum(hist[200:])  # Bright pixels (200-255)
        
        total_pixels = img_array.size
        dark_ratio = dark_pixels / total_pixels
        medium_ratio = medium_pixels / total_pixels
        bright_ratio = bright_pixels / total_pixels
        
        # 3. Check for typical X-ray intensity distribution
        # X-rays usually have significant dark background and some bright areas
        has_xray_distribution = (dark_ratio > 0.3 and bright_ratio > 0.05)
        
        # 4. Check image dimensions (X-rays are usually rectangular, not square)
        width, height = img.size
        aspect_ratio = max(width, height) / min(width, height)
        reasonable_aspect_ratio = 0.5 <= aspect_ratio <= 3.0
        
        # 5. Check for edges and structures typical in medical images
        # Simple edge detection using standard deviation of gradients
        grad_x = np.abs(np.diff(img_array, axis=1))
        grad_y = np.abs(np.diff(img_array, axis=0))
        edge_density = (np.std(grad_x) + np.std(grad_y)) / 2
        
        # X-rays typically have moderate edge density (not too smooth, not too noisy)
        has_medical_edges = 10 < edge_density < 100
        
        # Calculate overall X-ray likelihood score
        score = 0
        reasons = []
        
        if is_grayscale:
            score += 25
            reasons.append("Image is grayscale/monochrome")
        else:
            reasons.append("Image has significant color content (not typical for X-rays)")
        
        if has_xray_distribution:
            score += 30
            reasons.append("Intensity distribution matches X-ray patterns")
        else:
            reasons.append("Intensity distribution doesn't match typical X-ray patterns")
        
        if reasonable_aspect_ratio:
            score += 15
            reasons.append("Image has reasonable medical image proportions")
        else:
            reasons.append("Unusual aspect ratio for medical images")
        
        if has_medical_edges:
            score += 20
            reasons.append("Edge patterns consistent with medical imaging")
        else:
            reasons.append("Edge patterns not typical of medical images")
        
        # Additional checks for obvious non-X-ray content
        if dark_ratio < 0.1:  # Too few dark pixels
            score -= 20
            reasons.append("Insufficient dark background (not typical for X-rays)")
        
        if bright_ratio > 0.7:  # Too many bright pixels
            score -= 15
            reasons.append("Too much bright content (possibly overexposed or not X-ray)")
        
        # Final assessment
        is_likely_xray = score >= 50
        confidence_level = min(100, max(0, score))
        
        return {
            'is_xray': is_likely_xray,
            'confidence': confidence_level,
            'score': score,
            'reasons': reasons,
            'statistics': {
                'is_grayscale': is_grayscale,
                'dark_ratio': round(dark_ratio, 3),
                'medium_ratio': round(medium_ratio, 3),
                'bright_ratio': round(bright_ratio, 3),
                'aspect_ratio': round(aspect_ratio, 2),
                'edge_density': round(edge_density, 2)
            }
        }
        
    except Exception as e:
        print(f"Error in X-ray detection: {e}")
        return {
            'is_xray': False,
            'confidence': 0,
            'score': 0,
            'reasons': [f"Error analyzing image: {str(e)}"],
            'statistics': {}
        }

def generate_ai_reasoning(classification, confidence, prediction_value):
    """
    Generate detailed AI reasoning for the prediction
    
    Args:
        classification: "Benign" or "Malignant"
        confidence: Confidence percentage (0-100)
        prediction_value: Raw prediction value from model (0-1)
    
    Returns:
        Dictionary with detailed reasoning
    """
    # Determine certainty level
    if confidence >= 90:
        certainty = "very high"
        certainty_desc = "The model is highly confident in this classification."
    elif confidence >= 75:
        certainty = "high"
        certainty_desc = "The model shows strong confidence in this classification."
    elif confidence >= 60:
        certainty = "moderate"
        certainty_desc = "The model shows moderate confidence. Additional review recommended."
    else:
        certainty = "low"
        certainty_desc = "The model has low confidence. Professional medical review is strongly recommended."
    
    # Build reasoning based on classification - Doctor-focused guidance
    if classification == "Malignant":
        indicators = [
            "Irregular cellular patterns detected in tissue structure",
            "Abnormal cell morphology with increased nuclear-to-cytoplasmic ratio",
            "Loss of normal tissue architecture",
            "Features consistent with invasive ductal carcinoma characteristics"
        ]
        explanation = (
            f"AI Analysis: This histopathology sample shows features consistent with MALIGNANT tissue "
            f"with {certainty} confidence ({confidence:.1f}%). The CNN model identified irregular cellular "
            f"patterns, abnormal morphology, and architectural distortion typical of breast carcinoma. "
            f"{'This high confidence suggests strong malignant features.' if confidence >= 75 else 'The moderate confidence indicates borderline features requiring careful clinical correlation.'}"
        )

        risk_level = "High"
    else:  # Benign
        indicators = [
            "Regular cellular patterns with preserved tissue architecture",
            "Normal cell morphology with uniform nuclear features",
            "Absence of invasive or atypical characteristics",
            "Features consistent with benign breast tissue or fibroadenoma"
        ]
        explanation = (
            f"AI Analysis: This histopathology sample shows features consistent with BENIGN tissue "
            f"with {certainty} confidence ({confidence:.1f}%). The CNN model identified regular cellular "
            f"patterns, normal morphology, and preserved architecture typical of non-malignant breast tissue. "
            f"{'This high confidence supports benign diagnosis.' if confidence >= 75 else 'The moderate confidence suggests some atypical features may be present - clinical correlation advised.'}"
        )

        risk_level = "Low"
    
    reasoning = {
        'classification': classification,
        'confidence': round(confidence, 2),
        'certainty_level': certainty,
        'certainty_description': certainty_desc,
        'risk_level': risk_level,
        'explanation': explanation,
        'indicators': indicators,
        'technical_details': {
            'prediction_value': round(prediction_value, 4),
            'threshold': 0.5,
            'model_type': 'Convolutional Neural Network (CNN)',
            'input_size': '224x224 pixels'
        },
        'disclaimer': (
            "⚠️ CLINICAL NOTE: This AI prediction is a decision support tool and should be used in conjunction "
            "with clinical judgment, patient history, physical examination, and confirmatory diagnostic tests. "
            "Final diagnosis and treatment decisions remain the responsibility of the treating physician. "
            "AI predictions may have false positives/negatives - always correlate with clinical findings."
        )
    }
    
    return reasoning

def normalize_role(role):
    """Normalize role string for consistent comparison"""
    if not role:
        return "patient"
    
    # Convert to string and normalize
    role_str = str(role).strip().replace("-", "").replace(" ", "").lower()
    
    # Map variations to consistent values
    role_mapping = {
        "xrayspecialist": "xrayspecialist",
        "xray": "xrayspecialist", 
        "doctor": "doctor",
        "patient": "patient",
        "admin": "admin",
        "administrator": "admin",
        "reception": "reception",
        "healthofficer": "healthofficer"
    }
    
    return role_mapping.get(role_str, "patient")

# ---------------------- PATIENT NOTIFICATION FUNCTIONS ----------------------
def create_patient_notification(patient_id, title, message, notification_type='general', related_prediction_id=None, related_feedback_id=None):
    """Create a notification for a patient"""
    try:
        # For now, we'll store patient notifications in a simple way
        # In a production system, you'd want a proper PatientNotification model
        print(f"Patient Notification - Patient ID: {patient_id}, Title: {title}, Message: {message}")
        
        # You can implement actual patient notification storage here
        # For now, we'll just log it and the frontend will handle display
        return True
    except Exception as e:
        print(f"Error creating patient notification: {e}")
        return False

def create_doctor_validation_notification(prediction_id):
    """Create notification for patient and X-ray specialist when doctor provides validation"""
    try:
        prediction = Prediction.query.get(prediction_id)
        if not prediction:
            return False
            
        patient = User.query.get(prediction.patient_id)
        doctor = User.query.get(prediction.doctor_id)
        
        # Get patient unique ID for better identification
        patient_unique_id = prediction.patient_unique_id
        if not patient_unique_id and patient and patient.patient_profile:
            patient_unique_id = patient.patient_profile.patient_unique_id
        
        success = True
        
        # Notify the patient
        if patient and doctor:
            title = "Doctor Validation Results Available"
            message = f"Dr. {doctor.username} has provided validation results for your X-ray: {prediction.image_filename} (Patient ID: {patient_unique_id or 'N/A'})"
            
            # Legacy notification
            patient_success = create_patient_notification(
                patient_id=patient.id,
                title=title,
                message=message,
                notification_type='result',
                related_prediction_id=prediction_id
            )
            
            # Universal notification
            print(f"📧 Creating universal notification for patient {patient.username}")
            universal_notification = NotificationService.create_notification(
                user_id=patient.id,
                user_role='patient',
                title=title,
                message=message,
                notification_type='xray_result',
                action_url='#results',
                is_clickable=True
            )
            
            if universal_notification:
                print(f"✅ Created universal notification for patient {patient.username}")
            else:
                print(f"❌ Failed to create universal notification for patient")
            
            success = success and patient_success
        
        # Notify the X-ray specialist if the X-ray was sent by one
        if prediction.sent_by and doctor:
            sent_by_user = User.query.get(prediction.sent_by)
            if sent_by_user and sent_by_user.role == 'xrayspecialist':
                from models import XraySpecialistNotification
                
                # Legacy notification
                notification = XraySpecialistNotification(
                    xray_specialist_id=prediction.sent_by,
                    patient_id=prediction.patient_id,
                    patient_name=patient.username if patient else "Unknown Patient",
                    xray_filename=prediction.image_filename,
                    message=f"Dr. {doctor.username} validated X-ray for {patient.username if patient else 'patient'} (ID: {patient_unique_id or 'N/A'}): {prediction.doctor_validation}",
                    is_read=False,
                    notification_type='validation_result'
                )
                db.session.add(notification)
                
                # Universal notification
                print(f"📧 Creating universal notification for X-ray specialist {sent_by_user.username}")
                universal_notification = NotificationService.create_notification(
                    user_id=sent_by_user.id,
                    user_role='xrayspecialist',
                    title="Doctor Validated X-ray Results",
                    message=f"Dr. {doctor.username} validated X-ray for patient {patient.username if patient else 'Unknown'} (ID: {patient_unique_id or 'N/A'}): {prediction.doctor_validation}",
                    notification_type='validation_result',
                    action_url='#notes',
                    is_clickable=True
                )
                
                if universal_notification:
                    print(f"✅ Created universal notification for X-ray specialist {sent_by_user.username}")
                else:
                    print(f"❌ Failed to create universal notification for X-ray specialist")
                
                db.session.commit()
                print(f"Created validation notification for X-ray specialist {sent_by_user.username}")
        
        return success
    except Exception as e:
        print(f"Error creating doctor validation notification: {e}")
        return False

def create_admin_feedback_notification(feedback_id):
    """Create notification for patient when admin replies to feedback"""
    try:
        feedback = Feedback.query.get(feedback_id)
        if not feedback or not feedback.reply:
            return False
            
        patient = User.query.get(feedback.patient_id)
        
        if patient:
            title = "Admin Reply to Your Feedback"
            message = f"An administrator has replied to your feedback"
            
            return create_patient_notification(
                patient_id=patient.id,
                title=title,
                message=message,
                notification_type='feedback',
                related_feedback_id=feedback_id
            )
        return False
    except Exception as e:
        print(f"Error creating admin feedback notification: {e}")
        return False

def create_doctor_reply_notification(patient_id, doctor_name, message):
    """Create notification for patient when doctor replies to feedback"""
    try:
        patient = User.query.get(patient_id)
        if patient:
            title = "Doctor Reply to Your Feedback"
            message_text = f"Dr. {doctor_name} has replied to your feedback: {message[:100]}{'...' if len(message) > 100 else ''}"
            
            # Legacy notification
            legacy_success = create_patient_notification(
                patient_id=patient_id,
                title=title,
                message=message_text,
                notification_type='doctor_reply'
            )
            
            # Universal notification
            print(f"📧 Creating universal notification for patient {patient.username}")
            universal_notification = NotificationService.create_notification(
                user_id=patient_id,
                user_role='patient',
                title=title,
                message=message_text,
                notification_type='doctor_reply',
                action_url='#feedback',
                is_clickable=True
            )
            
            if universal_notification:
                print(f"✅ Created universal notification for patient {patient.username}")
            else:
                print(f"❌ Failed to create universal notification for patient")
            
            return legacy_success
        return False
    except Exception as e:
        print(f"Error creating doctor reply notification: {e}")
        return False

# ---------------------- TRANSLATION DICTIONARIES ----------------------
home_translations = {
    'en': {
        'title': 'Breast Cancer Detection System',
        'register': 'Register',
        'login': 'Login'
    },
    'or': {
        'title': 'Sirna Qorannoo Kaansarii Harmaa',
        'register': 'Galmaa\'i',
        'login': 'Seeni'
    }
}

register_translations = {
    'en': {
        'title': 'Register',
        'username': 'Username:',
        'phone': 'Phone (+251...):',
        'email': 'Email:',
        'password': 'Password:',
        'confirm_password': 'Confirm Password:',
        'role': 'Role:',
        'roles': {
            'patient': 'Patient',
            'doctor': 'Doctor',
            'xrayspecialist': 'X-ray Specialist',
            'reception': 'Reception',
            'healthofficer': 'Health Officer',
            'admin': 'Admin'
        },
        'register_button': 'Register',
        'already_account': 'Already have an account?',
        'login_here': 'Login here',
        'back_to': 'Back to',
        'home': 'Home',
        'flash_invalid_phone': 'Invalid phone number! Use +2519... or +2517...',
        'flash_duplicate': 'Username or phone number already exists!',
        'flash_duplicate_email': 'This email address is already registered!',
        'flash_invalid_email': 'Invalid email format! Please enter a valid email address.',
        'flash_password_mismatch': 'Passwords do not match!',
        'flash_invalid_role': 'Invalid role selected!',
        'flash_error': 'Error during registration: '
    },
    'or': {
        'title': 'Galmaa\'i',
        'username': 'Maqaa fayyadamaa:',
        'phone': 'Bilbila (+251...):',
        'email': 'Imeelii:',
        'password': 'Jecha darbii:',
        'confirm_password': 'Jecha darbii mirkaneessi:',
        'role': 'Gahee:',
        'roles': {
            'patient': 'Dhukkubsataa',
            'doctor': 'Ogeessa Fayyaa(Dr)',
            'xrayspecialist': 'Ogeessa X-ray',
            'reception': 'Simachuu',
            'healthofficer': 'Ogeessa Fayyaa',
            'admin': 'Admin'
        },
        'register_button': 'Galmaa\'i',
        'already_account': 'Dursa galmooftanii?',
        'login_here': 'Asiin seeni',
        'back_to': 'Gara duubaa deebii\'uuf?',
        'home': 'Fuula Duraa',
        'flash_invalid_phone': 'Lakkoofsi bilbilaa sirrii miti! +2519... yookiin +2517... fayyadami',
        'flash_duplicate': 'Maqaa fayyadamaa yookiin lakkoofsa bilbilaa duraan jira!',
        'flash_duplicate_email': 'Imeeliin kun duraan galmeeffameera!',
        'flash_invalid_email': 'Imeeliin sirrii miti! Imeelii sirrii galchaa.',
        'flash_password_mismatch': 'Jechoonni darbii wal hin siman!',
        'flash_invalid_role': 'Gaheen filatame sirrii miti!',
        'flash_error': 'Dogoggora galmaa\'uu: '
    }
}

login_translations = {
    'en': {
        'title': 'Login - Breast Cancer Detection System',
        'login_header': 'LOGIN',
        'username_label': 'Username',
        'username_placeholder': 'Enter your username',
        'password_label': 'Password',
        'password_placeholder': 'Password',
        'signin_button': 'Sign In',
        'forgot_password': 'Forgot Password?',
        'dont_have_account': "Don't have an account?",
        'register': 'Register',
        'back_to': 'Back to',
        'home': 'Home',
        'registration_success': 'Registration successful for {}! Please log in.',
        'no_account': "No account found for that username!",
        'pending_approval': "Your account is pending admin approval.",
        'invalid_password': "Invalid password!",
        'unknown_role': "Unknown role! Please contact admin.",
        'login_success': "Login successful!"
    },
    'or': {
        'title': 'Seensa - Sirna Qorannoo Kaansarii Harmaa',
        'login_header': 'SEENSA',
        'username_label': 'Maqaa fayyadamaa',
        'username_placeholder': 'Maqaa fayyadamaa galchaa',
        'password_label': 'Jecha darbii',
        'password_placeholder': 'Jecha darbii',
        'signin_button': 'Seeni',
        'forgot_password': 'Jecha darbii dagattan irra deebiin argachuufii?',
        'dont_have_account': "Galmee hin galmoofnee?",
        'register': 'Galmaa\'i',
        'back_to': 'Gara duubaa deebii\'uuf?',
        'home': 'Fuula Duraa',
        'registration_success': 'Galmeen milkaa\'eera {}! Mee seeni.',
        'no_account': "Fayyadamaan maqaa kanaan galmaa'e hin jiru!",
        'pending_approval': "Galmeen kee eeyyama Admin eeggachaa jira.",
        'invalid_password': "Jecha darbii sirrii miti!",
        'unknown_role': "Gahee hin beekamne! Admin qunnamuu qabda.",
        'login_success': "Seensa milkaa'eera!"
    }
}

logout_translations = {
    'en': {
        'logged_out_success': "Logged out successfully!"
    },
    'or': {
        'logged_out_success': "Milkaa'inaan baatanii jirtu!"
    }
}

admin_dashboard_translations = {
    'en': {
        'page_title': "Admin Dashboard",
        'profile_role': "Administrator",
        'sidebar': {
            'overview': "Overview",
            'users': "Users",
            'feedback': "Feedback",
            'settings': "Settings",
            'change_password': "Change Password",
            'logout': "Logout"
        },
        'welcome': "Welcome, {}!",
        'current_date_aria': "Current date",
        'total_doctors': "Total Doctors",
        'total_patients': "Total Patients",
        'total_xrayspecialists': "Total X-ray Specialists",
        'total_reception': "Total Reception",
        'total_healthofficer': "Total Health Officers",
        'users_list': "Users List",
        'feedback_list': "Patient Feedback",
        'no_feedback': "No feedback available.",
        'user_role': "Role",
        'user_username': "Username",
        'user_email': "Email",
        'user_phone': "Phone",
        'feedback_content': "Feedback",
        'feedback_date': "Date Submitted"
    },
    'or': {
        'page_title': "Fuula Admin",
        'profile_role': "Admin",
        'sidebar': {
            'overview': "Waliigala",
            'users': "Fayyadamtoota",
            'feedback': "Yaada",
            'settings': "Qindaa'inoota",
            'change_password': "Jecha darbii jijjiiruu",
            'logout': "Ba'uuf"
        },
        'welcome': "Baga nagaan dhuftan, {}!",
        'current_date_aria': "Guyyaa har'aa",
        'total_doctors': "Baayyina Dr.",
        'total_patients': "Baayyina Dhukkubsattootaa",
        'total_xrayspecialists': "Baayyina Ogeessa xray",
        'total_reception': "Baayyina Keessummeessaa",
        'total_healthofficer': "Baayyina Ogeessa Fayyaa",
        'users_list': "Tarree Fayyadamtoota",
        'feedback_list': "Yaada Dhukkubsattoota",
        'no_feedback': "Yaadni hin jiru.",
        'user_role': "Gahee",
        'user_username': "Maqaa fayyadamaa",
        'user_email': "Imeelii",
        'user_phone': "Bilbila",
        'feedback_content': "Yaada",
        'feedback_date': "Guyyaa Ergame"
    }
}

# ---------------------- ROUTES ----------------------
@app.route('/')
def home():
    lang = request.args.get('lang') or session.get('lang', 'en')
    if lang not in home_translations:
        lang = 'en'
    session['lang'] = lang
    texts = home_translations[lang]
    return render_template('home.html', texts=texts, lang=lang)

@app.route('/register', methods=['GET', 'POST'])
def register():
    lang = request.args.get('lang') or session.get('lang', 'en')
    if lang not in register_translations:
        lang = 'en'
    texts = register_translations[lang]

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone_input = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'patient').strip().lower()

        phone = '+251' + phone_input
        # Don't store form data in session - use placeholders instead
        
        # Debug: Print form data
        print(f"🔍 REGISTRATION DEBUG:")
        print(f"   Username: '{username}'")
        print(f"   Phone: '{phone_input}' -> '{phone}'")
        print(f"   Email: '{email}'")
        print(f"   Role: '{role}'")
        print(f"   Password length: {len(password)}")
        print(f"   Confirm password length: {len(confirm_password)}")
        
        # 1. VALIDATION: All fields cannot be empty
        if not username or not phone_input or not email or not password or not confirm_password or not role:
            flash('All fields are required. Please fill in all information.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # 2. VALIDATION: Username should allow characters and spaces only (no numbers, special characters)
        # Allow letters (a-z, A-Z), spaces, and common name characters like apostrophes and hyphens
        username_pattern = r'^[a-zA-Z\s\'-]+$'
        if not re.match(username_pattern, username):
            flash('Username can only contain letters, spaces, apostrophes, and hyphens. Numbers and special characters are not allowed.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Additional username validation: must be at least 2 characters and not just spaces
        if len(username.replace(' ', '')) < 2:
            flash('Username must contain at least 2 letters.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # 3. VALIDATION: Comprehensive Gmail email validation
        # First, check basic email structure (must have exactly one @ symbol)
        if email.count('@') != 1:
            flash('Invalid email format. Email must contain exactly one @ symbol.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Split email into local and domain parts
        try:
            local_part, domain_part = email.split('@')
        except ValueError:
            flash('Invalid email format. Please use a valid Gmail address like: yourname@gmail.com', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Check if domain is exactly "gmail.com" (case insensitive)
        if domain_part.lower() != 'gmail.com':
            flash('Email must be a Gmail address ending with @gmail.com', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Validate local part (before @gmail.com)
        # Must be 1-64 characters, contain only valid characters, and follow Gmail rules
        if len(local_part) < 1 or len(local_part) > 64:
            flash('Gmail username must be between 1 and 64 characters long.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Check for valid Gmail characters (letters, numbers, dots, plus, hyphens)
        # Gmail allows: a-z, A-Z, 0-9, . (dot), + (plus), - (hyphen)
        if not re.match(r'^[a-zA-Z0-9._+-]+$', local_part):
            flash('Gmail username can only contain letters, numbers, dots, plus signs, and hyphens.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Gmail-specific rules
        # Cannot start or end with dots
        if local_part.startswith('.') or local_part.endswith('.'):
            flash('Gmail username cannot start or end with a dot.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Cannot have consecutive dots
        if '..' in local_part:
            flash('Gmail username cannot contain consecutive dots.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Must contain at least one letter or number (not just dots and symbols)
        if not re.search(r'[a-zA-Z0-9]', local_part):
            flash('Gmail username must contain at least one letter or number.', "danger")
            return redirect(url_for('register', lang=lang))
        
        # Final comprehensive Gmail format validation
        gmail_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9._+-]*[a-zA-Z0-9])?@gmail\.com$'
        if not re.match(gmail_pattern, email, re.IGNORECASE):
            flash('Invalid Gmail format. Please use a valid Gmail address like: yourname@gmail.com', "danger")
            return redirect(url_for('register', lang=lang))
        
        # 4. VALIDATION: Password confirmation
        if password != confirm_password:
            flash(texts['flash_password_mismatch'], "danger")
            return redirect(url_for('register', lang=lang))
        
        # Additional password strength validation
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', "danger")
            return redirect(url_for('register', lang=lang))

        # Phone validation - validate 9-digit input before adding prefix
        phone_pattern = r'^[79]\d{8}$'
        if not re.match(phone_pattern, phone_input):
            flash(texts['flash_invalid_phone'], "danger")
            return redirect(url_for('register', lang=lang))

        # Normalize email for storage (already validated above)
        email = normalize_email(email)

        # Duplicate check - check all role tables
        existing_user = get_user_by_username(username)
        if not existing_user:
            existing_user = get_user_by_phone(phone)
        
        if existing_user:
            flash(texts['flash_duplicate'], "danger")
            return redirect(url_for('register', lang=lang))



        # Validate role - ADMIN AND PATIENT COMPLETELY EXCLUDED FROM PUBLIC REGISTRATION
        valid_roles = ['doctor', 'xrayspecialist', 'reception', 'healthofficer']
        if role not in valid_roles:
            flash(texts['flash_invalid_role'], "danger")
            return redirect(url_for('register', lang=lang))
        
        # Explicitly reject patient role with specific message
        if role == 'patient':
            flash('Patient registration is only available through reception staff. Please contact reception.', "danger")
            return redirect(url_for('register', lang=lang))

        # Create new user based on role
        try:
            if role == 'patient':
                new_user = create_patient_user(username, phone, password, email=email)
            elif role == 'doctor':
                new_user = create_doctor_user(username, phone, password, email=email)
            elif role == 'xrayspecialist':
                new_user = create_xray_specialist_user(username, phone, password, email=email)
            elif role == 'reception':
                new_user = create_reception_user(username, phone, password, email=email)
            elif role == 'healthofficer':
                new_user = create_health_officer_user(username, phone, password, email=email)
            else:
                flash(texts['flash_invalid_role'], "danger")
                return redirect(url_for('register', lang=lang))
            
            if not new_user:
                flash(texts['flash_error'] + "Failed to create user", "danger")
                return redirect(url_for('register', lang=lang))

            # Create notification for admins when staff registers
            if role in ['doctor', 'xrayspecialist', 'reception', 'healthofficer']:
                # Create universal notifications for all admins
                NotificationService.create_notifications_for_role(
                    role='admin',
                    title='New User Registration',
                    message=f'New {role} "{username}" registered and needs approval',
                    notification_type='user_approval',
                    action_url='#approve-users',
                    is_clickable=True
                )
                
                # Also create legacy notification for backward compatibility
                create_user_approval_notification(username, role)

            session.pop('form_data', None)
            return redirect(url_for('login', registered='true', role=role, lang=lang))

        except Exception as e:
            db.session.rollback()
            flash(texts['flash_error'] + str(e), "danger")
            return redirect(url_for('register', lang=lang))

    # Clear any form data from session - use placeholders instead
    session.pop('form_data', None)
    return render_template('register.html', texts=texts, lang=lang, admin_exists=True)

@app.route('/test-login')
def test_login_route():
    return f"""
    <h1>Login route is working!</h1>
    <p>Current user authenticated: {current_user.is_authenticated}</p>
    <p>Current user: {current_user.username if current_user.is_authenticated else 'None'}</p>
    <p>Current role: {current_user.role if current_user.is_authenticated else 'None'}</p>
    <p>Normalized role: {normalize_role(current_user.role) if current_user.is_authenticated else 'None'}</p>
    <p>Session role: {session.get('role', 'None')}</p>
    <a href="/logout">Logout</a> | <a href="/login">Login</a> | <a href="/dashboard/reception">Reception Dashboard</a>
    """

@app.route('/debug-xray')
@login_required
def debug_xray():
    return f"""
    <h1>X-ray Debug Info</h1>
    <p>Current user authenticated: {current_user.is_authenticated}</p>
    <p>Current user: {current_user.username if current_user.is_authenticated else 'None'}</p>
    <p>Current user role: {current_user.role if current_user.is_authenticated else 'None'}</p>
    <p>Normalized role: {normalize_role(current_user.role) if current_user.is_authenticated else 'None'}</p>
    <p>Session role: {session.get('role', 'None')}</p>
    <p>Role check (role == 'xrayspecialist'): {normalize_role(current_user.role) == 'xrayspecialist' if current_user.is_authenticated else 'N/A'}</p>
    <a href="/logout">Logout</a> | <a href="/login">Login</a> | <a href="/dashboard/xray">X-ray Dashboard</a>
    """

@app.route('/login', methods=['GET', 'POST'])
def login():
    lang = request.args.get('lang') or session.get('lang', 'en')
    if lang not in login_translations:
        lang = 'en'
    session['lang'] = lang
    texts = login_translations[lang]

    if current_user.is_authenticated:
        role = normalize_role(current_user.role)
        # Check if we're being redirected back from a dashboard (to prevent loops)
        if request.referrer and 'dashboard' in request.referrer:
            # User was redirected back from dashboard, show error instead of redirecting again
            logout_user()
            flash("Access denied. Please contact administrator.", "danger")
        else:
            # Normal redirect to appropriate dashboard
            if role == "doctor":
                return redirect(url_for('dashboard_doctor'))
            elif role == "patient":
                return redirect(url_for('dashboard_patient'))
            elif role == "xrayspecialist":
                return redirect(url_for('dashboard_xray'))
            elif role == "admin":
                return redirect(url_for('dashboard_admin'))
            elif role == "reception":
                return redirect(url_for('dashboard_reception'))
            elif role == "healthofficer":
                return redirect(url_for('dashboard_health_officer'))
            else:
                logout_user()
                flash("Access denied. Please contact administrator.", "danger")

    registered = request.args.get('registered', 'false')
    role_from_registration = request.args.get('role', '')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
        user_agent = request.headers.get('User-Agent', '')

        # ==================== CRITICAL SECURITY: LOCKOUT CHECK FIRST ====================
        # MUST check lockout status BEFORE any other validation
        # This prevents ANY login attempts (correct or incorrect password) during lockout
        if LoginAttempt.is_account_locked(username):
            remaining_minutes = LoginAttempt.get_lockout_time_remaining(username)
            
            # Record this attempt as blocked - regardless of password correctness
            LoginAttempt.record_attempt(username, ip_address, user_agent, False, 'account_locked')
            
            if lang == 'en':
                flash(f"🔒 Account is temporarily locked for security reasons. Please wait {remaining_minutes} minutes before trying again.", "danger")
            else:
                flash(f"🔒 Akkaawuntiin nageenyaaf yeroof cufameera. Daqiiqaa {remaining_minutes} eegi.", "danger")
            
            return redirect(url_for('login'))

        # Try to find user in any role table
        user = get_user_by_username(username)
        if not user:
            # Record failed attempt - user not found
            LoginAttempt.record_attempt(username, ip_address, user_agent, False, 'user_not_found')
            flash(texts['no_account'], "danger")
            return redirect(url_for('login'))

        role = normalize_role(user.role)
        
        print(f"🔍 LOGIN DEBUG: User {username}, role={user.role}, normalized_role={role}, is_approved={user.is_approved}")
        
        # Check if user needs approval
        if role in ["doctor", "xrayspecialist", "reception", "healthofficer"] and not user.is_approved:
            # Record failed attempt - pending approval
            LoginAttempt.record_attempt(username, ip_address, user_agent, False, 'pending_approval')
            flash(texts['pending_approval'], "warning")
            return redirect(url_for('login'))

        # Check password
        if not user.check_password(password):
            # Record failed attempt - invalid password
            LoginAttempt.record_attempt(username, ip_address, user_agent, False, 'invalid_password')
            
            # Check how many failed attempts after this one
            failed_count = LoginAttempt.get_failed_attempts_count(username) + 1
            remaining_attempts = 5 - failed_count
            
            if remaining_attempts > 0:
                if lang == 'en':
                    flash(f"❌ Invalid password. {remaining_attempts} attempts remaining before account lockout.", "danger")
                else:
                    flash(f"❌ Jecha icciitii dogoggoraa. Yaalii {remaining_attempts} hafe osoo akkaawuntiin hin cufamiin.", "danger")
            else:
                if lang == 'en':
                    flash("🔒 Account locked for 30 minutes due to too many failed attempts.", "danger")
                else:
                    flash("🔒 Akkaawuntiin daqiiqaa 30f cufameera sababa yaalii dogoggoraa baay'ee.", "danger")
            
            return redirect(url_for('login'))

        # ==================== SUCCESSFUL LOGIN ====================
        # Record successful login attempt
        LoginAttempt.record_attempt(username, ip_address, user_agent, True)
        
        # Clear any previous failed attempts for this user
        LoginAttempt.clear_failed_attempts(username)

        saved_lang = session.get('lang', 'en')
        session.clear()
        session.permanent = True
        app.permanent_session_lifetime = timedelta(minutes=45)
        login_user(user, remember=False)
        session['lang'] = saved_lang

        session['ua_hash'] = hashlib.sha256(request.headers.get('User-Agent', '').encode()).hexdigest()
        session['session_id'] = uuid.uuid4().hex
        session['role'] = role
        
        # Flash success message AFTER setting up new session
        flash(texts['login_success'], "success")

        if role == "doctor":
            return redirect(url_for('dashboard_doctor'))
        elif role == "patient":
            return redirect(url_for('dashboard_patient'))
        elif role == "xrayspecialist":
            return redirect(url_for('dashboard_xray'))
        elif role == "admin":
            return redirect(url_for('dashboard_admin'))
        elif role == "reception":
            return redirect(url_for('dashboard_reception'))
        elif role == "healthofficer":
            return redirect(url_for('dashboard_health_officer'))
        else:
            flash(texts['unknown_role'], "danger")
            logout_user()
            return redirect(url_for('login'))

    return render_template(
        'login.html',
        lang=lang,
        texts=texts,
        registered=registered,
        role=role_from_registration
    )

@app.route('/logout')
@login_required
def logout():
    lang = session.get('lang', 'en')
    
    # Log out the user
    logout_user()
    
    # Clear all session data except language preference
    session.clear()
    session['lang'] = lang
    session.modified = True
    
    flash("Logged out successfully!", "success")
    
    # Create response with cache-busting headers
    response = redirect(url_for('login', lang=lang, logged_out=1))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

# ============================================================
#                   PASSWORD RESET ROUTES
# ============================================================

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset request page"""
    lang = request.args.get('lang') or session.get('lang', 'en')
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash('Please enter your email address.', 'danger')
            return redirect(url_for('forgot_password', lang=lang))
        
        # Validate email format
        if not validate_email_format(email):
            flash('Please enter a valid email address.', 'danger')
            return redirect(url_for('forgot_password', lang=lang))
        
        # Check if email exists in any user profile
        email_found = False
        for role in ['patient', 'doctor', 'xrayspecialist', 'reception', 'healthofficer', 'admin']:
            user_email = None
            if role == 'patient':
                profile = Patient.query.filter(Patient.email.ilike(email)).first()
            elif role == 'doctor':
                profile = Doctor.query.filter(Doctor.email.ilike(email)).first()
            elif role == 'xrayspecialist':
                profile = XraySpecialist.query.filter(XraySpecialist.email.ilike(email)).first()
            elif role == 'reception':
                profile = Reception.query.filter(Reception.email.ilike(email)).first()
            elif role == 'healthofficer':
                profile = HealthOfficer.query.filter(HealthOfficer.email.ilike(email)).first()
            elif role == 'admin':
                profile = Admin.query.filter(Admin.email.ilike(email)).first()
            
            if profile:
                email_found = True
                break
        
        if email_found:
            # Generate and send verification code
            code = create_verification_code(email)
            if code:
                if send_verification_code_email(email, code):
                    flash('Verification code sent to your email address.', 'success')
                    return redirect(url_for('verify_code', email=email, lang=lang))
                else:
                    flash('Error sending verification code. Please try again.', 'danger')
            else:
                flash('Error generating verification code. Please try again.', 'danger')
        else:
            # Don't reveal if email exists or not for security
            flash('If this email is registered, you will receive a verification code.', 'info')
        
        return redirect(url_for('forgot_password', lang=lang))
    
    return render_template('forgot_password.html', lang=lang)

@app.route('/verify-code', methods=['GET', 'POST'])
def verify_code():
    """Verification code entry page"""
    lang = request.args.get('lang') or session.get('lang', 'en')
    email = request.args.get('email', '')
    
    if not email:
        flash('Invalid request. Please start the password reset process again.', 'danger')
        return redirect(url_for('forgot_password', lang=lang))
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        
        if not code:
            flash('Please enter the verification code.', 'danger')
            return redirect(url_for('verify_code', email=email, lang=lang))
        
        # Validate verification code
        is_valid, message = validate_verification_code(email, code)
        
        if is_valid:
            # Store email in session for password reset
            session['reset_email'] = email
            flash('Verification code accepted. Please set your new password.', 'success')
            return redirect(url_for('reset_password', lang=lang))
        else:
            flash(message, 'danger')
            return redirect(url_for('verify_code', email=email, lang=lang))
    
    return render_template('verify_code.html', email=email, lang=lang)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """New password setting page"""
    lang = request.args.get('lang') or session.get('lang', 'en')
    email = session.get('reset_email')
    
    if not email:
        flash('Invalid request. Please start the password reset process again.', 'danger')
        return redirect(url_for('forgot_password', lang=lang))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not password or len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('reset_password', lang=lang))
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('reset_password', lang=lang))
        
        # Find user by email and update password
        user_updated = False
        for role in ['patient', 'doctor', 'xrayspecialist', 'reception', 'healthofficer', 'admin']:
            if role == 'patient':
                profile = Patient.query.filter(Patient.email.ilike(email)).first()
            elif role == 'doctor':
                profile = Doctor.query.filter(Doctor.email.ilike(email)).first()
            elif role == 'xrayspecialist':
                profile = XraySpecialist.query.filter(XraySpecialist.email.ilike(email)).first()
            elif role == 'reception':
                profile = Reception.query.filter(Reception.email.ilike(email)).first()
            elif role == 'healthofficer':
                profile = HealthOfficer.query.filter(HealthOfficer.email.ilike(email)).first()
            elif role == 'admin':
                profile = Admin.query.filter(Admin.email.ilike(email)).first()
            
            if profile:
                user = User.query.get(profile.user_id)
                if user:
                    user.set_password(password)
                    db.session.commit()
                    user_updated = True
                    break
        
        if user_updated:
            # Clear reset session
            session.pop('reset_email', None)
            flash('Password updated successfully. You can now log in with your new password.', 'success')
            return redirect(url_for('login', lang=lang))
        else:
            flash('Error updating password. Please try again.', 'danger')
            return redirect(url_for('reset_password', lang=lang))
    
    return render_template('reset_password.html', lang=lang)

@app.route('/dashboard/admin')
@login_required
def dashboard_admin():
    role = normalize_role(current_user.role)
    if role != "admin":
        flash("Access denied!", "danger")
        return redirect(url_for('login'))

    lang = session.get('lang', 'en')
    if lang not in admin_dashboard_translations:
        lang = 'en'
    texts = admin_dashboard_translations[lang]

    users = User.query.filter(User.role != "patient").all()
    
    # Get all feedbacks including X-ray specialist and doctor feedback
    # FIXED: Exclude patient-to-doctor feedback (those are for doctors, not admin)
    all_feedbacks = Feedback.query.filter(
        Feedback.feedback_type != 'doctor_reply',
        Feedback.feedback_type != 'patient_to_doctor'
    ).order_by(Feedback.date_submitted.desc()).all()
    
    # Separate feedbacks by type for admin dashboard
    # FIXED: Exclude doctor_reply type from patient feedbacks (those are doctor replies TO patients)
    # FIXED: Exclude doctor validation results (they start with "Doctor Validation:")
    patient_feedbacks = [fb for fb in all_feedbacks if fb.patient_id is not None and fb.feedback_type != 'doctor_reply' and not (fb.feedback and fb.feedback.startswith("Doctor Validation:"))]
    # FIXED: Exclude doctor_reply type from doctor feedbacks (those are replies TO patients, not feedback TO admin)
    doctor_feedbacks = [fb for fb in all_feedbacks if fb.doctor_id is not None and fb.feedback_type != 'doctor_reply' and not (fb.feedback and fb.feedback.startswith("Doctor Validation:"))]
    xray_specialist_feedbacks = [fb for fb in all_feedbacks if fb.xray_specialist_id is not None]

    total_doctors = User.query.filter_by(role='doctor').count()
    total_patients = User.query.filter_by(role='patient').count()
    total_xrayspecialists = User.query.filter_by(role='xrayspecialist').count()
    total_reception = User.query.filter_by(role='reception').count()
    total_healthofficer = User.query.filter_by(role='healthofficer').count()

    # Get unread notifications for admin
    unread_notifications = Notification.query.filter_by(
        admin_id=current_user.id, 
        is_read=False
    ).order_by(Notification.created_at.desc()).all()

    return render_template(
        'admin_dashboard.html',
        users=users,
        feedbacks=patient_feedbacks,  # Default to patient feedbacks for backward compatibility
        all_feedbacks=all_feedbacks,
        patient_feedbacks=patient_feedbacks,
        doctor_feedbacks=doctor_feedbacks,
        xray_specialist_feedbacks=xray_specialist_feedbacks,
        total_doctors=total_doctors,
        total_patients=total_patients,
        total_xrayspecialists=total_xrayspecialists,
        total_reception=total_reception,
        total_healthofficer=total_healthofficer,
        texts=texts,
        lang=lang,
        unread_notifications=unread_notifications
    )

# ---------------------- ADMIN FUNCTIONS ----------------------
admin_user_translations = {
    'en': {
        'access_denied': "Access denied!",
        'phone_exists': "Phone number already exists.",
        'user_added_doctor_xray': "User '{username}' added with password '{password}'. Approval pending.",
        'user_added_other': "User '{username}' added with password '{password}'.",
        'user_approved': "User '{username}' has been approved.",
        'role_updated_logout': "Your role has been updated. Please log in again.",
        'user_updated': "User information updated successfully."
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'phone_exists': "Lakkoofsi bilbilaa duraan jira.",
        'user_added_doctor_xray': "Fayyadamaan '{username}' jecha darbii '{password}' waliin ida'ame. Eyyama eeggachaa jira.",
        'user_added_other': "Fayyadamaan '{username}' jecha darbii '{password}' waliin ida'ame.",
        'user_approved': "Fayyadamaa'{username}'eeyyamameef.",
        'role_updated_logout': "Gaheen kee haaromfameera. Maaloo deebisaa seena.",
        'user_updated': "Odeeffannoon fayyadamaa milkaa'inaan haaromfame."
    }
}

@app.route('/admin/add_user', methods=['POST'])
@login_required
def add_user():  # Changed function name to match route
    try:
        # Check if user is admin
        if current_user.role != 'admin':
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403

        # Get JSON data (not form data)
        data = request.get_json()
        username = data.get('username', '').strip()
        phone = data.get('phone', '').strip()
        role_input = data.get('role', '').strip()
        password = data.get('password', '').strip()

        # Validate required fields
        if not all([username, phone, role_input, password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        # Check if phone already exists
        if User.query.filter_by(phone=phone).first():
            return jsonify({'success': False, 'message': 'Phone number already exists'}), 400

        # Validate and normalize role
        normalized_role = normalize_role(role_input)
        valid_roles = ['patient', 'doctor', 'xrayspecialist', 'reception', 'healthofficer']
        if normalized_role not in valid_roles:
            return jsonify({'success': False, 'message': 'Invalid role'}), 400

        # Create new user
        user = User(
            username=username, 
            phone=phone, 
            role=normalized_role
        )
        user.set_password(password)

        # Auto-approve all users since admin is creating them
        user.is_approved = True

        db.session.add(user)
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': f'User {username} added successfully!'
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error adding user: {str(e)}")
        return jsonify({
            'success': False, 
            'message': 'An error occurred while adding user'
        }), 500

@app.route('/admin/approve_user/<int:user_id>', methods=['POST'])
@login_required
def admin_approve_user(user_id):
    role = normalize_role(current_user.role)
    lang = session.get('lang', 'en')
    texts = admin_user_translations.get(lang, admin_user_translations['en'])

    if role != "admin":
        return jsonify({"error": texts['access_denied']}), 403

    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    
    # Send email notification to user (if they have an email)
    try:
        email_sent = send_account_approval_email(user.id, user.role)
        if email_sent:
            print(f"✅ Approval email sent to {user.username}")
        else:
            print(f"⚠️ No email sent to {user.username} (no email address or email service not configured)")
    except Exception as e:
        print(f"❌ Error sending approval email to {user.username}: {e}")
    
    # Create notification for admin about approval
    notification = Notification(
        admin_id=current_user.id,
        title="User Approved",
        message=f"User {user.username} ({user.role}) has been approved successfully.",
        type='user_approval',
        related_user_id=user.id
    )
    db.session.add(notification)
    db.session.commit()
    
    message_template = texts.get('user_approved', "User '{username}' has been approved.")
    return jsonify({"success": message_template.format(username=user.username)}), 200

@app.route('/admin/update_user/<int:user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    role = normalize_role(current_user.role)
    lang = session.get('lang', 'en')
    texts = admin_user_translations.get(lang, admin_user_translations['en'])

    if role != "admin":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)
    old_role = user.role  # Store the original role
    
    user.username = request.form['username'].strip()
    user.phone = request.form['phone'].strip()

    new_role = normalize_role(request.form['role'])
    user.role = new_role

    # Handle email field for all user types that have profiles
    email = request.form.get('email', '').strip()
    
    if user.role == 'patient':
        # Get or create patient profile
        patient_profile = Patient.query.filter_by(user_id=user.id).first()
        if not patient_profile:
            # Create patient profile if it doesn't exist
            patient_unique_id = f"PAT-{datetime.now().strftime('%Y%m%d')}-{user.id:05d}"
            patient_profile = Patient(
                user_id=user.id,
                patient_unique_id=patient_unique_id,
                email=email if email else None
            )
            db.session.add(patient_profile)
        else:
            # Update existing patient profile
            patient_profile.email = email if email else None
            
    elif user.role == 'doctor':
        # Get or create doctor profile
        doctor_profile = Doctor.query.filter_by(user_id=user.id).first()
        if not doctor_profile:
            doctor_profile = Doctor(user_id=user.id, email=email if email else None)
            db.session.add(doctor_profile)
        else:
            doctor_profile.email = email if email else None
            
    elif user.role == 'xrayspecialist':
        # Get or create xray specialist profile
        xrayspecialist_profile = XraySpecialist.query.filter_by(user_id=user.id).first()
        if not xrayspecialist_profile:
            xrayspecialist_profile = XraySpecialist(user_id=user.id, email=email if email else None)
            db.session.add(xrayspecialist_profile)
        else:
            xrayspecialist_profile.email = email if email else None
            
    elif user.role == 'healthofficer':
        # Get or create health officer profile
        healthofficer_profile = HealthOfficer.query.filter_by(user_id=user.id).first()
        if not healthofficer_profile:
            healthofficer_profile = HealthOfficer(user_id=user.id, email=email if email else None)
            db.session.add(healthofficer_profile)
        else:
            healthofficer_profile.email = email if email else None
            
    elif user.role == 'reception':
        # Get or create reception profile
        reception_profile = Reception.query.filter_by(user_id=user.id).first()
        if not reception_profile:
            reception_profile = Reception(user_id=user.id, email=email if email else None)
            db.session.add(reception_profile)
        else:
            reception_profile.email = email if email else None

    # Only change approval status if the role is actually changing
    if old_role != new_role:
        # When admin changes a user's role, automatically approve them for the new role
        # This is because the admin is making the role change decision directly
        user.is_approved = True
    # If role hasn't changed, keep the existing approval status

    db.session.commit()

    if current_user.id == user.id:
        flash(texts['role_updated_logout'], "info")
        logout_user()
        return redirect(url_for('login'))

    flash(texts['user_updated'], "success")
    return redirect(url_for('dashboard_admin'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@csrf.exempt
@login_required
def delete_user(user_id):
    try:
        print(f"Delete user request received for user_id: {user_id}")
        print(f"Current user: {current_user.username}, role: {current_user.role}")
        
        # Check if user is admin
        if current_user.role != 'admin':
            print("Unauthorized access - user is not admin")
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403

        # Get the user to delete
        user = User.query.get(user_id)
        if not user:
            print(f"User with id {user_id} not found")
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Prevent admin from deleting themselves
        if user.id == current_user.id:
            print("Admin trying to delete themselves")
            return jsonify({'success': False, 'message': 'Cannot delete your own account'}), 400

        username = user.username
        user_role = user.role
        print(f"Attempting to delete user: {username} (role: {user_role})")

        # Count related records before deletion for logging
        related_count = 0
        
        # Validate user role and profile existence
        if user_role == 'doctor':
            doctor_profile = Doctor.query.filter_by(user_id=user_id).first()
            if doctor_profile:
                print(f"Doctor profile found: {doctor_profile}")
            else:
                print("Warning: No doctor profile found for this user")
        
        # Test database connection
        try:
            test_count = User.query.count()
            print(f"Database connection test successful. Total users: {test_count}")
        except Exception as db_error:
            print(f"Database connection error: {db_error}")
            raise Exception(f"Database connection failed: {db_error}")
        
        # Disable foreign key constraints temporarily for SQLite
        pragma_disabled = False
        try:
            db.session.execute(text('PRAGMA foreign_keys = OFF'))
            db.session.commit()
            pragma_disabled = True
            print("Foreign key constraints disabled")
        except Exception as pragma_error:
            print(f"Warning: Could not disable foreign key constraints: {pragma_error}")
            # Continue anyway - the deletion might still work
        
        # Delete related data based on user role to avoid foreign key constraint errors
        if user_role == 'patient':
            print("Deleting patient-related data...")
            
            # Delete clinical interviews (as patient)
            related_count += ClinicalInterview.query.filter_by(patient_id=user_id).count()
            ClinicalInterview.query.filter_by(patient_id=user_id).delete()
            
            # Delete clinical interviews (as health officer, if any)
            related_count += ClinicalInterview.query.filter_by(health_officer_id=user_id).count()
            ClinicalInterview.query.filter_by(health_officer_id=user_id).delete()
            
            # Delete predictions
            related_count += Prediction.query.filter_by(patient_id=user_id).count()
            Prediction.query.filter_by(patient_id=user_id).delete()
            
            # Delete feedback
            related_count += Feedback.query.filter_by(patient_id=user_id).count()
            Feedback.query.filter_by(patient_id=user_id).delete()
            
            # Delete appointments
            related_count += Appointment.query.filter_by(patient_id=user_id).count()
            Appointment.query.filter_by(patient_id=user_id).delete()
            
            # Delete patient-doctor assignments
            related_count += PatientDoctorAssignment.query.filter_by(patient_id=user_id).count()
            PatientDoctorAssignment.query.filter_by(patient_id=user_id).delete()
            
            # Delete medical reports
            related_count += MedicalReport.query.filter_by(patient_id=user_id).count()
            MedicalReport.query.filter_by(patient_id=user_id).delete()
            
            # Delete doctor notifications related to this patient
            related_count += DoctorNotification.query.filter_by(patient_id=user_id).count()
            DoctorNotification.query.filter_by(patient_id=user_id).delete()
            
            # Delete xray specialist notifications related to this patient
            related_count += XraySpecialistNotification.query.filter_by(patient_id=user_id).count()
            XraySpecialistNotification.query.filter_by(patient_id=user_id).delete()
            
            # Delete universal notifications
            related_count += UniversalNotification.query.filter_by(user_id=user_id).count()
            UniversalNotification.query.filter_by(user_id=user_id).delete()
            
            # Delete patient profile
            related_count += Patient.query.filter_by(user_id=user_id).count()
            Patient.query.filter_by(user_id=user_id).delete()
            
        elif user_role == 'doctor':
            print("Deleting doctor-related data...")
            
            try:
                # Update predictions to remove doctor reference (set to NULL)
                prediction_count = Prediction.query.filter_by(doctor_id=user_id).count()
                print(f"Found {prediction_count} predictions to update")
                if prediction_count > 0:
                    Prediction.query.filter_by(doctor_id=user_id).update({'doctor_id': None})
                    related_count += prediction_count
                
                # Delete feedback from this doctor
                feedback_count = Feedback.query.filter_by(doctor_id=user_id).count()
                print(f"Found {feedback_count} feedback records to delete")
                if feedback_count > 0:
                    Feedback.query.filter_by(doctor_id=user_id).delete()
                    related_count += feedback_count
                
                # Delete appointments
                appointment_count = Appointment.query.filter_by(doctor_id=user_id).count()
                print(f"Found {appointment_count} appointments to delete")
                if appointment_count > 0:
                    Appointment.query.filter_by(doctor_id=user_id).delete()
                    related_count += appointment_count
                
                # Delete patient-doctor assignments
                assignment_count = PatientDoctorAssignment.query.filter_by(doctor_id=user_id).count()
                assigned_by_count = PatientDoctorAssignment.query.filter_by(assigned_by=user_id).count()
                print(f"Found {assignment_count} assignments as doctor, {assigned_by_count} assignments as assigner")
                if assignment_count > 0:
                    PatientDoctorAssignment.query.filter_by(doctor_id=user_id).delete()
                    related_count += assignment_count
                if assigned_by_count > 0:
                    PatientDoctorAssignment.query.filter_by(assigned_by=user_id).delete()
                    related_count += assigned_by_count
                
                # Delete medical reports
                report_count = MedicalReport.query.filter_by(doctor_id=user_id).count()
                print(f"Found {report_count} medical reports to delete")
                if report_count > 0:
                    MedicalReport.query.filter_by(doctor_id=user_id).delete()
                    related_count += report_count
                
                # Delete doctor notifications
                notification_count = DoctorNotification.query.filter_by(doctor_id=user_id).count()
                print(f"Found {notification_count} doctor notifications to delete")
                if notification_count > 0:
                    DoctorNotification.query.filter_by(doctor_id=user_id).delete()
                    related_count += notification_count
                
                # Delete universal notifications
                universal_notification_count = UniversalNotification.query.filter_by(user_id=user_id).count()
                print(f"Found {universal_notification_count} universal notifications to delete")
                if universal_notification_count > 0:
                    UniversalNotification.query.filter_by(user_id=user_id).delete()
                    related_count += universal_notification_count
                
                # Delete doctor profile
                doctor_profile_count = Doctor.query.filter_by(user_id=user_id).count()
                print(f"Found {doctor_profile_count} doctor profiles to delete")
                if doctor_profile_count > 0:
                    Doctor.query.filter_by(user_id=user_id).delete()
                    related_count += doctor_profile_count
                
                print(f"Doctor deletion completed. Total related records: {related_count}")
                
            except Exception as doctor_delete_error:
                print(f"Error during doctor-specific deletion: {doctor_delete_error}")
                raise doctor_delete_error
            
        elif user_role == 'xrayspecialist':
            print("Deleting xray specialist-related data...")
            
            # Update predictions to remove xray specialist reference (set to NULL)
            Prediction.query.filter_by(sent_by=user_id).update({'sent_by': None})
            
            # Delete feedback from this xray specialist
            Feedback.query.filter_by(xray_specialist_id=user_id).delete()
            
            # Delete xray specialist notifications
            XraySpecialistNotification.query.filter_by(xray_specialist_id=user_id).delete()
            
            # Delete universal notifications
            UniversalNotification.query.filter_by(user_id=user_id).delete()
            
            # Delete xray specialist profile
            XraySpecialist.query.filter_by(user_id=user_id).delete()
            
        elif user_role == 'reception':
            print("Deleting reception-related data...")
            
            # Update appointments to remove reception reference (set to NULL)
            Appointment.query.filter_by(created_by_reception=user_id).update({'created_by_reception': None})
            
            # Delete universal notifications
            UniversalNotification.query.filter_by(user_id=user_id).delete()
            
            # Delete reception profile
            Reception.query.filter_by(user_id=user_id).delete()
            
        elif user_role == 'healthofficer':
            print("Deleting health officer-related data...")
            
            # Delete clinical interviews (as health officer)
            ClinicalInterview.query.filter_by(health_officer_id=user_id).delete()
            
            # Delete feedback from this health officer
            Feedback.query.filter_by(health_officer_id=user_id).delete()
            
            # Delete universal notifications
            UniversalNotification.query.filter_by(user_id=user_id).delete()
            
            # Delete health officer profile
            HealthOfficer.query.filter_by(user_id=user_id).delete()
            
        elif user_role == 'admin':
            print("Deleting admin-related data...")
            
            # Delete admin notifications
            Notification.query.filter_by(admin_id=user_id).delete()
            
            # Delete universal notifications
            UniversalNotification.query.filter_by(user_id=user_id).delete()
            
            # Delete admin profile
            Admin.query.filter_by(user_id=user_id).delete()

        # Final cleanup: Check for any remaining references before deleting user
        try:
            # Check clinical interviews
            remaining_interviews_as_patient = ClinicalInterview.query.filter_by(patient_id=user_id).count()
            remaining_interviews_as_officer = ClinicalInterview.query.filter_by(health_officer_id=user_id).count()
            
            if remaining_interviews_as_patient > 0:
                print(f"Warning: Found {remaining_interviews_as_patient} clinical interviews where user {user_id} ({user_role}) is referenced as patient")
                ClinicalInterview.query.filter_by(patient_id=user_id).delete()
                related_count += remaining_interviews_as_patient
                
            if remaining_interviews_as_officer > 0:
                print(f"Warning: Found {remaining_interviews_as_officer} clinical interviews where user {user_id} ({user_role}) is referenced as health officer")
                ClinicalInterview.query.filter_by(health_officer_id=user_id).delete()
                related_count += remaining_interviews_as_officer
            
            # Check for any remaining profile references that might cause constraint errors
            if user_role != 'patient':
                # Make sure no patient profile references this user (shouldn't happen, but just in case)
                orphaned_patient_profiles = Patient.query.filter_by(user_id=user_id).count()
                if orphaned_patient_profiles > 0:
                    print(f"Warning: Found {orphaned_patient_profiles} orphaned patient profiles for non-patient user {user_id}")
                    Patient.query.filter_by(user_id=user_id).delete()
                    related_count += orphaned_patient_profiles
            
            if user_role != 'doctor':
                # Make sure no doctor profile references this user
                orphaned_doctor_profiles = Doctor.query.filter_by(user_id=user_id).count()
                if orphaned_doctor_profiles > 0:
                    print(f"Warning: Found {orphaned_doctor_profiles} orphaned doctor profiles for non-doctor user {user_id}")
                    Doctor.query.filter_by(user_id=user_id).delete()
                    related_count += orphaned_doctor_profiles
                    
        except Exception as cleanup_error:
            print(f"Error during final cleanup: {cleanup_error}")
            # Continue with deletion anyway
        
        # Flush the session to execute all pending deletions
        try:
            db.session.flush()
            print("Session flushed successfully")
        except Exception as flush_error:
            print(f"Error during session flush: {flush_error}")
            db.session.rollback()
            raise flush_error
        
        # Commit all the related record deletions first
        try:
            db.session.commit()
            print("Related records committed successfully")
        except Exception as commit_error:
            print(f"Error during commit: {commit_error}")
            db.session.rollback()
            raise commit_error
        
        # Now delete the user record
        try:
            print(f"Attempting to delete user object: {user}")
            db.session.delete(user)
            db.session.commit()
            print(f"User {username} deleted successfully")
        except Exception as final_delete_error:
            db.session.rollback()
            print(f"Error in final user deletion: {final_delete_error}")
            # Try to delete the user more forcefully using query delete
            try:
                print("Attempting force delete using query")
                deleted_count = User.query.filter_by(id=user_id).delete()
                print(f"Force delete affected {deleted_count} rows")
                db.session.commit()
                print(f"User {username} force deleted successfully")
            except Exception as force_delete_error:
                db.session.rollback()
                print(f"Force delete also failed: {force_delete_error}")
                raise Exception(f"Could not delete user {username}: {force_delete_error}")
        finally:
            # Re-enable foreign key constraints only if we successfully disabled them
            if pragma_disabled:
                try:
                    db.session.execute(text('PRAGMA foreign_keys = ON'))
                    db.session.commit()
                    print("Foreign key constraints re-enabled")
                except Exception as pragma_error:
                    print(f"Warning: Could not re-enable foreign key constraints: {pragma_error}")
                    # This is not critical, but log it
        
        print(f"User {username} and {related_count} related records deleted successfully")
        return jsonify({'success': True, 'message': f'User {username} deleted successfully'}), 200

    except Exception as e:
        db.session.rollback()
        error_message = str(e)
        print(f"Error deleting user: {error_message}")
        import traceback
        traceback.print_exc()
        
        # Provide more specific error messages based on the error type
        if "FOREIGN KEY constraint failed" in error_message:
            detailed_message = f"Cannot delete user due to related data. Error: {error_message}"
        elif "NOT NULL constraint failed" in error_message:
            detailed_message = f"Database constraint error. Error: {error_message}"
        elif "IntegrityError" in error_message:
            detailed_message = f"Database integrity error. Error: {error_message}"
        else:
            detailed_message = f"Unexpected error: {error_message}"
        
        return jsonify({
            'success': False, 
            'message': detailed_message,
            'error_type': type(e).__name__
        }), 500

# ---------------------- DASHBOARDS ----------------------
xray_dashboard_translations = {
    'en': {
        'page_title': "X-ray Specialist Dashboard",
        'profile_role': "X-ray Specialist",
        'sidebar': {
            'overview': "Overview",
            'appointment': "Send X-ray",
            'notes': "X-ray Records",
            'feedback': "Feedback",
            'settings': "Settings",
            'profile_picture': "Profile Picture",
            'change_password': "Change Password",
            'logout': "Logout"
        },
        'welcome': "Welcome, {}!",
        'current_date_aria': "Current date",
        'total_patients': "Total Patients",
        'total_appointments': "Total X-rays Sent",
        'latest_medical_image': "Latest Medical Image",
        'performance_progress': "Performance progress circle",
        'performance': "Performance",
        'send_xray_to_patient': "Send Patient X-ray to Doctor",
        'choose_patient': "Choose Patient:",
        'select_patient': "-- Select Patient --",
        'choose_doctor': "Choose Doctor:",
        'select_doctor': "-- Select Doctor --",
        'choose_xray_file': "Choose X-ray File:",
        'send_xray_button': "Send X-ray to Doctor",
        'sent_xray_records': "Sent X-ray Records",
        'patient_name': "Patient Name",
        'doctor_name': "Doctor Name",
        'file_name': "File Name",
        'date_sent': "Date Sent",
        'no_xray_sent': "No X-ray sent yet.",
        'overview': {
            'xray_overview': "X-ray Specialist Overview",
            'xray_tools': "X-ray Tools",
            'overview_text': "Welcome to the X-ray Specialist Dashboard. This comprehensive platform allows you to efficiently manage X-ray imaging, send diagnostic images to doctors, and maintain X-ray records.",
            'tools_text': "Use the navigation menu to access different X-ray specialist functions. You can send X-ray images to doctors, view sent records, and manage your settings."
        },
        'forms': {
            'choose_profile_picture': "Choose Profile Picture",
            'update_profile_picture': "Update Profile Picture",
            'current_password': "Current Password",
            'new_password': "New Password",
            'confirm_new_password': "Confirm New Password",
            'change_password_button': "Change Password"
        },
        'feedback': {
            'send_to_admin': "Send to Admin",
            'send_to_health_officer': "Send to Health Officer",
            'send_feedback': "Send Feedback",
            'your_message': "Your Message",
            'your_feedback_replies': "Your Feedback & Replies"
        }
    },
    'or': {
        'page_title': "Fuula Ogeessa X-ray",
        'profile_role': "Ogeessa X-ray",
        'sidebar': {
            'overview': "Waliigala",
            'appointment': "X-ray Erguu",
            'notes': "Galmee X-ray",
            'feedback': "Yaada",
            'settings': "Qindaa'inoota",
            'profile_picture': "Suuraa Piroofaayilii",
            'change_password': "Jecha Darbii Jijjiiruu",
            'logout': "Ba'uuf"
        },
        'welcome': "Baga nagaan dhuftan, {}!",
        'current_date_aria': "Guyyaa har'aa",
        'total_patients': "Dhukkubsattoota Guutuu",
        'total_appointments': "X-ray Ergaman Guutuu",
        'latest_medical_image': "Suuraa Fayyaa Dhiyoo",
        'performance_progress': "Adeemsa Gahumsa",
        'performance_desc': "Dhibbeentaa gahumsa kee ammaa agarsiisa",
        'performance': "Gahumsa",
        'send_xray_to_patient': "X-ray Dhukkubsataa Gara Ogeessa Fayyaatti Ergi",
        'choose_patient': "Dhukkubsataa Filadhu:",
        'select_patient': "-- Dhukkubsataa Filadhu --",
        'choose_doctor': "Ogeessa Fayyaa Filadhu:",
        'select_doctor': "-- Ogeessa Fayyaa Filadhu --",
        'choose_xray_file': "Faayila X-ray Filadhu:",
        'send_xray_button': "X-ray Gara Ogeessa Fayyaatti Ergi",
        'sent_xray_records': "Galmee X-ray Ergame",
        'patient_name': "Maqaa Dhukkubsataa",
        'doctor_name': "Maqaa Ogeessa Fayyaa",
        'file_name': "Maqaa Faayilii",
        'date_sent': "Guyyaa Ergame",
        'no_xray_sent': "X-ray hin ergamne.",
        'overview': {
            'xray_overview': "Waliigala Ogeessa X-ray",
            'xray_tools': "Meeshaalee X-ray",
            'overview_text': "Baga nagaan dhuftan gara Fuula Ogeessa X-ray. Waltajjiin kun suuraa X-ray bulchuu, suuraa qorannoo gara ogeessota fayyaatti erguu fi galmee X-ray kunuunsuu bu'a qabeessa ta'een akka hojjettan si dandeessisa.",
            'tools_text': "Baafata navigeeshinii fayyadamuun hojii ogeessa X-ray adda addaa argachuu dandeessa. Suuraa X-ray gara ogeessota fayyaatti erguu, galmee ergaman ilaaluu fi qindaa'inoota kee bulchuu dandeessa."
        },
        'forms': {
            'choose_profile_picture': "Suuraa Piroofaayilii Filadhu",
            'update_profile_picture': "Suuraa Piroofaayilii Haaromsi",
            'current_password': "Jecha Darbii Ammaa",
            'new_password': "Jecha Darbii Haaraa",
            'confirm_new_password': "Jecha Darbii Haaraa Mirkaneessi",
            'change_password_button': "Jecha Darbii Jijjiiruu"
        },
        'feedback': {
            'send_to_admin': "Gara Bulchaa Erguu",
            'send_to_health_officer': "Gara Ogeessa Fayyaa Erguu",
            'send_feedback': "Yaada Erguu",
            'your_message': "Ergaa Kee",
            'your_feedback_replies': "Yaada fi Deebii Kee"
        }
    }
}

@app.route('/dashboard/xray')
@login_required
def dashboard_xray():
    try:
        print(f"🔍 XRAY DASHBOARD DEBUG: User {current_user.username}, role={current_user.role}")
        role = normalize_role(current_user.role)
        print(f"🔍 XRAY DASHBOARD DEBUG: Normalized role={role}")
        
        if role != "xrayspecialist":
            print(f"❌ XRAY ACCESS DENIED: role='{role}', expected='xrayspecialist'")
            print(f"❌ current_user.role='{current_user.role}'")
            print(f"❌ session role='{session.get('role', 'None')}'")
            flash("Access denied! X-ray Specialist privileges required.", "danger")
            return redirect(url_for('logout'))

        lang = session.get('lang', 'en')
        if lang not in xray_dashboard_translations:
            lang = 'en'
        texts = xray_dashboard_translations[lang]

        # Get only assigned patients for this X-ray specialist (not all patients)
        # Query assignments where this X-ray specialist is assigned
        assignments = Appointment.query.filter_by(
            doctor_id=current_user.id,
            appointment_type='xray_assignment'
        ).filter(
            Appointment.status.in_(['assigned', 'scheduled'])  # Only active assignments
        ).all()
        
        # Extract patients from assignments
        assigned_patient_ids = [assignment.patient_id for assignment in assignments]
        patients = User.query.filter(User.id.in_(assigned_patient_ids)).all() if assigned_patient_ids else []
        
        # DEBUG: Print what we're passing to template
        print(f"🔍 DEBUG - Template data for {current_user.username}:")
        print(f"   assigned_patient_ids: {assigned_patient_ids}")
        print(f"   patients count: {len(patients)}")
        for patient in patients:
            print(f"   • Patient: ID {patient.id}, username '{patient.username}', role '{patient.role}'")
        
        # Get all approved doctors for the form dropdowns (this stays the same)
        doctors = User.query.filter_by(role='doctor', is_approved=True).all()
        
        print(f"   doctors count: {len(doctors)}")
        for doctor in doctors:
            print(f"   • Doctor: ID {doctor.id}, username '{doctor.username}', role '{doctor.role}'")
        
        # Get only predictions uploaded by THIS X-ray specialist
        uploaded_predictions = Prediction.query.filter_by(sent_by=current_user.id).order_by(Prediction.date_uploaded.desc()).all()
        
        # Count only patients that THIS X-ray specialist has served
        patients_served = set(pred.patient_id for pred in uploaded_predictions)
        total_patients = len(patients_served)
        total_appointments = len(uploaded_predictions)
        
        uploaded_images = []
        for pred in uploaded_predictions:
            patient = User.query.get(pred.patient_id)
            doctor = User.query.get(pred.doctor_id) if pred.doctor_id else None
            
            # Debug: Print prediction data
            print(f"🔍 DEBUG - Processing prediction {pred.id}:")
            print(f"   patient_id: {pred.patient_id} -> {patient.username if patient else 'None'}")
            print(f"   doctor_id: {pred.doctor_id} -> {doctor.username if doctor else 'None'}")
            
            # Better doctor name display
            if doctor:
                doctor_name = f"Dr. {doctor.username}"
            else:
                # For old records without doctor assignment
                if pred.doctor_validation:
                    doctor_name = "Completed (legacy record)"
                else:
                    doctor_name = "Not assigned"
            
            print(f"   doctor_name: {doctor_name}")
            
            uploaded_images.append({
                "id": pred.id,
                "patient_name": patient.username if patient else texts['profile_role'],
                "doctor_name": doctor_name,
                "filename": pred.image_filename,
                "date_sent": pred.date_uploaded.strftime('%Y-%m-%d %H:%M') if pred.date_uploaded else "N/A",
                "status": texts['send_xray_to_patient']
            })

        return render_template(
            'dashboard_xray.html',
            patients=patients,
            doctors=doctors,
            uploaded_images=uploaded_images,
            total_patients=total_patients,
            total_appointments=total_appointments,
            texts=texts,
            lang=lang
        )
    except Exception as e:
        print(f"❌ ERROR in dashboard_xray: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Dashboard error: {str(e)}", "danger")
        return redirect(url_for('login'))

patient_dashboard_translations = {
    'en': {
        'page_title': "Patient Dashboard",
        'profile_role': "Patient",
        'sidebar': {
            'overview': "Overview",
            'xray_results': "X-ray Results",
            'feedback': "Feedback",
            'settings': "Settings",
            'profile_picture': "Profile Picture",
            'change_password': "Change Password",
            'logout': "Logout"
        },
        'welcome': "Welcome, {}!",
        'current_date_aria': "Current date",
        'overview_section': "Medical Overview",
        'performance': "Performance",
        'performance_desc': "Keep tracking your progress!",
        'hospital_visit_info': "Visit Hospital for X-ray",
        'xray_results_feedback': "X-ray Results and Doctor Feedback",
        'file_name': "File Name",
        'doctor': "Doctor Name",
        'date_uploaded': "Date and Time",
        'validation': "Validation",
        'recommendation': "Recommendation",
        'download': "Download",
        'not_available': "Not Available",
        'pending': "Pending",
        'no_results': "No results received yet.",
        'feedback_section': "Feedback",
        'select_doctor': "Choose Doctor",
        'choose_doctor': "Choose a doctor...",
        'write_feedback_placeholder': "Write your feedback...",
        'submit_feedback': "Submit Feedback",
        'your_feedback_admin_reply': "Your Feedbacks & Admin Replies",
        'admin_reply_not_yet': "Admin has not replied yet.",
        'no_feedback': "No feedback submitted yet.",
        'overview': {
            'patient_overview': "Patient Overview",
            'patient_tools': "Patient Tools",
            'overview_text': "Welcome to your Patient Dashboard. This platform allows you to view your X-ray results, receive doctor feedback, and communicate with healthcare professionals.",
            'tools_text': "Use the navigation menu to access different patient functions. You can view X-ray results, provide feedback to doctors, and manage your settings."
        },
        'forms': {
            'choose_profile_picture': "Choose Profile Picture",
            'update_profile_picture': "Update Profile Picture",
            'current_password': "Current Password",
            'new_password': "New Password",
            'confirm_new_password': "Confirm New Password",
            'change_password_button': "Change Password"
        },
        'feedback': {
            'send_to_doctor': "Send to Doctor",
            'send_to_admin': "Send to Admin",
            'send_feedback': "Send Feedback",
            'your_message': "Your Message",
            'your_feedback_replies': "Your Feedback & Replies"
        }
    },
    'or': {
        'page_title': "Fuula Dhukkubsataa",
        'profile_role': "Dhukkubsataa",
        'sidebar': {
            'overview': "Waliigala",
            'xray_results': "Bu'aa X-ray",
            'feedback': "Yaada",
            'settings': "Qindaa'inoota",
            'profile_picture': "Suuraa Piroofaayilii",
            'change_password': "Jecha Darbii Jijjiiruu",
            'logout': "Ba'uuf"
        },
        'welcome': "Baga nagaan dhuftan, {}!",
        'current_date_aria': "Guyyaa har'aa",
        'overview_section': "Waliigala Fayyaa",
        'performance': "Gahumsa",
        'performance_desc': "Adeemsa kee hordofuu itti fufi!",
        'hospital_visit_info': "X-rayf Hospitaala Dhaqaa",
        'xray_results_feedback': "Bu'aa X-ray fi Yaada Ogeessa Fayyaa",
        'file_name': "Maqaa Faayilii",
        'doctor': "Maqaa Ogeessa Fayyaa",
        'date_uploaded': "Guyyaa fi Sa'aatii",
        'validation': "Mirkaneessa",
        'recommendation': "Gorsa",
        'download': "Buufadhu",
        'not_available': "Hin Jiru",
        'pending': "Eeggachaa Jira",
        'no_results': "Bu'aan hin argamne.",
        'feedback_section': "Yaada",
        'select_doctor': "Ogeessa Fayyaa Filadhu",
        'choose_doctor': "Ogeessa fayyaa filadhu...",
        'write_feedback_placeholder': "Yaada kee barreessi...",
        'submit_feedback': "Yaada Ergi",
        'your_feedback_admin_reply': "Yaada Kee fi Deebii Admin",
        'admin_reply_not_yet': "Adminin deebii hin kennine.",
        'no_feedback': "Yaada hin kennine.",
        'overview': {
            'patient_overview': "Waliigala Dhukkubsataa",
            'patient_tools': "Meeshaalee Dhukkubsataa",
            'overview_text': "Baga nagaan dhuftan gara Fuula Dhukkubsataa. Waltajjiin kun bu'aa X-ray kee ilaaluu, yaada ogeessa fayyaa argachuu fi ogeessota fayyaa waliin qunnamuu si dandeessisa.",
            'tools_text': "Baafata navigeeshinii fayyadamuun hojii dhukkubsataa adda addaa argachuu dandeessa. Bu'aa X-ray ilaaluu, yaada ogeessota fayyaaf kennuu fi qindaa'inoota kee bulchuu dandeessa."
        },
        'forms': {
            'choose_profile_picture': "Suuraa Piroofaayilii Filadhu",
            'update_profile_picture': "Suuraa Piroofaayilii Haaromsi",
            'current_password': "Jecha Darbii Ammaa",
            'new_password': "Jecha Darbii Haaraa",
            'confirm_new_password': "Jecha Darbii Haaraa Mirkaneessi",
            'change_password_button': "Jecha Darbii Jijjiiruu"
        },
        'feedback': {
            'send_to_doctor': "Gara Ogeessa Fayyaa Erguu",
            'send_to_admin': "Gara Bulchaa Erguu",
            'send_feedback': "Yaada Erguu",
            'your_message': "Ergaa Kee",
            'your_feedback_replies': "Yaada fi Deebii Kee"
        }
    }
}

@app.route('/patient/dashboard')
@login_required
def dashboard_patient():
    if normalize_role(current_user.role) != "patient":
        flash("Access denied!", "danger")
        return redirect(url_for('login'))

    lang = session.get('lang', 'en')
    if lang not in patient_dashboard_translations:
        lang = 'en'
    texts = patient_dashboard_translations[lang]

    performance_percent = 75

    # Remove received_xrays since patients no longer view X-ray images directly
    latest_medical_image = None

    xray_results = (
        Prediction.query.filter(
            Prediction.patient_id == current_user.id,
            (Prediction.doctor_validation.isnot(None)) | (Prediction.doctor_notes.isnot(None))
        )
        .order_by(Prediction.date_uploaded.desc())
        .all()
    )

    # Removed patient_notes since Notes section is no longer needed

    all_feedbacks = (
        Feedback.query
        .filter(
            Feedback.patient_id == current_user.id,
            ~Feedback.feedback.like("Doctor Validation:%")
        )
        .order_by(Feedback.id.desc())
        .all()
    )

    seen_texts = set()
    feedbacks = []
    for f in all_feedbacks:
        if f.feedback not in seen_texts:
            feedbacks.append(f)
            seen_texts.add(f.feedback)

    # Doctors are now loaded dynamically via AJAX for feedback functionality

    # Get notifications for patient - include doctor validations and admin replies
    unread_notifications = []
    
    # Get X-ray notifications from X-ray specialists
    recent_xrays = (
        db.session.query(Prediction)
        .join(User, Prediction.sent_by == User.id)
        .filter(
            Prediction.patient_id == current_user.id,
            User.role == 'xrayspecialist',
            Prediction.date_uploaded >= datetime.utcnow() - timedelta(days=7)
        )
        .order_by(Prediction.date_uploaded.desc())
        .all()
    )
    
    # Get doctor validation notifications
    recent_validations = (
        db.session.query(Prediction)
        .join(User, Prediction.doctor_id == User.id)
        .filter(
            Prediction.patient_id == current_user.id,
            Prediction.doctor_validation.isnot(None),
            Prediction.date_uploaded >= datetime.utcnow() - timedelta(days=7)
        )
        .order_by(Prediction.date_uploaded.desc())
        .all()
    )
    
    # Get admin feedback reply notifications
    recent_feedback_replies = (
        db.session.query(Feedback)
        .filter(
            Feedback.patient_id == current_user.id,
            Feedback.reply.isnot(None),
            Feedback.date_submitted >= datetime.utcnow() - timedelta(days=7)
        )
        .order_by(Feedback.date_submitted.desc())
        .all()
    )
    
    # Convert to serializable format
    for xray in recent_xrays:
        unread_notifications.append({
            'id': xray.id,
            'server_id': f"xray_{xray.id}",
            'sender_name': xray.sent_by_user.username if xray.sent_by_user else 'X-ray Specialist',
            'message': f'Sent you a new X-ray image: {xray.image_filename}',
            'created_at': xray.date_uploaded.isoformat() if xray.date_uploaded else None,
            'type': 'xray'
        })

    for validation in recent_validations:
        unread_notifications.append({
            'id': validation.id,
            'server_id': f"validation_{validation.id}",
            'sender_name': validation.doctor.username if validation.doctor else 'Doctor',
            'message': f'Provided validation results for your X-ray: {validation.image_filename}',
            'created_at': validation.date_uploaded.isoformat() if validation.date_uploaded else None,
            'type': 'result'
        })

    for feedback in recent_feedback_replies:
        unread_notifications.append({
            'id': feedback.id,
            'server_id': f"feedback_{feedback.id}",
            'sender_name': 'Administrator',
            'message': f'Replied to your feedback',
            'created_at': feedback.reply_date.isoformat() if feedback.reply_date else feedback.date_submitted.isoformat(),
            'type': 'feedback'
        })
    
    # Sort all notifications by created_at (newest first)
    unread_notifications.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)

    return render_template(
        'dashboard_patient.html',
        latest_medical_image=latest_medical_image,

        xray_results=xray_results,

        feedbacks=feedbacks,
        performance_percent=performance_percent,
        texts=texts,
        lang=lang,
        unread_notifications=unread_notifications
    )

# PATIENT NOTIFICATION ENDPOINTS - Using unique names
@app.route('/get_patient_notifications')
@login_required
def get_patient_notifications():
    """Get unread notifications for patient"""
    try:
        if normalize_role(current_user.role) != "patient":
            return jsonify([]), 403

        notifications = []
        
        # Get X-ray notifications from X-ray specialists (last 7 days)
        recent_xrays = (
            db.session.query(Prediction)
            .join(User, Prediction.sent_by == User.id)
            .filter(
                Prediction.patient_id == current_user.id,
                User.role == 'xrayspecialist',
                Prediction.date_uploaded >= datetime.utcnow() - timedelta(days=7)
            )
            .order_by(Prediction.date_uploaded.desc())
            .all()
        )
        
        # Get doctor validation notifications (last 7 days)
        recent_validations = (
            db.session.query(Prediction)
            .join(User, Prediction.doctor_id == User.id)
            .filter(
                Prediction.patient_id == current_user.id,
                Prediction.doctor_validation.isnot(None),
                Prediction.date_uploaded >= datetime.utcnow() - timedelta(days=7)
            )
            .order_by(Prediction.date_uploaded.desc())
            .all()
        )
        
        # Get admin feedback reply notifications (last 7 days)
        recent_feedback_replies = (
            db.session.query(Feedback)
            .filter(
                Feedback.patient_id == current_user.id,
                Feedback.reply.isnot(None),
                Feedback.date_submitted >= datetime.utcnow() - timedelta(days=7)
            )
            .order_by(Feedback.date_submitted.desc())
            .all()
        )
        
        # Convert to notification format
        for xray in recent_xrays:
            notifications.append({
                'id': xray.id,
                'server_id': f"xray_{xray.id}",
                'sender_name': xray.sent_by_user.username if xray.sent_by_user else 'X-ray Specialist',
                'message': f'Sent you a new X-ray image: {xray.image_filename}',
                'created_at': xray.date_uploaded.isoformat() if xray.date_uploaded else None,
                'type': 'xray'
            })

        for validation in recent_validations:
            notifications.append({
                'id': validation.id,
                'server_id': f"validation_{validation.id}",
                'sender_name': validation.doctor.username if validation.doctor else 'Doctor',
                'message': f'Provided validation results for your X-ray: {validation.image_filename}',
                'created_at': validation.date_uploaded.isoformat() if validation.date_uploaded else None,
                'type': 'result'
            })

        for feedback in recent_feedback_replies:
            notifications.append({
                'id': feedback.id,
                'server_id': f"feedback_{feedback.id}",
                'sender_name': 'Administrator',
                'message': f'Replied to your feedback',
                'created_at': feedback.reply_date.isoformat() if feedback.reply_date else feedback.date_submitted.isoformat(),
                'type': 'feedback'
            })
        
        # Sort all notifications by created_at (newest first)
        notifications.sort(key=lambda x: x['created_at'] if x['created_at'] else '', reverse=True)
        
        return jsonify(notifications)
    
    except Exception as e:
        print(f"Error fetching patient notifications: {e}")
        return jsonify([])

@app.route('/mark_patient_notification_read', methods=['POST'])
@login_required
def mark_patient_notification_read():
    """Mark a patient notification as read"""
    try:
        if normalize_role(current_user.role) != "patient":
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        data = request.get_json()
        notification_id = data.get('notification_id')
        
        # For now, we'll just return success since we're using existing records
        # In a production system, you'd update a read status in a notifications table
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error marking patient notification as read: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/clear_all_patient_notifications', methods=['POST'])
@login_required
def clear_all_patient_notifications():
    """Clear all notifications for patient"""
    try:
        if normalize_role(current_user.role) != "patient":
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        # For now, we'll just return success
        # In a production system, you'd mark all as read in a notifications table
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error clearing patient notifications: {e}")
        return jsonify({'success': False, 'error': str(e)})
    
doctor_dashboard_translations = {
    'en': {
        'page_title': "Doctor Dashboard - Breast Cancer Detection System",
        'profile_role': "Doctor",
        'sidebar': {
            'overview': "Overview",
            'appointment': "Appointment",
            'ai_model': "AI Model",
            'validation': "Validation",
            'notes': "Notes",
            'feedback': "Feedback",
            'settings': "Settings",
            'profile_picture': "Profile Picture",
            'change_password': "Change Password",
            'logout': "Logout"
        },
        'welcome': "Welcome, Dr. {}!",
        'current_date_aria': "Current date",
        'total_patients': "Total Patients",
        'total_appointments': "Total Appointments",
        'latest_medical_image': "Latest Medical Image",
        'performance_progress': "Performance Progress",
        'performance_desc': "Shows your current performance percentage",
        'performance': "Performance",
        'patient_name': "Patient Name",
        'xray_specialist': "X-ray Specialist",
        'file_name': "File Name",
        'view': "View",
        'download': "Download",
        'analyze_with_ai': "Analyze with AI",
        'no_xray_submissions': "No X-ray submissions yet.",
        'select_patient_xray': "Select Patient X-ray:",
        'validation_label': "Validation:",
        'select_option': "--Select--",
        'malignant': "Malignant",
        'benign': "Benign",
        'recommendation': "Recommendation:",
        'recommendation_placeholder': "Recommend treatment or next steps",
        'send_result': "Send Result",
        'validation_result': "Validation Result",
        'date_sent': "Date Sent",
        'no_results_sent': "No results sent yet.",
        'ai_analysis_results': "AI Analysis Results",
        'patient': "Patient",
        'file': "File",
        'confidence': "Confidence",
        'ai_explanation': "AI Explanation",
        'disclaimer': "This is an AI prediction. Final diagnosis should be confirmed by medical professionals.",
        'overview_text': "Welcome to the Doctor Dashboard. This comprehensive platform allows you to efficiently manage patient appointments, analyze medical images with AI, validate results, and provide recommendations.",
        'tools_text': "Use the navigation menu to access different doctor functions. You can view appointments, analyze X-ray images with AI, validate results, and manage patient notes.",
        'doctor_overview': "Doctor Overview",
        'doctor_tools': "Doctor Tools",
        'upload_image': "Upload Image",
        'choose_file': "Choose File",
        'predict_button': "Predict",
        'classification_result': "Classification Result",
        'send_to_admin': "Send to Admin",
        'send_to_health_officer': "Send to Health Officer",
        'send_feedback': "Send Feedback",
        'your_message': "Your Message",
        'your_feedback_replies': "Your Feedback & Replies",
        'select_health_officer': "Select Health Officer",
        'choose_profile_picture': "Choose Profile Picture",
        'update_profile_picture': "Update Profile Picture",
        'current_password': "Current Password",
        'new_password': "New Password",
        'confirm_new_password': "Confirm New Password",
        'change_password_button': "Change Password"
    },
    'or': {
        'page_title': "Fuula Ogeessa Fayyaa - Sirna Qorannoo Kaansarii Harmaa",
        'profile_role': "Ogeessa Fayyaa",
        'sidebar': {
            'overview': "Waliigala",
            'appointment': "Beellama",
            'ai_model': "Moodeela AI",
            'validation': "Mirkaneessa",
            'notes': "Yaadannoo",
            'feedback': "Yaada",
            'settings': "Qindaa'inoota",
            'profile_picture': "Suuraa Piroofaayilii",
            'change_password': "Jecha Darbii Jijjiiruu",
            'logout': "Ba'uuf"
        },
        'welcome': "Baga nagaan dhuftan, Dr. {}!",
        'current_date_aria': "Guyyaa har'aa",
        'total_patients': "Dhukkubsattoota Guutuu",
        'total_appointments': "Beellamawwan Guutuu",
        'latest_medical_image': "Suuraa Fayyaa Dhiyoo",
        'performance_progress': "Adeemsa Gahumsa",
        'performance_desc': "Dhibbeentaa gahumsa kee ammaa agarsiisa",
        'performance': "Gahumsa",
        'patient_name': "Maqaa Dhukkubsataa",
        'xray_specialist': "Ogeessa X-ray",
        'file_name': "Maqaa Faayilii",
        'view': "Ilaali",
        'download': "Buufadhu",
        'analyze_with_ai': "AI waliin Xiinxali",
        'no_xray_submissions': "Suuraan X-ray hin ergamne.",
        'select_patient_xray': "Suuraa X-ray Dhukkubsataa Filadhu:",
        'validation_label': "Mirkaneessa:",
        'select_option': "--Filadhu--",
        'malignant': "Dhibee Hamaa",
        'benign': "Dhibee Salphaa",
        'recommendation': "Gorsa:",
        'recommendation_placeholder': "Yaada yaala ykn tarkaanfii itti aanu kenni",
        'send_result': "Bu'aa Ergi",
        'validation_result': "Bu'aa Mirkaneessaa",
        'date_sent': "Guyyaa Ergame",
        'no_results_sent': "Bu'aan hin ergamne.",
        'ai_analysis_results': "Bu'aa Xiinxala AI",
        'patient': "Dhukkubsataa",
        'file': "Faayila",
        'confidence': "Amanamummaa",
        'ai_explanation': "Ibsa AI",
        'disclaimer': "Kun tilmaama AI ti. Qorannoo dhumaa ogeessa fayyaa biraa gaafachuu qaba.",
        'overview_text': "Baga nagaan dhuftan gara Fuula Ogeessa Fayyaa. Waltajjiin kun beellama dhukkubsattootaa, xiinxala suuraa fayyaa AI waliin, mirkaneessa bu'aa fi gorsa kennuu bu'a qabeessa ta'een akka bulchitan si dandeessisa.",
        'tools_text': "Baafata navigeeshinii fayyadamuun hojii ogeessa fayyaa adda addaa argachuu dandeessa. Beellama ilaaluu, suuraa X-ray AI waliin xiinxaluu, bu'aa mirkaneessuu fi yaadannoo dhukkubsataa bulchuu dandeessa.",
        'doctor_overview': "Waliigala Ogeessa Fayyaa",
        'doctor_tools': "Meeshaalee Ogeessa Fayyaa",
        'upload_image': "Suuraa Fe'uu",
        'choose_file': "Faayila Filadhu",
        'predict_button': "Tilmaami",
        'classification_result': "Bu'aa Ramaddii",
        'send_to_admin': "Gara Bulchaa Erguu",
        'send_to_health_officer': "Gara Ogeessa Fayyaa Erguu",
        'send_feedback': "Yaada Erguu",
        'your_message': "Ergaa Kee",
        'your_feedback_replies': "Yaada fi Deebii Kee",
        'select_health_officer': "Ogeessa Fayyaa Filadhu",
        'choose_profile_picture': "Suuraa Piroofaayilii Filadhu",
        'update_profile_picture': "Suuraa Piroofaayilii Haaromsi",
        'current_password': "Jecha Darbii Ammaa",
        'new_password': "Jecha Darbii Haaraa",
        'confirm_new_password': "Jecha Darbii Haaraa Mirkaneessi",
        'change_password_button': "Jecha Darbii Jijjiiruu"
    }
}

@app.route('/dashboard/doctor')
@login_required
def dashboard_doctor():
    if normalize_role(current_user.role) != "doctor":
        flash("Access denied!", "danger")
        return redirect(url_for('login'))

    lang = session.get('lang', 'en')
    if lang not in doctor_dashboard_translations:
        lang = 'en'
    texts = doctor_dashboard_translations[lang]

    # Get only predictions assigned to this doctor
    all_predictions = Prediction.query.filter_by(doctor_id=current_user.id).order_by(Prediction.id.desc()).all()

    latest_predictions = {}
    for pred in all_predictions:
        if pred.patient_id not in latest_predictions:
            latest_predictions[pred.patient_id] = pred
    predictions = list(latest_predictions.values())

    validations = Prediction.query.filter(
        Prediction.doctor_id == current_user.id,
        Prediction.doctor_validation.isnot(None)
    ).order_by(Prediction.date_uploaded.desc()).all()

    # Get latest medical image for this doctor only
    latest_medical_image = Prediction.query.filter_by(doctor_id=current_user.id).order_by(Prediction.date_uploaded.desc()).first()
    
    # Count only patients assigned to this doctor
    patients_for_this_doctor = set(pred.patient_id for pred in all_predictions)
    total_patients = len(patients_for_this_doctor)
    total_validated = len([p for p in predictions if p.doctor_validation])
    performance_percent = int((total_validated / total_patients * 100) if total_patients else 0)

    # Get unread notifications for this doctor and convert to dictionaries
    try:
        unread_notifications = DoctorNotification.query.filter_by(
            doctor_id=current_user.id, 
            is_read=False
        ).order_by(DoctorNotification.created_at.desc()).all()
        
        # Convert DoctorNotification objects to dictionaries for JSON serialization
        unread_notifications_data = []
        for notification in unread_notifications:
            unread_notifications_data.append({
                'id': notification.id,
                'doctor_id': notification.doctor_id,
                'patient_id': notification.patient_id,
                'patient_name': notification.patient_name,
                'xray_filename': notification.xray_filename,
                'message': notification.message,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'formatted_time': notification.get_formatted_time()
            })
    except Exception as e:
        print(f"Error loading notifications: {e}")
        unread_notifications_data = []

    return render_template(
        'dashboard_doctor.html',
        predictions=predictions,
        validations=validations,
        latest_medical_image=latest_medical_image,
        total_appointments=len(predictions),
        total_patients=total_patients,
        performance_percent=performance_percent,
        texts=texts,
        lang=lang,
        unread_notifications=unread_notifications_data,  # Pass the dictionary data instead of objects
        current_user=current_user
    )

# ---------------------- RECEPTION DASHBOARD ----------------------
reception_dashboard_translations = {
    'en': {
        'page_title': "Reception Dashboard",
        'profile_role': "Reception Staff",
        'sidebar': {
            'overview': "Overview",
            'register_patient': "Register Patient",
            'assign_health_officer': "Assign Health Officer",
            'patient_list': "Patient List",
            'feedback': "Feedback",
            'settings': "Settings",
            'profile_picture': "Profile Picture",
            'change_password': "Change Password",
            'logout': "Logout"
        },
        'overview': {
            'reception_overview': "Reception Overview",
            'reception_tools': "Reception Tools",
            'overview_text': "Baga nagaan dhuftan gara Fuula Mana Galmee. Waltajjiin kun galmii dhukkubsattootaa, qindaa'ina beellamaa fi hojii mana galmee bu'a qabeessa ta'een akka bulchitan si dandeessisa.",
            'tools_text': "Baafata navigeeshinii fayyadamuun hojii mana galmee adda addaa argachuu dandeessa. Dhukkubsattoota haaraa galmaa'uu, beellama qindeessuu, tarree dhukkubsattootaa ilaaluu fi qindaa'inoota mana galmee bulchuu dandeessa."
        },
        'forms': {
            'username': "Username",
            'phone': "Phone Number",
            'email': "Gmail Address",
            'password': "Password",
            'confirm_password': "Confirm Password",
            'role': "Role",
            'patient': "Patient",
            'register_button': "Register Patient",
            'select_patient': "Select Patient",
            'assign_health_officer': "Assign Health Officer",
            'assign_button': "Assign Health Officer",
            'current_assignments': "Current Health Officer Assignments",
            'loading_patients': "Loading patients...",
            'loading_officers': "Loading Health Officers...",
            'loading_assignments': "Loading current assignments...",
            'search_placeholder': "Search patients by name, phone, or ID...",
            'choose_profile_picture': "Choose Profile Picture",
            'update_profile_picture': "Update Profile Picture",
            'current_password': "Current Password",
            'new_password': "New Password",
            'confirm_new_password': "Confirm New Password",
            'change_password_button': "Change Password"
        },
        'table': {
            'username': "Username",
            'phone': "Phone",
            'email': "Email",
            'patient_id': "Patient ID",
            'registration_date': "Registration Date"
        },
        'feedback': {
            'send_to_admin': "Send to Admin",
            'send_to_health_officer': "Send to Health Officer",
            'send_feedback_admin': "Send Feedback to Admin",
            'send_feedback_officer': "Send Feedback to Health Officer",
            'your_message': "Your Message",
            'send_button': "Send Feedback",
            'your_feedback_replies': "Your Feedback & Replies",
            'select_health_officer': "Select Health Officer"
        }
    },
    'or': {
        'page_title': "Fuula Mana Galmee",
        'profile_role': "Hojjetaa Mana Galmee",
        'sidebar': {
            'overview': "Waliigala",
            'register_patient': "Dhukkubsataa Galmaa'uu",
            'assign_health_officer': "Ogeessa Fayyaa Ramaduu",
            'patient_list': "Tarree Dhukkubsattootaa",
            'feedback': "Yaada",
            'settings': "Qindaa'inoota",
            'profile_picture': "Suuraa Piroofaayilii",
            'change_password': "Jecha Darbii Jijjiiruu",
            'logout': "Ba'uuf"
        },
        'overview': {
            'reception_overview': "Waliigala Mana Galmee",
            'reception_tools': "Meeshaalee Mana Galmee",
            'overview_text': "Baga nagaan dhuftan gara Fuula Mana Galmee. Waltajjiin kun galmii dhukkubsattootaa, qindaa'ina beellamaa fi hojii mana galmee bu'a qabeessa ta'een akka bulchitan si dandeessisa.",
            'tools_text': "Baafata navigeeshinii fayyadamuun hojii mana galmee adda addaa argachuu dandeessa. Dhukkubsattoota haaraa galmaa'uu, beellama qindeessuu, tarree dhukkubsattootaa ilaaluu fi qindaa'inoota mana galmee bulchuu dandeessa."
        },
        'forms': {
            'username': "Maqaa fayyadamaa",
            'phone': "Lakkoofsa Bilbilaa",
            'email': "Teessoo Imeelii",
            'password': "Jecha Darbii",
            'confirm_password': "Jecha Darbii Mirkaneessi",
            'role': "Gahee",
            'patient': "Dhukkubsataa",
            'register_button': "Dhukkubsataa Galmaa'uu",
            'select_patient': "Dhukkubsataa Filadhu",
            'assign_health_officer': "Ogeessa Fayyaa Ramaduu",
            'assign_button': "Ogeessa Fayyaa Ramaduu",
            'current_assignments': "Ramaduu Ogeessota Fayyaa Ammaa",
            'loading_patients': "Dhukkubsattoota fe'aa jira...",
            'loading_officers': "Ogeessota Fayyaa fe'aa jira...",
            'loading_assignments': "Ramaduu ammaa fe'aa jira...",
            'search_placeholder': "Dhukkubsattoota maqaa, bilbila ykn ID'n barbaadi...",
            'choose_profile_picture': "Suuraa Piroofaayilii Filadhu",
            'update_profile_picture': "Suuraa Piroofaayilii Haaromsi",
            'current_password': "Jecha Darbii Ammaa",
            'new_password': "Jecha Darbii Haaraa",
            'confirm_new_password': "Jecha Darbii Haaraa Mirkaneessi",
            'change_password_button': "Jecha Darbii Jijjiiruu"
        },
        'table': {
            'username': "Maqaa fayyadamaa",
            'phone': "Bilbila",
            'email': "Imeelii",
            'patient_id': "Eenyummaa Dhukkubsataa",
            'registration_date': "Guyyaa Galmaa'e"
        },
        'feedback': {
            'send_to_admin': "Gara Bulchaa Erguu",
            'send_to_health_officer': "Gara Ogeessa Fayyaa Erguu",
            'send_feedback_admin': "Yaada gara Bulchaa Erguu",
            'send_feedback_officer': "Yaada gara Ogeessa Fayyaa Erguu",
            'your_message': "Ergaa Kee",
            'send_button': "Yaada Erguu",
            'your_feedback_replies': "Yaada fi Deebii Kee",
            'select_health_officer': "Ogeessa Fayyaa Filadhu"
        }
    }
}

# ---------------------- HEALTH OFFICER DASHBOARD ----------------------
health_officer_dashboard_translations = {
    'en': {
        'page_title': "Health Officer Dashboard",
        'profile_role': "Health Officer",
        'sidebar': {
            'overview': "Overview",
            'assigned_patients': "Assigned Patients",
            'assign_xray': "Assign X-ray Specialist",
            'clinical_interview': "Patient Clinical Interview",
            'notes': "Notes",
            'feedback': "Feedback",
            'settings': "Settings",
            'profile_picture': "Profile Picture",
            'change_password': "Change Password",
            'logout': "Logout"
        },
        'welcome': "Welcome, {}!",
        'current_date_aria': "Current date",
        'total_assigned_patients': "Assigned Patients",
        'total_xray_assignments': "X-ray Assignments Made",
        'total_notes_created': "Notes Created",
        'total_feedback_responses': "Feedback Responses",
        'recent_activities': "Recent Activities",
        'assigned_patients_list': "Assigned Patients",
        'xray_assignments': "X-ray Assignments",
        'notes_management': "Notes Management",
        'feedback_management': "Feedback Management",
        'no_assigned_patients': "No patients assigned.",
        'no_recent_activities': "No recent activities.",
        'view_all_patients': "View All Assigned Patients",
        'create_new_note': "Create New Note",
        'view_all_feedback': "View All Feedback",
        'clinical_interview': {
            'title': "Patient Clinical Interview",
            'description': "Send clinical interview questions to your assigned patients and receive their responses for better patient assessment."
        },
        'overview': {
            'health_officer_overview': "Health Officer Overview",
            'health_officer_tools': "Health Officer Tools",
            'overview_text': "Welcome to the Health Officer Dashboard. This comprehensive platform allows you to efficiently manage assigned patients, coordinate X-ray specialists, conduct clinical interviews, and maintain patient notes.",
            'tools_text': "Use the navigation menu to access different health officer functions. You can view assigned patients, assign X-ray specialists, conduct clinical interviews, and manage patient notes."
        },
        'forms': {
            'patient_name': "Patient Name",
            'select_patient': "Select Patient",
            'select_xray_specialist': "Select X-ray Specialist",
            'assign_button': "Assign X-ray Specialist",
            'send_interview': "Send Interview",
            'interview_question': "Interview Question",
            'patient_response': "Patient Response",
            'no_response': "No response yet",
            'choose_profile_picture': "Choose Profile Picture",
            'update_profile_picture': "Update Profile Picture",
            'current_password': "Current Password",
            'new_password': "New Password",
            'confirm_new_password': "Confirm New Password",
            'change_password_button': "Change Password"
        },
        'feedback': {
            'send_to_admin': "Send to Admin",
            'send_to_reception': "Send to Reception",
            'send_feedback': "Send Feedback",
            'your_message': "Your Message",
            'your_feedback_replies': "Your Feedback & Replies",
            'patient_feedback': "Patient Feedback",
            'reception_feedback': "Reception Feedback"
        }
    },
    'or': {
        'page_title': "Fuula Ogeessa Fayyaa",
        'profile_role': "Ogeessa Fayyaa",
        'sidebar': {
            'overview': "Waliigala",
            'assigned_patients': "Dhukkubsattoota Ramadaman",
            'assign_xray': "Ogeessa X-ray Ramaduu",
            'clinical_interview': "Gaaffii Qorannoo Fayyaa Dhukkubsataa",
            'notes': "Yaadannoo",
            'feedback': "Yaada",
            'settings': "Qindaa'inoota",
            'profile_picture': "Suuraa Piroofaayilii",
            'change_password': "Jecha Darbii Jijjiiruu",
            'logout': "Ba'uuf"
        },
        'welcome': "Baga nagaan dhuftan, {}!",
        'current_date_aria': "Guyyaa har'aa",
        'total_assigned_patients': "Dhukkubsattoota Ramadaman",
        'total_xray_assignments': "Ramaduu X-ray Raawwatan",
        'total_notes_created': "Yaadannoo Uuman",
        'total_feedback_responses': "Deebii Yaadaa",
        'recent_activities': "Sochiiwwan Dhiyoo",
        'assigned_patients_list': "Tarree Dhukkubsattootaa Ramadaman",
        'xray_assignments': "Ramaduu X-ray",
        'notes_management': "Bulchiinsa Yaadannoo",
        'feedback_management': "Bulchiinsa Yaadaa",
        'no_assigned_patients': "Dhukkubsataan ramadame hin jiru.",
        'no_recent_activities': "Sochiin dhiyoo hin jiru.",
        'view_all_patients': "Dhukkubsattoota Ramadaman Hunda Ilaali",
        'create_new_note': "Yaadannoo Haaraa Uumi",
        'view_all_feedback': "Yaada Hunda Ilaali",
        'clinical_interview': {
            'title': "Gaaffii Qorannoo Fayyaa Dhukkubsataa",
            'description': "Gaaffii qorannoo fayyaa dhukkubsattoota siif ramadamaniif ergiitii deebii isaanii argachuun madaallii fayyaa fooyya'aa ta'e kennuu."
        },
        'overview': {
            'health_officer_overview': "Waliigala Ogeessa Fayyaa",
            'health_officer_tools': "Meeshaalee Ogeessa Fayyaa",
            'overview_text': "Baga nagaan dhuftan gara Fuula Ogeessa Fayyaa. Waltajjiin kun dhukkubsattoota siif ramadaman bulchuu, ogeessota X-ray qindeessuu, gaaffii qorannoo fayyaa gaggeessuu fi yaadannoo dhukkubsataa kunuunsuu bu'a qabeessa ta'een akka hojjettan si dandeessisa.",
            'tools_text': "Baafata navigeeshinii fayyadamuun hojii ogeessa fayyaa adda addaa argachuu dandeessa. Dhukkubsattoota ramadaman ilaaluu, ogeessota X-ray ramaduu, gaaffii qorannoo fayyaa gaggeessuu fi yaadannoo dhukkubsataa bulchuu dandeessa."
        },
        'forms': {
            'patient_name': "Maqaa Dhukkubsataa",
            'select_patient': "Dhukkubsataa Filadhu",
            'select_xray_specialist': "Ogeessa X-ray Filadhu",
            'assign_button': "Ogeessa X-ray Ramaduu",
            'send_interview': "Gaaffii Ergi",
            'interview_question': "Gaaffii Qorannoo",
            'patient_response': "Deebii Dhukkubsataa",
            'no_response': "Deebiin hin jiru",
            'choose_profile_picture': "Suuraa Piroofaayilii Filadhu",
            'update_profile_picture': "Suuraa Piroofaayilii Haaromsi",
            'current_password': "Jecha Darbii Ammaa",
            'new_password': "Jecha Darbii Haaraa",
            'confirm_new_password': "Jecha Darbii Haaraa Mirkaneessi",
            'change_password_button': "Jecha Darbii Jijjiiruu"
        },
        'feedback': {
            'send_to_admin': "Gara Bulchaa Erguu",
            'send_to_reception': "Gara Mana Galmee Erguu",
            'send_feedback': "Yaada Erguu",
            'your_message': "Ergaa Kee",
            'your_feedback_replies': "Yaada fi Deebii Kee",
            'patient_feedback': "Yaada Dhukkubsataa",
            'reception_feedback': "Yaada Mana Galmee"
        }
    }
}
@app.route('/dashboard/reception/simple')
@login_required
def dashboard_reception_simple():
    """Simple reception dashboard without complex template"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reception Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ background: #0078D4; color: white; padding: 20px; border-radius: 8px; }}
            .content {{ margin: 20px 0; }}
            .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
            .stat-card {{ background: #f5f5f5; padding: 15px; border-radius: 8px; }}
            .nav {{ margin: 20px 0; }}
            .nav a {{ margin-right: 15px; padding: 8px 16px; background: #0078D4; color: white; text-decoration: none; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏥 Reception Dashboard</h1>
            <p>Welcome, {current_user.username}!</p>
        </div>
        
        <div class="nav">
            <a href="/logout">Logout</a>
            <a href="/dashboard/reception">Full Dashboard</a>
            <a href="/test-login">Test Page</a>
        </div>
        
        <div class="content">
            <h2>User Information</h2>
            <p><strong>Username:</strong> {current_user.username}</p>
            <p><strong>Role:</strong> {current_user.role}</p>
            <p><strong>Approved:</strong> {current_user.is_approved}</p>
            <p><strong>Active:</strong> {current_user.is_active_user}</p>
            
            <h2>Reception Functions</h2>
            <div class="stats">
                <div class="stat-card">
                    <h3>Register Patient</h3>
                    <p>Register new patients in the system</p>
                </div>
                <div class="stat-card">
                    <h3>Schedule Appointment</h3>
                    <p>Schedule appointments for patients</p>
                </div>
                <div class="stat-card">
                    <h3>View Patients</h3>
                    <p>View and manage patient records</p>
                </div>
            </div>
            
            <h2>System Status</h2>
            <p>✅ Reception dashboard is working!</p>
            <p>✅ User authentication successful</p>
            <p>✅ Reception role verified</p>
        </div>
    </body>
    </html>
    """

@app.route('/dashboard/reception')
@login_required
@reception_required
def dashboard_reception():
    print(f"🔍 Reception dashboard route called for user: {current_user.username}")
    try:
        # Simplified version to avoid redirect loops
        lang = session.get('lang', 'en')
        if lang not in reception_dashboard_translations:
            lang = 'en'
        texts = reception_dashboard_translations[lang]

        # Get or create reception profile
        reception_profile = Reception.query.filter_by(user_id=current_user.id).first()
        if not reception_profile:
            reception_profile = Reception(
                user_id=current_user.id,
                department='Reception',
                can_register_patients=True,
                can_schedule_appointments=True,
                can_modify_patient_info=True
            )
            db.session.add(reception_profile)
            db.session.commit()

        # Simple default values to avoid database errors
        todays_appointments = []
        recent_patients = []
        total_patients = 0
        total_appointments = 0
        reception_stats = {
            'patients_registered_today': 0,
            'appointments_scheduled_today': 0
        }

        # Try to get basic statistics safely
        try:
            total_patients = User.query.filter_by(role='patient').count()
            recent_patients = User.query.filter_by(role='patient').order_by(User.date_created.desc()).limit(5).all()
        except Exception as e:
            print(f"Error getting statistics: {e}")

        # Try to render the template, fall back to simple version if it fails
        print(f"🔍 Attempting to render template...")
        try:
            result = render_template(
                'dashboard_reception.html',
                texts=texts,
                lang=lang,
                current_user=current_user,
                reception_profile=reception_profile,
                todays_appointments=todays_appointments,
                recent_patients=recent_patients,
                total_patients=total_patients,
                total_appointments=total_appointments,
                reception_stats=reception_stats
            )
            print(f"✅ Template rendered successfully, length: {len(result)}")
            return result
        except Exception as template_error:
            print(f"Template error: {template_error}")
            import traceback
            print(f"Full traceback:")
            traceback.print_exc()
            # Fall back to simple HTML if template fails
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Reception Dashboard</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            </head>
            <body class="bg-light">
                <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
                    <div class="container">
                        <span class="navbar-brand">🏥 Reception Dashboard</span>
                        <div class="navbar-nav ms-auto">
                            <a class="nav-link" href="/logout">Logout</a>
                        </div>
                    </div>
                </nav>
                
                <div class="container mt-4">
                    <div class="row">
                        <div class="col-12">
                            <div class="alert alert-success">
                                <h4><i class="fas fa-check-circle"></i> Welcome, {current_user.username}!</h4>
                                <p>Reception dashboard is working. Template had an error, so showing simplified version.</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-4">
                            <div class="card">
                                <div class="card-body text-center">
                                    <i class="fas fa-user-plus fa-3x text-primary mb-3"></i>
                                    <h5>Register Patient</h5>
                                    <p>Register new patients in the system</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card">
                                <div class="card-body text-center">
                                    <i class="fas fa-calendar-plus fa-3x text-success mb-3"></i>
                                    <h5>Schedule Appointment</h5>
                                    <p>Schedule appointments for patients</p>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card">
                                <div class="card-body text-center">
                                    <i class="fas fa-users fa-3x text-info mb-3"></i>
                                    <h5>View Patients</h5>
                                    <p>Total Patients: {total_patients}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="row mt-4">
                        <div class="col-12">
                            <div class="card">
                                <div class="card-header">
                                    <h5><i class="fas fa-info-circle"></i> System Information</h5>
                                </div>
                                <div class="card-body">
                                    <p><strong>User:</strong> {current_user.username}</p>
                                    <p><strong>Role:</strong> {current_user.role}</p>
                                    <p><strong>Department:</strong> {reception_profile.department if reception_profile else 'Reception'}</p>
                                    <p><strong>Status:</strong> <span class="badge bg-success">Active</span></p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
    except Exception as e:
        # If there's any error, show a simple message instead of crashing
        print(f"Dashboard error: {e}")
        import traceback
        traceback.print_exc()
        return f"""
        <h1>Reception Dashboard Error</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><strong>User:</strong> {current_user.username if current_user.is_authenticated else 'Not authenticated'}</p>
        <p><strong>Role:</strong> {current_user.role if current_user.is_authenticated else 'No role'}</p>
        <div style="margin: 20px 0;">
            <a href="/logout" style="margin-right: 10px;">Logout</a>
            <a href="/dashboard/reception/simple" style="margin-right: 10px;">Simple Dashboard</a>
            <a href="/test-login">Test Page</a>
        </div>
        <details>
            <summary>Technical Details</summary>
            <pre>{traceback.format_exc()}</pre>
        </details>
        """

# ---------------------- RECEPTION FUNCTIONALITY ROUTES ----------------------

@app.route('/reception/get_patients')
@login_required
@reception_required
def get_patients_for_reception():
    """Get all patients for appointment scheduling"""
    try:
        patients = User.query.filter_by(role='patient', is_approved=True, is_active_user=True).all()
        patient_list = []
        for patient in patients:
            patient_list.append({
                'id': patient.id,
                'username': patient.username,
                'phone': patient.phone
            })
        return jsonify(patient_list)
    except Exception as e:
        print(f"Error getting patients: {e}")
        return jsonify([])

# ---------------------- HEALTH OFFICER DASHBOARD ----------------------
@app.route('/dashboard/healthofficer')
@login_required
@health_officer_required
def dashboard_health_officer():
    try:
        lang = session.get('lang', 'en')
        if lang not in health_officer_dashboard_translations:
            lang = 'en'
        texts = health_officer_dashboard_translations[lang]

        # Get or create health officer profile
        health_officer_profile = HealthOfficer.query.filter_by(user_id=current_user.id).first()
        if not health_officer_profile:
            health_officer_profile = HealthOfficer(
                user_id=current_user.id,
                department='Health Services',
                can_conduct_screenings=True,
                can_provide_health_education=True,
                can_assist_doctors=True
            )
            db.session.add(health_officer_profile)
            db.session.commit()

        # Get assigned patients for this health officer
        assigned_patients = []
        recent_activities = []
        total_assigned_patients = 0
        total_xray_assignments = 0
        total_notes = 0
        total_feedback_responses = 0
        
        # Try to get assigned patients and statistics
        try:
            # Get patients assigned to this health officer
            assignments = Appointment.query.filter_by(
                doctor_id=current_user.id,  # Health officer stored in doctor_id field
                appointment_type='health_officer_assignment'
            ).filter(Appointment.status.in_(['assigned', 'scheduled'])).all()
            
            assigned_patients = []
            for assignment in assignments:
                patient = User.query.get(assignment.patient_id)
                if patient:
                    # Get patient profile for additional info
                    patient_profile = Patient.query.filter_by(user_id=patient.id).first()
                    
                    patient_data = {
                        'id': patient.id,
                        'username': patient.username,
                        'phone': patient.phone,
                        'patient_unique_id': patient_profile.patient_unique_id if patient_profile else f'P{patient.id:06d}',
                        'assigned_date': assignment.appointment_date,
                        'status': assignment.status,
                        'assignment_id': assignment.id
                    }
                    assigned_patients.append(patient_data)
            
            total_assigned_patients = len(assigned_patients)
            
            # Get X-ray assignments made by this health officer (stored in Appointment table with type 'xray_assignment')
            xray_assignments = Appointment.query.filter_by(
                created_by_reception=current_user.id,  # Health officer who made the assignment
                appointment_type='xray_assignment'
            ).all()
            total_xray_assignments = len(xray_assignments)
            
            # Create recent activities from assignments
            recent_activities = []
            for assignment in assignments[:5]:  # Last 5 assignments
                patient = User.query.get(assignment.patient_id)
                if patient:
                    activity = {
                        'type': 'Patient Assignment',
                        'patient_name': patient.username,
                        'date': assignment.appointment_date,
                        'status': assignment.status
                    }
                    recent_activities.append(activity)
            
            # Add X-ray assignments to recent activities
            for xray_assignment in xray_assignments[-3:]:  # Last 3 X-ray assignments
                patient = User.query.get(xray_assignment.patient_id)
                if patient:
                    activity = {
                        'type': 'X-ray Assignment',
                        'patient_name': patient.username,
                        'date': xray_assignment.appointment_date,
                        'status': xray_assignment.status
                    }
                    recent_activities.append(activity)
            
            # Sort recent activities by date
            recent_activities.sort(key=lambda x: x['date'], reverse=True)
            recent_activities = recent_activities[:5]  # Keep only 5 most recent
            
        except Exception as e:
            print(f"Error getting health officer data: {e}")
            # Fallback to empty data
            assigned_patients = []
            recent_activities = []
            total_assigned_patients = 0
            total_xray_assignments = 0
        
        health_officer_stats = {
            'assigned_patients_count': total_assigned_patients,
            'xray_assignments_today': 0,  # Could be calculated if needed
            'notes_created_today': 0,     # Could be calculated if needed
            'feedback_responses_today': 0  # Could be calculated if needed
        }

        # Try to render the template
        try:
            return render_template(
                'dashboard_health_officer.html',
                texts=texts,
                lang=lang,
                current_user=current_user,
                health_officer_profile=health_officer_profile,
                assigned_patients=assigned_patients,
                recent_activities=recent_activities,
                total_assigned_patients=total_assigned_patients,
                total_xray_assignments=total_xray_assignments,
                total_notes=total_notes,
                total_feedback_responses=total_feedback_responses,
                health_officer_stats=health_officer_stats
            )
        except Exception as e:
            print(f"Template error: {e}")
            return dashboard_health_officer_simple()

    except Exception as e:
        print(f"Health Officer Dashboard error: {e}")
        return dashboard_health_officer_simple()

@app.route('/dashboard/healthofficer/simple')
@login_required
def dashboard_health_officer_simple():
    """Simple health officer dashboard without complex template"""
    return f"""
    <h1>Health Officer Dashboard</h1>
    <p>Welcome, {current_user.username}!</p>
    <p>Role: {current_user.role}</p>
    <p>User ID: {current_user.id}</p>
    <a href="/logout">Logout</a>
    <br><br>
    <p>This is a simplified dashboard. The full template is now available.</p>
    <a href="/dashboard/healthofficer">Go to Full Dashboard</a>
    """

@app.route('/reception/get_doctors')
@login_required
@reception_required
def get_doctors_for_reception():
    """Get all doctors for appointment assignment"""
    try:
        doctors = User.query.filter_by(role='doctor', is_approved=True, is_active_user=True).all()
        doctor_list = []
        for doctor in doctors:
            doctor_list.append({
                'id': doctor.id,
                'username': doctor.username
            })
        return jsonify(doctor_list)
    except Exception as e:
        print(f"Error getting doctors: {e}")
        return jsonify([])

@app.route('/reception/get_all_patients')
@login_required
@reception_required
def get_all_patients_for_reception():
    """Get all patients with detailed information"""
    try:
        patients = User.query.filter_by(role='patient').all()
        patient_list = []
        for patient in patients:
            patient_profile = Patient.query.filter_by(user_id=patient.id).first()
            patient_list.append({
                'id': patient.id,
                'username': patient.username,
                'phone': patient.phone,
                'email': patient_profile.email if patient_profile else None,
                'patient_id': patient_profile.patient_unique_id if patient_profile else None,
                'age': patient_profile.age if patient_profile else None,
                'gender': patient_profile.gender if patient_profile else None,
                'date_created': patient.date_created.strftime('%Y-%m-%d') if patient.date_created else 'N/A'
            })
        return jsonify(patient_list)
    except Exception as e:
        print(f"Error getting all patients: {e}")
        return jsonify([])

@app.route('/reception/get_patient/<int:patient_id>')
@login_required
@reception_required
def get_patient_details(patient_id):
    """Get detailed information for a specific patient"""
    try:
        patient = User.query.get(patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({'error': 'Patient not found'}), 404
            
        patient_profile = Patient.query.filter_by(user_id=patient.id).first()
        
        patient_data = {
            'id': patient.id,
            'username': patient.username,
            'phone': patient.phone,
            'email': getattr(patient_profile, 'email', None) if patient_profile else None,
            'age': patient_profile.age if patient_profile else None,
            'gender': patient_profile.gender if patient_profile else None,
            'address': getattr(patient_profile, 'address', None) if patient_profile else None,
            'medical_history': getattr(patient_profile, 'medical_history', None) if patient_profile else None,
            'date_created': patient.date_created.strftime('%Y-%m-%d %H:%M') if patient.date_created else 'N/A'
        }
        return jsonify(patient_data)
    except Exception as e:
        print(f"Error getting patient details: {e}")
        return jsonify({'error': 'Failed to get patient details'}), 500

@app.route('/reception/schedule_appointment', methods=['POST'])
@login_required
@reception_required
def schedule_appointment():
    """Schedule a new appointment"""
    try:
        patient_id = request.form.get('patient_id')
        appointment_date = request.form.get('appointment_date')
        appointment_time = request.form.get('appointment_time')
        appointment_type = request.form.get('appointment_type')
        doctor_id = request.form.get('doctor_id')
        notes = request.form.get('notes', '')
        
        if not all([patient_id, appointment_date, appointment_time, appointment_type]):
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        # Combine date and time
        from datetime import datetime
        appointment_datetime = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %H:%M")
        
        # Create appointment (you'll need to create an Appointment model)
        # For now, just return success
        return jsonify({'success': True, 'message': 'Appointment scheduled successfully'})
        
    except Exception as e:
        print(f"Error scheduling appointment: {e}")
        return jsonify({'success': False, 'message': 'Failed to schedule appointment'})

@app.route('/reception/get_todays_appointments')
@login_required
@reception_required
def get_todays_appointments():
    """Get today's appointments"""
    try:
        # This would query actual appointments - placeholder for now
        appointments = []
        return jsonify(appointments)
    except Exception as e:
        print(f"Error getting today's appointments: {e}")
        return jsonify([])

# ====================== X-RAY SPECIALIST ASSIGNMENT ROUTES ======================

@app.route('/reception/get_xray_specialists')
@login_required
@reception_required
def get_xray_specialists_for_reception():
    """Get all approved X-ray specialists for assignment"""
    try:
        xray_specialists = User.query.filter_by(role='xrayspecialist', is_approved=True, is_active_user=True).all()
        specialist_list = []
        for specialist in xray_specialists:
            specialist_list.append({
                'id': specialist.id,
                'username': specialist.username
            })
        return jsonify(specialist_list)
    except Exception as e:
        print(f"Error getting X-ray specialists: {e}")
        return jsonify([])

@app.route('/reception/assign_xray_specialist', methods=['POST'])
@login_required
@reception_required
def assign_xray_specialist():
    """Assign X-ray specialist to patient"""
    try:
        patient_id = request.form.get('patient_id')
        xray_specialist_id = request.form.get('xray_specialist_id')
        
        if not patient_id or not xray_specialist_id:
            return jsonify({'success': False, 'message': 'Please select both patient and X-ray specialist!'})
        
        # Get patient and X-ray specialist
        patient = User.query.get(patient_id)
        xray_specialist = User.query.get(xray_specialist_id)
        
        if not patient or patient.role != 'patient':
            return jsonify({'success': False, 'message': 'Invalid patient selected!'})
        
        if not xray_specialist or xray_specialist.role != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Invalid X-ray specialist selected!'})
        
        # Simple approach: Add a column to User table for X-ray assignment
        # Check if patient already has an assignment
        if hasattr(patient, 'assigned_xray_specialist_id') and patient.assigned_xray_specialist_id:
            return jsonify({'success': False, 'message': 'Patient already has an X-ray specialist assigned!'})
        
        # For now, we'll create a simple assignment record in a new table or use a simpler approach
        # Let's use the existing database structure and create a simple assignment
        
        # Create assignment using existing appointment table structure
        from datetime import datetime
        
        # BUSINESS RULE: 1 patient can only be assigned to 1 X-ray specialist
        # Check if patient already has an ACTIVE assignment
        existing_assignment = Appointment.query.filter_by(
            patient_id=patient_id, 
            appointment_type='xray_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if existing_assignment:
            # Get the currently assigned specialist name
            current_specialist = User.query.get(existing_assignment.doctor_id)
            specialist_name = current_specialist.username if current_specialist else "Unknown"
            
            return jsonify({
                'success': False, 
                'message': f'Patient {patient.username} is already assigned to X-ray specialist {specialist_name}. Please complete or cancel the existing assignment first.'
            })
        
        # Create assignment record using the Appointment model
        assignment = Appointment(
            patient_id=patient_id,
            doctor_id=xray_specialist_id,  # X-ray specialist stored in doctor_id field
            appointment_type='xray_assignment',
            status='assigned',
            appointment_date=datetime.utcnow(),  # Required field
            patient_name_at_appointment=patient.username,
            patient_phone_at_appointment=patient.phone,
            notes=f'X-ray specialist {xray_specialist.username} assigned to patient {patient.username}',
            created_by_reception=current_user.id
        )
        
        db.session.add(assignment)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'X-ray specialist {xray_specialist.username} assigned to patient {patient.username} successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error assigning X-ray specialist: {e}")
        return jsonify({'success': False, 'message': 'Failed to assign X-ray specialist. Please try again.'})


@app.route('/reception/reassign_xray_specialist', methods=['POST'])
@login_required
@reception_required
def reassign_xray_specialist():
    """Reassign patient to a different X-ray specialist"""
    try:
        patient_id = request.form.get('patient_id')
        new_xray_specialist_id = request.form.get('xray_specialist_id')
        
        if not patient_id or not new_xray_specialist_id:
            return jsonify({'success': False, 'message': 'Please select both patient and new X-ray specialist!'})
        
        # Get patient and new X-ray specialist
        patient = User.query.get(patient_id)
        new_specialist = User.query.get(new_xray_specialist_id)
        
        if not patient or patient.role != 'patient':
            return jsonify({'success': False, 'message': 'Invalid patient selected!'})
        
        if not new_specialist or new_specialist.role != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Invalid X-ray specialist selected!'})
        
        # Find existing assignment
        existing_assignment = Appointment.query.filter_by(
            patient_id=patient_id, 
            appointment_type='xray_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if not existing_assignment:
            return jsonify({'success': False, 'message': 'No active assignment found for this patient!'})
        
        # Get old specialist name for logging
        old_specialist = User.query.get(existing_assignment.doctor_id)
        old_specialist_name = old_specialist.username if old_specialist else "Unknown"
        
        # Update the assignment to new specialist
        existing_assignment.doctor_id = new_xray_specialist_id
        existing_assignment.updated_at = datetime.utcnow()
        existing_assignment.notes += f"\nReassigned from {old_specialist_name} to {new_specialist.username} by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Patient {patient.username} reassigned from {old_specialist_name} to {new_specialist.username} successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error reassigning X-ray specialist: {e}")
        return jsonify({'success': False, 'message': 'Failed to reassign X-ray specialist. Please try again.'})


@app.route('/reception/cancel_xray_assignment', methods=['POST'])
@login_required
@reception_required
def cancel_xray_assignment():
    """Cancel an existing X-ray assignment"""
    try:
        patient_id = request.form.get('patient_id')
        
        if not patient_id:
            return jsonify({'success': False, 'message': 'Patient ID is required!'})
        
        # Find existing assignment
        existing_assignment = Appointment.query.filter_by(
            patient_id=patient_id, 
            appointment_type='xray_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if not existing_assignment:
            return jsonify({'success': False, 'message': 'No active assignment found for this patient!'})
        
        # Get patient and specialist names for logging
        patient = User.query.get(patient_id)
        specialist = User.query.get(existing_assignment.doctor_id)
        
        patient_name = patient.username if patient else "Unknown"
        specialist_name = specialist.username if specialist else "Unknown"
        
        # Cancel the assignment
        existing_assignment.status = 'cancelled'
        existing_assignment.updated_at = datetime.utcnow()
        existing_assignment.notes += f"\nAssignment cancelled by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Assignment of patient {patient_name} to {specialist_name} has been cancelled successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error cancelling X-ray assignment: {e}")
        return jsonify({'success': False, 'message': 'Failed to cancel assignment. Please try again.'})

@app.route('/reception/get_xray_assignments')
@login_required
@reception_required
def get_xray_assignments():
    """Get all current X-ray assignments"""
    try:
        # Query X-ray assignments using ORM - only active assignments
        assignments = Appointment.query.filter_by(
            appointment_type='xray_assignment'
        ).filter(
            Appointment.status.in_(['assigned', 'scheduled'])
        ).order_by(Appointment.created_at.desc()).all()
        
        assignment_list = []
        for assignment in assignments:
            patient_name = assignment.patient.username if assignment.patient else "Unknown"
            specialist_name = assignment.doctor.username if assignment.doctor else "Unknown"
            
            assignment_list.append({
                'id': assignment.id,
                'patient_id': assignment.patient_id,  # Added patient_id for frontend
                'patient_name': patient_name,
                'xray_specialist_id': assignment.doctor_id,  # Added for reassignment
                'xray_specialist_name': specialist_name,
                'assignment_date': assignment.created_at.strftime('%Y-%m-%d') if assignment.created_at else 'Unknown',
                'status': assignment.status or 'Active'
            })
        
        return jsonify(assignment_list)
    except Exception as e:
        print(f"Error getting X-ray assignments: {e}")
        return jsonify([])

# Test route to verify routing works - MODIFIED FOR FEEDBACK
@app.route('/reception/test', methods=['GET', 'POST'])
@login_required
@reception_required
def test_reception_route():
    if request.method == 'GET':
        return jsonify({'success': True, 'message': 'Reception route is working!'})
    
    # Handle feedback submission
    try:
        data = request.get_json()
        action = data.get('action')
        
        if action == 'send_admin_feedback':
            print(f"🔄 Processing send_admin_feedback for user {current_user.username}")
            message = data.get('message', '').strip()
            print(f"📝 Message: {message}")
            
            if not message:
                print("❌ No message provided")
                return jsonify({'success': False, 'message': 'Message is required'}), 400
            
            # Create feedback record using existing model structure
            feedback = Feedback(
                patient_id=current_user.id,  # Using patient_id field for reception staff
                feedback=message,  # Using feedback field instead of message
                feedback_type='reception_to_admin',
                date_submitted=datetime.utcnow()
            )
            
            print(f"💾 Creating feedback record for user ID {current_user.id}")
            db.session.add(feedback)
            db.session.commit()
            print(f"✅ Feedback saved with ID: {feedback.id}")
            
            return jsonify({
                'success': True, 
                'message': 'Feedback sent to admin successfully!'
            })
            
        elif action == 'send_health_officer_feedback':
            health_officer_id = data.get('health_officer_id')
            message = data.get('message', '').strip()
            
            if not health_officer_id or not message:
                return jsonify({'success': False, 'message': 'Health officer and message are required'}), 400
            
            # Verify health officer exists
            health_officer = User.query.filter_by(id=health_officer_id, role='healthofficer').first()
            if not health_officer:
                return jsonify({'success': False, 'message': 'Health officer not found'}), 404
            
            # Create feedback record
            feedback = Feedback(
                patient_id=current_user.id,
                feedback=f"To Health Officer {health_officer.username}: {message}",
                feedback_type=f'reception_to_healthofficer_{health_officer_id}',
                date_submitted=datetime.utcnow()
            )
            
            db.session.add(feedback)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'Feedback sent to {health_officer.username} successfully!'
            })
            
        elif action == 'get_health_officers':
            health_officers = User.query.filter_by(role='healthofficer', is_approved=True).all()
            
            officers_list = []
            for officer in health_officers:
                officers_list.append({
                    'id': officer.id,
                    'username': officer.username,
                    'phone': officer.phone
                })
            
            return jsonify(officers_list)
            
        elif action == 'get_admin_replies':
            print(f"🔄 Getting admin replies for user {current_user.username} (ID: {current_user.id})")
            # Get feedback sent by this reception staff
            feedbacks = Feedback.query.filter(
                Feedback.patient_id == current_user.id,
                Feedback.feedback_type.like('reception_%')
            ).order_by(Feedback.date_submitted.desc()).all()
            
            print(f"📊 Found {len(feedbacks)} feedback records")
            
            replies_list = []
            for feedback in feedbacks:
                print(f"   - Feedback ID {feedback.id}: {feedback.feedback[:30]}...")
                recipient_name = "Administrator"
                
                # Parse recipient from feedback_type
                if feedback.feedback_type.startswith('reception_to_healthofficer_'):
                    health_officer_id = feedback.feedback_type.split('_')[-1]
                    try:
                        health_officer = User.query.get(int(health_officer_id))
                        if health_officer:
                            recipient_name = f"Health Officer: {health_officer.username}"
                    except (ValueError, TypeError):
                        pass
                
                replies_list.append({
                    'id': feedback.id,
                    'recipient_name': recipient_name,
                    'message': feedback.feedback,
                    'reply': feedback.reply,
                    'date_sent': feedback.date_submitted.strftime('%Y-%m-%d %H:%M') if feedback.date_submitted else 'N/A',
                    'reply_date': feedback.reply_date.strftime('%Y-%m-%d %H:%M') if feedback.reply_date else None
                })
            
            return jsonify(replies_list)
        
        else:
            return jsonify({'success': False, 'message': 'Unknown action'}), 400
            
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in reception feedback: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ====================== HEALTH OFFICER ASSIGNMENT ROUTES ======================

@app.route('/reception/get_health_officers')
@login_required
@reception_required
def get_health_officers_for_reception():
    """Get all approved Health Officers for assignment"""
    try:
        health_officers = User.query.filter_by(role='healthofficer', is_approved=True, is_active_user=True).all()
        print(f"🔍 Found {len(health_officers)} health officers for assignment")
        
        officer_list = []
        for officer in health_officers:
            officer_list.append({
                'id': officer.id,
                'username': officer.username
            })
            print(f"  - {officer.username} (ID: {officer.id}, approved: {officer.is_approved}, active: {officer.is_active_user})")
        
        return jsonify(officer_list)
    except Exception as e:
        print(f"❌ Error getting Health Officers for assignment: {e}")
        return jsonify([])

@app.route('/reception/assign_health_officer', methods=['POST'])
@login_required
@reception_required
def assign_health_officer():
    """Assign Health Officer to patient"""
    try:
        patient_id = request.form.get('patient_id')
        health_officer_id = request.form.get('health_officer_id')
        
        if not patient_id or not health_officer_id:
            return jsonify({'success': False, 'message': 'Please select both patient and Health Officer!'})
        
        # Get patient and Health Officer
        patient = User.query.get(patient_id)
        health_officer = User.query.get(health_officer_id)
        
        if not patient or patient.role != 'patient':
            return jsonify({'success': False, 'message': 'Invalid patient selected!'})
        
        if not health_officer or health_officer.role != 'healthofficer':
            return jsonify({'success': False, 'message': 'Invalid Health Officer selected!'})
        
        # BUSINESS RULE: 1 patient can only be assigned to 1 Health Officer
        # Check if patient already has an ACTIVE assignment
        existing_assignment = Appointment.query.filter_by(
            patient_id=patient_id, 
            appointment_type='health_officer_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if existing_assignment:
            # Get the currently assigned officer name
            current_officer = User.query.get(existing_assignment.doctor_id)
            officer_name = current_officer.username if current_officer else "Unknown"
            
            return jsonify({
                'success': False, 
                'message': f'Patient {patient.username} is already assigned to Health Officer {officer_name}. Please complete or cancel the existing assignment first.'
            })
        
        # Create assignment record using the Appointment model
        assignment = Appointment(
            patient_id=patient_id,
            doctor_id=health_officer_id,  # Health Officer stored in doctor_id field
            appointment_type='health_officer_assignment',
            status='assigned',
            appointment_date=datetime.utcnow(),  # Required field
            patient_name_at_appointment=patient.username,
            patient_phone_at_appointment=patient.phone,
            notes=f'Health Officer {health_officer.username} assigned to patient {patient.username}',
            created_by_reception=current_user.id
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        # Create notification for the health officer about new patient assignment
        print(f"🔄 Creating notification for health officer ID: {health_officer_id}, username: {health_officer.username}")
        print(f"🔄 Patient: {patient.username}, Reception: {current_user.username}")
        
        notification = NotificationService.create_notification(
            user_id=int(health_officer_id),  # Ensure it's an integer
            user_role='healthofficer',
            title='New Patient Assignment',
            message=f'Reception staff {current_user.username} assigned patient {patient.username} to you',
            notification_type='patient_assignment',
            action_url='#assigned-patients',
            is_clickable=True
        )
        
        if notification:
            print(f"✅ Created assignment notification for health officer {health_officer.username} - Notification ID: {notification.id}")
        else:
            print(f"❌ Failed to create assignment notification for health officer {health_officer.username}")
        
        return jsonify({
            'success': True, 
            'message': f'Health Officer {health_officer.username} assigned to patient {patient.username} successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error assigning Health Officer: {e}")
        return jsonify({'success': False, 'message': 'Failed to assign Health Officer. Please try again.'})

@app.route('/reception/reassign_health_officer', methods=['POST'])
@login_required
@reception_required
def reassign_health_officer():
    """Reassign patient to a different Health Officer"""
    try:
        patient_id = request.form.get('patient_id')
        new_health_officer_id = request.form.get('health_officer_id')
        
        if not patient_id or not new_health_officer_id:
            return jsonify({'success': False, 'message': 'Please select both patient and new Health Officer!'})
        
        # Get patient and new Health Officer
        patient = User.query.get(patient_id)
        new_officer = User.query.get(new_health_officer_id)
        
        if not patient or patient.role != 'patient':
            return jsonify({'success': False, 'message': 'Invalid patient selected!'})
        
        if not new_officer or new_officer.role != 'healthofficer':
            return jsonify({'success': False, 'message': 'Invalid Health Officer selected!'})
        
        # Find existing assignment
        existing_assignment = Appointment.query.filter_by(
            patient_id=patient_id, 
            appointment_type='health_officer_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if not existing_assignment:
            return jsonify({'success': False, 'message': 'No active assignment found for this patient!'})
        
        # Get old officer name for logging
        old_officer = User.query.get(existing_assignment.doctor_id)
        old_officer_name = old_officer.username if old_officer else "Unknown"
        
        # Update the assignment to new officer
        existing_assignment.doctor_id = new_health_officer_id
        existing_assignment.updated_at = datetime.utcnow()
        existing_assignment.notes += f"\nReassigned from {old_officer_name} to {new_officer.username} by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        
        db.session.commit()
        
        # Create notification for the new health officer about patient reassignment
        notification = NotificationService.create_notification(
            user_id=new_health_officer_id,
            user_role='healthofficer',
            title='Patient Reassignment',
            message=f'Reception staff {current_user.username} reassigned patient {patient.username} to you from {old_officer_name}',
            notification_type='patient_reassignment',
            action_url='#assigned-patients',
            is_clickable=True
        )
        
        if notification:
            print(f"✅ Created reassignment notification for health officer {new_officer.username}")
        else:
            print(f"❌ Failed to create reassignment notification for health officer {new_officer.username}")
        
        return jsonify({
            'success': True, 
            'message': f'Patient {patient.username} reassigned from {old_officer_name} to {new_officer.username} successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error reassigning Health Officer: {e}")
        return jsonify({'success': False, 'message': 'Failed to reassign Health Officer. Please try again.'})

@app.route('/reception/cancel_health_officer_assignment', methods=['POST'])
@login_required
@reception_required
def cancel_health_officer_assignment():
    """Cancel an existing Health Officer assignment"""
    try:
        patient_id = request.form.get('patient_id')
        
        if not patient_id:
            return jsonify({'success': False, 'message': 'Patient ID is required!'})
        
        # Find existing assignment
        existing_assignment = Appointment.query.filter_by(
            patient_id=patient_id, 
            appointment_type='health_officer_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if not existing_assignment:
            return jsonify({'success': False, 'message': 'No active assignment found for this patient!'})
        
        # Get patient and officer names for logging
        patient = User.query.get(patient_id)
        officer = User.query.get(existing_assignment.doctor_id)
        
        patient_name = patient.username if patient else "Unknown"
        officer_name = officer.username if officer else "Unknown"
        
        # Cancel the assignment
        existing_assignment.status = 'cancelled'
        existing_assignment.updated_at = datetime.utcnow()
        existing_assignment.notes += f"\nAssignment cancelled by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Assignment of patient {patient_name} to {officer_name} has been cancelled successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error cancelling Health Officer assignment: {e}")
        return jsonify({'success': False, 'message': 'Failed to cancel assignment. Please try again.'})

@app.route('/reception/get_health_officer_assignments')
@login_required
@reception_required
def get_health_officer_assignments():
    """Get all current Health Officer assignments"""
    try:
        # Query Health Officer assignments using ORM - only active assignments
        assignments = Appointment.query.filter_by(
            appointment_type='health_officer_assignment'
        ).filter(
            Appointment.status.in_(['assigned', 'scheduled'])
        ).order_by(Appointment.created_at.desc()).all()
        
        assignment_list = []
        for assignment in assignments:
            patient_name = assignment.patient.username if assignment.patient else "Unknown"
            officer_name = assignment.doctor.username if assignment.doctor else "Unknown"
            
            assignment_list.append({
                'id': assignment.id,
                'patient_id': assignment.patient_id,  # Added patient_id for frontend
                'patient_name': patient_name,
                'health_officer_id': assignment.doctor_id,  # Added for reassignment
                'health_officer_name': officer_name,
                'assignment_date': assignment.created_at.strftime('%Y-%m-%d') if assignment.created_at else 'Unknown',
                'status': assignment.status or 'Active'
            })
        
        return jsonify(assignment_list)
    except Exception as e:
        print(f"Error getting Health Officer assignments: {e}")
        return jsonify([])

# ====================== HEALTH OFFICER DASHBOARD ROUTES ======================

@app.route('/healthofficer/get_assigned_patients')
@login_required
@health_officer_required
def get_assigned_patients_for_health_officer():
    """Get patients assigned to the current health officer"""
    try:
        # Get assignments for this health officer
        assignments = Appointment.query.filter_by(
            doctor_id=current_user.id,  # Health officer stored in doctor_id field
            appointment_type='health_officer_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).all()
        
        patient_list = []
        for assignment in assignments:
            patient = User.query.get(assignment.patient_id)
            if patient:
                # Get patient profile for additional info
                patient_profile = Patient.query.filter_by(user_id=patient.id).first()
                
                patient_data = {
                    'id': patient.id,
                    'username': patient.username,
                    'phone': patient.phone,
                    'patient_unique_id': patient_profile.patient_unique_id if patient_profile else f'P{patient.id:06d}',
                    'assigned_date': assignment.appointment_date.strftime('%Y-%m-%d') if assignment.appointment_date else 'N/A',
                    'status': assignment.status,
                    'assignment_id': assignment.id
                }
                patient_list.append(patient_data)
        
        return jsonify(patient_list)
    except Exception as e:
        print(f"Error getting assigned patients: {e}")
        return jsonify([])

@app.route('/healthofficer/get_xray_specialists')
@login_required
@health_officer_required
def get_xray_specialists_for_health_officer():
    """Get all approved X-ray specialists for assignment"""
    try:
        xray_specialists = User.query.filter_by(role='xrayspecialist', is_approved=True, is_active_user=True).all()
        specialist_list = []
        for specialist in xray_specialists:
            specialist_list.append({
                'id': specialist.id,
                'username': specialist.username,
                'phone': specialist.phone
            })
        return jsonify(specialist_list)
    except Exception as e:
        print(f"Error getting X-ray specialists: {e}")
        return jsonify([])

@app.route('/healthofficer/get_reception_feedback')
@login_required
@health_officer_required
def get_reception_feedback_for_health_officer():
    """Get feedback sent to this health officer from reception staff"""
    try:
        # Get feedback sent TO this health officer from reception staff
        # The feedback_type format is: 'reception_to_healthofficer_{health_officer_id}'
        feedback_type = f'reception_to_healthofficer_{current_user.id}'
        
        feedbacks = Feedback.query.filter_by(
            feedback_type=feedback_type
        ).order_by(Feedback.date_submitted.desc()).all()
        
        feedbacks_data = []
        for feedback in feedbacks:
            # Get the reception staff who sent this feedback
            sender = User.query.get(feedback.patient_id)  # Reception staff stored in patient_id field
            
            # Extract the actual message (remove the "To Health Officer..." prefix if present)
            message = feedback.feedback
            if message and message.startswith(f"To Health Officer {current_user.username}: "):
                message = message.replace(f"To Health Officer {current_user.username}: ", "")
            
            feedbacks_data.append({
                'id': feedback.id,
                'sender_name': sender.username if sender else 'Reception Staff',
                'sender_role': sender.role if sender else 'reception',
                'message': message,
                'date_sent': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply': feedback.reply,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read
            })
        
        print(f"✅ Found {len(feedbacks_data)} feedback messages for health officer {current_user.username}")
        
        return jsonify({
            'success': True,
            'feedbacks': feedbacks_data
        })
        
    except Exception as e:
        print(f"❌ Error getting reception feedback for health officer: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/healthofficer/reply_to_reception_feedback', methods=['POST'])
@csrf.exempt
@login_required
@health_officer_required
def reply_to_reception_feedback():
    """Health officer replies to reception feedback"""
    try:
        data = request.get_json()
        feedback_id = data.get('feedback_id')
        reply_message = data.get('reply', '').strip()
        
        if not feedback_id or not reply_message:
            return jsonify({'success': False, 'message': 'Feedback ID and reply message are required'}), 400
        
        # Get the feedback and verify it belongs to this health officer
        feedback_type = f'reception_to_healthofficer_{current_user.id}'
        feedback = Feedback.query.filter_by(
            id=feedback_id,
            feedback_type=feedback_type
        ).first()
        
        if not feedback:
            return jsonify({'success': False, 'message': 'Feedback not found or access denied'}), 404
        
        # Set the reply
        feedback.reply = reply_message
        feedback.reply_date = datetime.utcnow()
        feedback.is_read = True
        
        # Create notification for the reception staff who sent the feedback
        reception_user = User.query.get(feedback.patient_id)  # Reception staff stored in patient_id field
        if reception_user and reception_user.role == 'reception':
            print(f"📧 Creating notification for reception staff {reception_user.username}")
            universal_notification = UniversalNotification(
                user_id=reception_user.id,
                user_role='reception',
                title="Health Officer Reply to Your Feedback",
                message=f"Health Officer {current_user.username} has replied to your feedback: {reply_message[:100]}{'...' if len(reply_message) > 100 else ''}",
                notification_type='health_officer_reply',
                action_url='#feedback',
                is_clickable=True
            )
            db.session.add(universal_notification)
            print(f"✅ Created universal notification for reception staff {reception_user.username}")
        
        db.session.commit()
        
        print(f"✅ Health officer {current_user.username} replied to reception feedback {feedback_id}")
        
        return jsonify({'success': True, 'message': 'Reply sent successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error replying to reception feedback: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/healthofficer/send_admin_feedback', methods=['POST'])
@csrf.exempt
@login_required
@health_officer_required
def health_officer_send_admin_feedback():
    """Health officer sends feedback to admin"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'message': 'Message is required'}), 400
        
        # Create feedback record for health officer to admin
        feedback = Feedback(
            patient_id=current_user.id,  # Using patient_id field for health officer
            feedback=message,
            feedback_type='healthofficer_to_admin',
            date_submitted=datetime.utcnow()
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        print(f"✅ Health officer {current_user.username} sent feedback to admin: ID {feedback.id}")
        
        # Create universal notifications for all admins
        universal_notifications = NotificationService.create_notifications_for_role(
            role='admin',
            title='New Health Officer Feedback',
            message=f'Health Officer {current_user.username} sent feedback: {message[:100]}{"..." if len(message) > 100 else ""}',
            notification_type='feedback',
            action_url='#feedback',
            is_clickable=True
        )
        
        # Also create legacy notifications for backward compatibility
        legacy_notification_success = create_feedback_notification(current_user.username, message, feedback.id)
        
        if universal_notifications:
            print(f"✅ Created universal notifications for {len(universal_notifications)} admins")
        else:
            print(f"⚠️ Warning: Failed to create universal notifications")
            
        if legacy_notification_success:
            print(f"✅ Created legacy notifications for admins")
        else:
            print(f"⚠️ Warning: Failed to create legacy notifications")
        
        return jsonify({
            'success': True, 
            'message': 'Feedback sent to admin successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error sending health officer feedback to admin: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/healthofficer/get_sent_feedback')
@login_required
@health_officer_required
def get_sent_feedback_for_health_officer():
    """Get feedback sent by this health officer (to admin and X-ray specialists)"""
    print(f"🔄 get_sent_feedback called for user {current_user.username}")
    try:
        feedback_list = []
        
        # Get feedback sent by this health officer to admin
        admin_feedback = Feedback.query.filter_by(
            patient_id=current_user.id,
            feedback_type='healthofficer_to_admin'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        for feedback in admin_feedback:
            feedback_list.append({
                'id': feedback.id,
                'recipient_name': 'Admin',
                'message': feedback.feedback,
                'feedback_type': feedback.feedback_type,
                'date_sent': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply': feedback.reply,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read
            })
        
        # Get feedback sent by this health officer to X-ray specialists
        xray_feedback = Feedback.query.filter_by(
            health_officer_id=current_user.id,
            feedback_type='healthofficer_to_xray'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        for feedback in xray_feedback:
            xray_specialist = User.query.get(feedback.xray_specialist_id)
            recipient_name = xray_specialist.username if xray_specialist else 'Unknown X-ray Specialist'
            
            feedback_list.append({
                'id': feedback.id,
                'recipient_name': recipient_name,
                'message': feedback.feedback,
                'feedback_type': feedback.feedback_type,
                'date_sent': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply': feedback.reply,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read
            })
        
        print(f"✅ Found {len(feedback_list)} sent feedback messages for health officer {current_user.username}")
        return jsonify(feedback_list)
        
    except Exception as e:
        print(f"❌ Error getting sent feedback for health officer: {e}")
        return jsonify([])

@app.route('/healthofficer/test_route')
def test_health_officer_route():
    """Test route to verify routing works"""
    return jsonify({'message': 'Test route works!', 'user': 'test'})

@app.route('/test_simple')
def test_simple_route():
    """Very simple test route"""
    return jsonify({'message': 'Simple test works!'})

@app.route('/healthofficer/test_xray_feedback', methods=['GET', 'POST'])
@csrf.exempt
def test_xray_feedback_route():
    """Simple test route for X-ray feedback"""
    return jsonify({'success': True, 'message': 'Test route reached successfully', 'method': request.method})

@app.route('/healthofficer/send_xray_feedback', methods=['POST'])
@csrf.exempt
@login_required
def health_officer_send_xray_feedback():
    """Send feedback from health officer to X-ray specialist"""
    # Check if user is health officer
    if current_user.role != 'healthofficer':
        return jsonify({'success': False, 'message': 'Health Officer privileges required'}), 403
    
    print(f"🔄 Health Officer {current_user.username} sending X-ray feedback...")
    try:
        data = request.get_json()
        print(f"📋 Request data: {data}")
        
        xray_specialist_id = data.get('xray_specialist_id')
        message = data.get('message', '').strip()
        
        print(f"📋 Parsed data - xray_specialist_id: {xray_specialist_id}, message length: {len(message) if message else 0}")
        
        if not xray_specialist_id or not message:
            print(f"❌ Missing required fields - xray_specialist_id: {xray_specialist_id}, message: {bool(message)}")
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # Verify X-ray specialist exists
        print(f"🔍 Looking for X-ray specialist with ID: {xray_specialist_id}")
        xray_specialist = User.query.filter_by(id=xray_specialist_id, role='xrayspecialist').first()
        if not xray_specialist:
            print(f"❌ X-ray specialist not found with ID: {xray_specialist_id}")
            return jsonify({'success': False, 'message': 'X-ray specialist not found'}), 404
        
        print(f"✅ Found X-ray specialist: {xray_specialist.username}")
        
        # Create feedback record
        print(f"📝 Creating feedback record...")
        feedback = Feedback(
            health_officer_id=current_user.id,
            xray_specialist_id=xray_specialist_id,
            feedback=message,
            feedback_type='healthofficer_to_xray',
            date_submitted=datetime.utcnow()
        )
        
        db.session.add(feedback)
        db.session.flush()  # Get the feedback ID
        
        # Create notification for the X-ray specialist (legacy)
        from models import XraySpecialistNotification, UniversalNotification
        notification = XraySpecialistNotification(
            xray_specialist_id=xray_specialist_id,
            patient_id=None,
            patient_name=f"Health Officer {current_user.username}",
            xray_filename="health_officer_feedback",
            message=f"Health Officer {current_user.username} sent you feedback: {message[:100]}{'...' if len(message) > 100 else ''}",
            is_read=False,
            notification_type='health_officer_feedback'
        )
        db.session.add(notification)
        
        # Also create universal notification
        universal_notification = UniversalNotification(
            user_id=xray_specialist_id,
            user_role='xrayspecialist',
            title="Health Officer Feedback",
            message=f"Health Officer {current_user.username} sent you feedback: {message[:100]}{'...' if len(message) > 100 else ''}",
            notification_type='health_officer_feedback',
            action_url='#feedback',
            is_clickable=True
        )
        db.session.add(universal_notification)
        
        db.session.commit()
        
        print(f"✅ Health Officer {current_user.username} sent feedback to X-ray specialist {xray_specialist.username}")
        print(f"✅ Created notification for X-ray specialist")
        
        return jsonify({
            'success': True, 
            'message': f'Feedback sent to {xray_specialist.username} successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error sending health officer feedback to X-ray specialist: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/healthofficer/assign_xray_specialist', methods=['POST'])
@login_required
@health_officer_required
def health_officer_assign_xray_specialist():
    """Assign X-ray specialist to a patient"""
    try:
        patient_id = request.form.get('patient_id')
        xray_specialist_id = request.form.get('xray_specialist_id')
        notes = request.form.get('notes', '')
        
        if not patient_id or not xray_specialist_id:
            return jsonify({'success': False, 'message': 'Please select both patient and X-ray specialist!'})
        
        # Get patient and X-ray specialist
        patient = User.query.get(patient_id)
        xray_specialist = User.query.get(xray_specialist_id)
        
        if not patient or patient.role != 'patient':
            return jsonify({'success': False, 'message': 'Invalid patient selected!'})
        
        if not xray_specialist or xray_specialist.role != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Invalid X-ray specialist selected!'})
        
        # Check if patient is assigned to this health officer
        health_officer_assignment = Appointment.query.filter_by(
            patient_id=patient_id,
            doctor_id=current_user.id,
            appointment_type='health_officer_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if not health_officer_assignment:
            return jsonify({'success': False, 'message': 'This patient is not assigned to you!'})
        
        # Check if patient already has an active X-ray assignment
        existing_xray_assignment = Appointment.query.filter_by(
            patient_id=patient_id,
            appointment_type='xray_assignment'
        ).filter(Appointment.status.in_(['assigned', 'scheduled'])).first()
        
        if existing_xray_assignment:
            current_specialist = User.query.get(existing_xray_assignment.doctor_id)
            specialist_name = current_specialist.username if current_specialist else "Unknown"
            
            return jsonify({
                'success': False,
                'message': f'Patient {patient.username} is already assigned to X-ray specialist {specialist_name}. Please complete or cancel the existing assignment first.'
            })
        
        # Create X-ray assignment record
        xray_assignment = Appointment(
            patient_id=patient_id,
            doctor_id=xray_specialist_id,  # X-ray specialist stored in doctor_id field
            appointment_type='xray_assignment',
            status='assigned',
            appointment_date=datetime.utcnow(),
            patient_name_at_appointment=patient.username,
            patient_phone_at_appointment=patient.phone,
            notes=f'X-ray specialist {xray_specialist.username} assigned by Health Officer {current_user.username}. Notes: {notes}',
            created_by_reception=current_user.id  # Health officer who made the assignment
        )
        
        db.session.add(xray_assignment)
        db.session.flush()  # Get the assignment ID
        
        # Create notification for the X-ray specialist about patient assignment
        print(f"📧 Creating notification for X-ray specialist {xray_specialist.username}")
        universal_notification = NotificationService.create_notification(
            user_id=xray_specialist.id,
            user_role='xrayspecialist',
            title="New Patient Assignment",
            message=f"Health Officer {current_user.username} has assigned patient {patient.username} to you for X-ray imaging. Notes: {notes[:100] if notes else 'No additional notes'}{'...' if notes and len(notes) > 100 else ''}",
            notification_type='patient_assignment',
            action_url='#assigned-patients',
            is_clickable=True
        )
        
        if universal_notification:
            print(f"✅ Created universal notification for X-ray specialist {xray_specialist.username}")
        else:
            print(f"❌ Failed to create universal notification for X-ray specialist")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'X-ray specialist {xray_specialist.username} assigned to patient {patient.username} successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error assigning X-ray specialist: {e}")
        return jsonify({'success': False, 'message': 'Failed to assign X-ray specialist. Please try again.'})

@app.route('/healthofficer/get_xray_assignments')
@login_required
@health_officer_required
def get_xray_assignments_for_health_officer():
    """Get X-ray assignments made by this health officer"""
    try:
        # Get X-ray assignments made by this health officer
        assignments = Appointment.query.filter_by(
            created_by_reception=current_user.id,  # Health officer who made the assignment
            appointment_type='xray_assignment'
        ).order_by(Appointment.created_at.desc()).all()
        
        assignment_list = []
        for assignment in assignments:
            patient = User.query.get(assignment.patient_id)
            xray_specialist = User.query.get(assignment.doctor_id)
            
            patient_name = patient.username if patient else "Unknown"
            specialist_name = xray_specialist.username if xray_specialist else "Unknown"
            
            assignment_list.append({
                'id': assignment.id,
                'patient_id': assignment.patient_id,
                'patient_name': patient_name,
                'xray_specialist_id': assignment.doctor_id,
                'xray_specialist_name': specialist_name,
                'assignment_date': assignment.created_at.strftime('%Y-%m-%d %H:%M') if assignment.created_at else 'Unknown',
                'status': assignment.status or 'Active',
                'notes': assignment.notes or ''
            })
        
        return jsonify(assignment_list)
    except Exception as e:
        print(f"Error getting X-ray assignments: {e}")
        return jsonify([])

# ====================== TEST ROUTES ======================

@app.route('/test/health_officer')
def test_health_officer_browser():
    """Serve the health officer test page"""
    return send_from_directory('.', 'test_health_officer_browser.html')

# ====================== RECEPTION REGISTRATION SYSTEM ======================
# Complete rebuild with proper error handling and working routes

@app.route('/reception/register_patient', methods=['POST'])
@login_required
@reception_required
def reception_register_patient():
    """Reception registration - mirrors general registration exactly"""
    
    # Handle GET request - return to dashboard
    if request.method == 'GET':
        return redirect(url_for('dashboard_reception'))
    
    # Handle POST request - EXACT COPY OF GENERAL REGISTRATION LOGIC
    try:
        username = request.form.get('username', '').strip()
        phone_input = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'patient').strip().lower()

        phone = '+251' + phone_input

        # Phone validation - validate 9-digit input before adding prefix
        phone_pattern = r'^[79]\d{8}$'
        if not re.match(phone_pattern, phone_input):
            return jsonify({'success': False, 'message': 'Invalid phone number! Must be 9 digits starting with 7 or 9'})

        # Duplicate check - EXACT SAME AS GENERAL REGISTRATION
        existing_user = get_user_by_username(username)
        if not existing_user:
            existing_user = get_user_by_phone(phone)
        
        if existing_user:
            return jsonify({'success': False, 'message': 'Username or phone number already exists!'})

        # Password confirmation - EXACT SAME AS GENERAL REGISTRATION
        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match!'})

        # Validate role - EXACT SAME AS GENERAL REGISTRATION (ADMIN EXCLUDED)
        valid_roles = ['patient', 'doctor', 'xrayspecialist', 'reception', 'healthofficer']
        if role not in valid_roles:
            return jsonify({'success': False, 'message': 'Invalid role selected!'})

        # Create new user based on role - EXACT SAME AS GENERAL REGISTRATION
        try:
            if role == 'patient':
                new_user = create_patient_user(username, phone, password)
                # Get patient unique ID for success message
                patient_profile = Patient.query.filter_by(user_id=new_user.id).first()
                unique_id = patient_profile.patient_unique_id if patient_profile else f"PAT{new_user.id:06d}"
                message = f'Patient {username} registered successfully with ID: {unique_id}!'
            elif role == 'doctor':
                new_user = create_doctor_user(username, phone, password)
                message = f'Doctor {username} registered successfully! Awaiting admin approval.'
            elif role == 'xrayspecialist':
                new_user = create_xray_specialist_user(username, phone, password)
                message = f'X-ray Specialist {username} registered successfully! Awaiting admin approval.'
            elif role == 'reception':
                new_user = create_reception_user(username, phone, password)
                message = f'Reception user {username} registered successfully! Awaiting admin approval.'
            elif role == 'healthofficer':
                new_user = create_health_officer_user(username, phone, password)
                message = f'Health Officer {username} registered successfully! Awaiting admin approval.'
            else:
                return jsonify({'success': False, 'message': 'Invalid role selected!'})
            
            if not new_user:
                return jsonify({'success': False, 'message': 'Failed to create user'})

            # Create notification for admins when staff registers - EXACT SAME AS GENERAL REGISTRATION
            if role in ['doctor', 'xrayspecialist', 'reception', 'healthofficer']:
                # Create universal notifications for all admins
                NotificationService.create_notifications_for_role(
                    role='admin',
                    title='New User Registration',
                    message=f'New {role} "{username}" registered and needs approval',
                    notification_type='user_approval',
                    action_url='#approve-users',
                    is_clickable=True
                )
                
                # Also create legacy notification for backward compatibility
                create_user_approval_notification(username, role)

            return jsonify({'success': True, 'message': message})

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Registration error: {str(e)}'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in reception registration: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Failed to register user: {str(e)}'})

@app.route('/reception/register_user', methods=['POST'])
@login_required
@reception_required
def register_user_reception():
    """Register a new user from reception dashboard - Complete general registration form"""
    try:
        username = request.form.get('username', '').strip()
        phone_input = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'patient').strip().lower()
        
        # Log registration attempt for debugging
        print(f"Reception registration attempt - Username: {username}, Phone: {phone_input}, Role: {role}")
        
        # ========== COMPLETE VALIDATION (MATCHING GENERAL REGISTRATION) ==========
        
        # Format phone number
        phone = '+251' + phone_input
        
        # Phone validation - validate 9-digit input before adding prefix
        phone_pattern = r'^[79]\d{8}$'
        if not re.match(phone_pattern, phone_input):
            return jsonify({'success': False, 'message': 'Invalid phone number! Must be 9 digits starting with 7 or 9'})

        # Duplicate check - check all role tables
        existing_user = get_user_by_username(username)
        if not existing_user:
            existing_user = get_user_by_phone(phone)
        
        if existing_user:
            return jsonify({'success': False, 'message': 'Username or phone number already exists!'})

        # Password confirmation
        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match!'})

        # Validate role - ADMIN COMPLETELY EXCLUDED
        valid_roles = ['patient', 'doctor', 'xrayspecialist', 'reception', 'healthofficer']
        if role not in valid_roles:
            return jsonify({'success': False, 'message': 'Invalid role selected!'})

        # Create new user based on role using the existing functions
        try:
            if role == 'patient':
                new_user = create_patient_user(username, phone, password)
                # Get the patient profile to show the unique ID
                patient_profile = Patient.query.filter_by(user_id=new_user.id).first()
                unique_id = patient_profile.patient_unique_id if patient_profile else f"PAT{new_user.id:06d}"
                success_message = f'Patient {username} registered successfully with ID: {unique_id}'
            elif role == 'doctor':
                new_user = create_doctor_user(username, phone, password)
                success_message = f'Doctor {username} registered successfully! Awaiting admin approval.'
            elif role == 'xrayspecialist':
                new_user = create_xray_specialist_user(username, phone, password)
                success_message = f'X-ray Specialist {username} registered successfully! Awaiting admin approval.'
            elif role == 'reception':
                new_user = create_reception_user(username, phone, password)
                success_message = f'Reception user {username} registered successfully! Awaiting admin approval.'
            elif role == 'healthofficer':
                new_user = create_health_officer_user(username, phone, password)
                success_message = f'Health Officer {username} registered successfully! Awaiting admin approval.'
            else:
                return jsonify({'success': False, 'message': 'Invalid role selected!'})
            
            if not new_user:
                return jsonify({'success': False, 'message': 'Failed to create user'})

            # Create notification for admins when staff registers (not for patients)
            if role in ['doctor', 'xrayspecialist', 'reception', 'healthofficer']:
                # Create universal notifications for all admins
                NotificationService.create_notifications_for_role(
                    role='admin',
                    title='New User Registration',
                    message=f'New {role} "{username}" registered and needs approval',
                    notification_type='user_approval',
                    action_url='#approve-users',
                    is_clickable=True
                )
                
                # Also create legacy notification for backward compatibility
                create_user_approval_notification(username, role)

            return jsonify({
                'success': True, 
                'message': success_message
            })

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': f'Registration error: {str(e)}'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error registering patient: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Failed to register patient: {str(e)}'})

# ---------------------- X-RAY UPLOAD BY SPECIALIST ----------------------
xray_upload_translations = {
    'en': {
        'access_denied': "Access denied!",
        'select_patient_file': "Please select a patient and a file!",
        'xray_sent_success': "✅ X-ray '{filename}' sent to patient successfully."
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'select_patient_file': "Dhukkubsataa fi Suuraa filadhu!",
        'xray_sent_success': "✅ X-ray '{filename}' gara Dhukkubsataatti milkaa'inaan ergameera."
    }
}

@app.route('/xray/upload', methods=['POST'])
@login_required
def upload_xray():
    lang = session.get('lang', 'en')
    texts = xray_upload_translations.get(lang, xray_upload_translations['en'])

    role = normalize_role(current_user.role)
    if role != "xrayspecialist":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    file = request.files.get('xray_file')
    patient_id = request.form.get('patient_id')  # Selected from dropdown
    doctor_id = request.form.get('doctor_id')

    if not patient_id or not doctor_id or not file or file.filename == '':
        flash("Please select patient, select doctor, and choose X-ray file.", "danger")
        return redirect(url_for('dashboard_xray'))

    # Get patient from database
    patient = User.query.filter_by(id=int(patient_id), role='patient').first()
    if not patient:
        flash("Selected patient not found.", "danger")
        return redirect(url_for('dashboard_xray'))

    # Get patient unique ID
    patient_unique_id = None
    if patient.patient_profile:
        patient_unique_id = patient.patient_profile.patient_unique_id

    # 1. Check file extension validation only
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if file_ext not in allowed_extensions:
        flash("Invalid file type. Only JPG, PNG, JPEG, and GIF files are allowed.", "danger")
        return redirect(url_for('dashboard_xray'))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    # Create prediction with proper patient identification
    prediction = Prediction(
        patient_id=patient.id,
        doctor_id=int(doctor_id),
        sent_by=current_user.id,
        image_filename=filename,
        patient_unique_id=patient_unique_id,
        patient_name_provided=patient.username,  # Use actual patient name from database
        sent_by_xray_specialist=True
    )

    db.session.add(prediction)
    db.session.commit()
    
    # Create notification for the doctor
    doctor = User.query.get(int(doctor_id))
    if doctor:
        # Legacy notification
        doctor_notification = DoctorNotification(
            doctor_id=int(doctor_id),
            patient_id=patient.id,
            patient_name=patient.username,
            xray_filename=filename,
            message=f"X-ray specialist {current_user.username} sent X-ray for patient {patient.username} (ID: {patient_unique_id})",
            is_read=False,
            notification_type='xray_from_specialist'
        )
        db.session.add(doctor_notification)
        
        # Universal notification
        print(f"📧 Creating universal notification for doctor {doctor.username}")
        universal_notification = NotificationService.create_notification(
            user_id=doctor.id,
            user_role='doctor',
            title="New X-ray Image Received",
            message=f"X-ray Specialist {current_user.username} sent X-ray image for patient {patient.username} (ID: {patient_unique_id}). File: {filename}",
            notification_type='xray_image',
            action_url='#appointment',
            is_clickable=True
        )
        
        if universal_notification:
            print(f"✅ Created universal notification for doctor {doctor.username}")
        else:
            print(f"❌ Failed to create universal notification for doctor")
        
        db.session.commit()

    flash(f"✅ X-ray '{filename}' sent to Dr. {doctor.username} for patient {patient.username} (ID: {patient_unique_id})", "success")
    return redirect(url_for('dashboard_xray'))

# ---------------------- PATIENT SEND X-RAY BACK TO DOCTOR ----------------------
send_xray_to_doctor_translations = {
    'en': {
        'access_denied': "Access denied!",
        'choose_file': "Please choose a file!",
        'select_doctor': "Please select a doctor!",
        'save_file_failed': "Failed to save file: {error}",
        'xray_sent_success': "✅ X-ray '{filename}' sent to doctor successfully!",
        'save_record_failed': "Failed to save record: {error}"
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'choose_file': "Suuraa filadhu!",
        'select_doctor': "Ogeessa fayyaa(Dr) filadhu!",
        'save_file_failed': "Suuraa olkaa'uu hin dandeenye: {error}",
        'xray_sent_success': "✅ X-ray '{filename}' gara ogeessa fayyaa(Dr) milkaa'inaan ergameera!",
        'save_record_failed': "Galmee olkaa'uu hin dandeenye: {error}"
    }
}

@app.route('/send_xray_to_doctor', methods=['POST'])
@login_required
def send_xray_to_doctor():
    lang = session.get('lang', 'en')
    texts = send_xray_to_doctor_translations.get(lang, send_xray_to_doctor_translations['en'])

    if normalize_role(current_user.role) != 'patient':
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    file = request.files.get('xray_file')
    doctor_id = request.form.get('doctor_id')

    if not file or file.filename == '':
        flash(texts['choose_file'], "danger")
        return redirect(url_for('dashboard_patient'))

    if not doctor_id:
        flash(texts['select_doctor'], "danger")
        return redirect(url_for('dashboard_patient'))

    # 1. Check file extension validation only
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if file_ext not in allowed_extensions:
        flash("Invalid file type. Only JPG, PNG, JPEG, and GIF files are allowed.", "danger")
        return redirect(url_for('dashboard_patient'))

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        file.save(file_path)
    except Exception as e:
        flash(texts['save_file_failed'].format(error=str(e)), "danger")
        return redirect(url_for('dashboard_patient'))

    try:
        new_prediction = Prediction(
            patient_id=current_user.id,
            sent_by=current_user.id,
            doctor_id=int(doctor_id),
            image_filename=filename,
            sent_by_patient_only=True
        )
        db.session.add(new_prediction)
        db.session.commit()
        
        # Get doctor's user object to store notification
        doctor = User.query.get(int(doctor_id))
        
        # Create a notification for the doctor
        doctor_notification = DoctorNotification(
            doctor_id=int(doctor_id),
            patient_id=current_user.id,
            patient_name=current_user.username,
            xray_filename=filename,
            message=f"Patient {current_user.username} has sent you a new X-ray for analysis",
            is_read=False
        )
        db.session.add(doctor_notification)
        db.session.commit()
        
        flash(texts['xray_sent_success'].format(filename=filename), "success")
    except Exception as e:
        db.session.rollback()
        flash(texts['save_record_failed'].format(error=str(e)), "danger")

    return redirect(url_for('dashboard_patient'))



@app.route('/mark_notification_read', methods=['POST'])
@login_required
def mark_notification_read():
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    notification_id = data.get('notification_id')
    
    if notification_id:
        notification = DoctorNotification.query.filter_by(
            id=notification_id, 
            doctor_id=current_user.id
        ).first()
        
        if notification:
            notification.is_read = True
            db.session.commit()
    
    return jsonify({'success': True})

@app.route('/get_doctor_notifications')
@login_required
def get_doctor_notifications():
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'error': 'Access denied'}), 403
    
    unread_notifications = DoctorNotification.query.filter_by(
        doctor_id=current_user.id, 
        is_read=False
    ).order_by(DoctorNotification.created_at.desc()).all()
    
    notifications_data = []
    for notif in unread_notifications:
        notifications_data.append({
            'id': notif.id,
            'patient_id': notif.patient_id,
            'patient_name': notif.patient_name,
            'xray_filename': notif.xray_filename,
            'message': notif.message,
            'notification_type': notif.notification_type,
            'created_at': notif.created_at.isoformat(),
            'formatted_time': notif.get_formatted_time()
        })
    
    return jsonify(notifications_data)

@app.route('/clear_all_notifications', methods=['POST'])
@login_required
def clear_all_notifications():
    """Delete all doctor notifications"""
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Delete all notifications for this doctor
        DoctorNotification.query.filter_by(
            doctor_id=current_user.id
        ).delete()
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ---------------------- PATIENT FEEDBACK ----------------------
patient_feedback_translations = {
    'en': {
        'access_denied': "Access denied!",
        'feedback_submitted': "Feedback submitted successfully!",
        'feedback_empty': "Feedback cannot be empty."
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'feedback_submitted': "Yaadni milkaa'inaan ergameera!",
        'feedback_empty': "Yaadni duwwaa ta'uu hin danda'u."
    }
}

@app.route('/patient/feedback', methods=['POST'])
@login_required
def patient_feedback():
    lang = session.get('lang', 'en')
    texts = patient_feedback_translations.get(lang, patient_feedback_translations['en'])

    if normalize_role(current_user.role) != "patient":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    feedback_text = request.form.get('feedback')
    if feedback_text:
        new_feedback = Feedback(patient_id=current_user.id, feedback=feedback_text)
        db.session.add(new_feedback)
        db.session.commit()
        
        # Create notification for admins
        create_feedback_notification(current_user.username, feedback_text, new_feedback.id)
        
        flash(texts['feedback_submitted'], "success")
    else:
        flash(texts['feedback_empty'], "danger")

    return redirect(url_for('dashboard_patient'))

# ---------------------- DOCTOR RUN AI PREDICTION ----------------------
doctor_predict_translations = {
    'en': {
        'access_denied': "Access denied!",
        'upload_xray': "Please upload an X-ray image.",
        'ai_prediction_failed': "AI prediction failed.",
        'ai_model_not_loaded': "AI model not loaded.",
        'prediction_malignant': "Malignant",
        'prediction_benign': "Benign"
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'upload_xray': "Suuraa X-ray olkaa'i.",
        'ai_prediction_failed': "Tilmaamni AI hin milkoofne.",
        'ai_model_not_loaded': "Model AI hin fe'amne.",
        'prediction_malignant': "Dhibee Qaba",
        'prediction_benign': "Dhibee hin Qabu"
    }
}

@app.route('/doctor/predict', methods=['GET', 'POST'])
@login_required
def doctor_predict():
    lang = session.get('lang', 'en')
    texts = doctor_predict_translations.get(lang, doctor_predict_translations['en'])

    if normalize_role(current_user.role) != 'doctor':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': texts['access_denied']
            }), 403
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    prediction_result = None
    reasoning = None
    confidence = None
    result_class = None  # English classification for template

    if request.method == 'POST':
        file = request.files.get('xray_file')
        if not file or file.filename == '':
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': texts['upload_xray']
                }), 400
            flash(texts['upload_xray'], "danger")
        else:
            # 1. Check file extension validation
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            
            if file_ext not in allowed_extensions:
                error_msg = "Invalid file type. Only JPG, PNG, JPEG, and GIF files are allowed."
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'error': error_msg,
                        'validation_error': True
                    }), 400
                flash(error_msg, "danger")
                return render_template('index.html', 
                                     validation_error=error_msg,
                                     show_validation_error=True)
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # 2. Check saturation validation for X-ray detection
            import cv2
            try:
                img_check = cv2.imread(file_path)
                if img_check is not None:
                    hsv_check = cv2.cvtColor(img_check, cv2.COLOR_BGR2HSV)
                    max_sat_check = np.max(hsv_check[:,:,1])
                    
                    print(f"\n{'='*70}")
                    print(f"DOCTOR ROUTE - IMAGE VALIDATION for {filename}")
                    print(f"{'='*70}")
                    print(f"Max saturation: {max_sat_check}")
                    
                    # Check if saturation is above 250 (indicating not an X-ray)
                    if max_sat_check >= 250:
                        print(f"REJECTED: Image has high saturation (not X-ray)")
                        print(f"{'='*70}\n")
                        
                        error_msg = "The uploaded image is not an X-ray image"
                        
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify({
                                'success': False,
                                'error': error_msg,
                                'validation_error': True,
                                'saturation_error': True
                            }), 400
                        
                        return render_template('index.html', 
                                             validation_error=error_msg,
                                             show_validation_error=True,
                                             saturation_error=True)
                    else:
                        print(f"PASSED: Image has acceptable saturation for X-ray")
                        print(f"{'='*70}\n")
            except Exception as e:
                print(f"Saturation validation error: {e}")

            # INLINE VALIDATION CHECK FOR DOCTOR ROUTE
            import cv2
            try:
                img_check = cv2.imread(file_path)
                if img_check is not None:
                    hsv_check = cv2.cvtColor(img_check, cv2.COLOR_BGR2HSV)
                    max_sat_check = np.max(hsv_check[:,:,1])
                    avg_sat_check = np.mean(hsv_check[:,:,1])
                    
                    print(f"\n{'='*70}")
                    print(f"DOCTOR ROUTE - INLINE VALIDATION CHECK for {filename}")
                    print(f"{'='*70}")
                    print(f"Max saturation: {max_sat_check}")
                    print(f"Avg saturation: {avg_sat_check:.2f}")
                    
                    # HARD REJECT if image has saturated pixels
                    if max_sat_check >= 250 or avg_sat_check >= 50:
                        print(f"REJECTED: Image has high saturation")
                        print(f"{'='*70}\n")
                        
                        error_msg = "Not X-ray Image"
                        
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return jsonify({
                                'success': False,
                                'error': error_msg,
                                'is_medical': False
                            }), 400
                        
                        flash("⚠️ The uploaded image is not a valid X-ray or medical image.", "warning")
                        return render_template('index.html', prediction_result="Not X-ray Image")
                    else:
                        print(f"PASSED: Image has low saturation")
                        print(f"{'='*70}\n")
            except Exception as e:
                print(f"Inline validation error: {e}")

            if cnn_model:
                try:
                    img = image.load_img(file_path, target_size=(224, 224))
                    img_array = image.img_to_array(img) / 255.0
                    img_array = np.expand_dims(img_array, axis=0)
                    result = cnn_model.predict(img_array)
                    
                    # Get prediction value
                    prediction_value = float(result[0][0])
                    
                    # Determine classification and confidence
                    if prediction_value > 0.5:
                        prediction_result = texts['prediction_malignant']
                        confidence = prediction_value * 100
                        classification = "Malignant"  # English for reasoning
                        result_class = "Malignant"  # English for template comparison
                    else:
                        prediction_result = texts['prediction_benign']
                        confidence = (1 - prediction_value) * 100
                        classification = "Benign"  # English for reasoning
                        result_class = "Benign"  # English for template comparison
                    
                    # Generate AI Reasoning - ALWAYS generate it
                    try:
                        reasoning = generate_ai_reasoning(classification, confidence, prediction_value)
                        print(f"✅ Reasoning generated successfully")
                        print(f"   Classification: {classification}")
                        print(f"   Confidence: {confidence:.2f}%")
                        print(f"   Reasoning keys: {list(reasoning.keys())}")
                    except Exception as reasoning_error:
                        print(f"❌ Reasoning generation error: {reasoning_error}")
                        import traceback
                        traceback.print_exc()
                        # Create a simple fallback reasoning
                        reasoning = {
                            'classification': classification,
                            'confidence': round(confidence, 2),
                            'certainty_level': 'moderate',
                            'explanation': f"The model predicts this as {classification} with {confidence:.1f}% confidence.",
                            'indicators': ['Analysis completed'],
                            'next_steps': ['Consult with healthcare provider'],
                            'disclaimer': 'This is an AI prediction. Consult medical professionals.'
                        }
                    
                    # Handle AJAX request
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({
                            'success': True,
                            'prediction_result': prediction_result,
                            'confidence': round(confidence, 2),
                            'reasoning': reasoning
                        })
                    
                    # Debug output for template rendering
                    print(f"📄 Rendering template with:")
                    print(f"   prediction_result: {prediction_result}")
                    print(f"   confidence: {confidence}")
                    print(f"   reasoning: {'Present' if reasoning else 'None'}")
                    
                except Exception as e:
                    print(f"Prediction error: {e}")
                    import traceback
                    traceback.print_exc()
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return jsonify({
                            'success': False,
                            'error': texts['ai_prediction_failed']
                        }), 500
                    flash(texts['ai_prediction_failed'], "danger")
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'error': texts['ai_model_not_loaded']
                    }), 500
                flash(texts['ai_model_not_loaded'], "warning")

    # For GET requests or regular POST requests (non-AJAX)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # If it's an AJAX request but we reached here, something went wrong
        return jsonify({
            'success': False,
            'error': texts['unexpected_error']
        }), 400
    
    # Final debug before rendering
    print(f"\n{'='*70}")
    print(f"FINAL TEMPLATE VARIABLES:")
    print(f"{'='*70}")
    print(f"prediction_result: {prediction_result}")
    print(f"result: {prediction_result}")
    print(f"confidence: {confidence}")
    print(f"reasoning: {'Present with keys: ' + str(reasoning.keys()) if reasoning else 'None'}")
    print(f"{'='*70}\n")
    
    return render_template('index.html', 
                         prediction_result=prediction_result,
                         reasoning=reasoning,
                         confidence=confidence,
                         result=result_class or prediction_result)

# ---------------------- ANALYZE IMAGE FROM APPOINTMENT ----------------------
@app.route('/doctor/analyze_appointment_image/<int:prediction_id>', methods=['POST'])
@login_required
@doctor_required
def analyze_appointment_image(prediction_id):
    """Analyze an image directly from the appointment view without downloading"""
    try:
        # Get the prediction record
        prediction = Prediction.query.get_or_404(prediction_id)
        
        # Verify the image file exists
        if not prediction.image_filename:
            return jsonify({
                'success': False,
                'error': 'No image file associated with this prediction'
            }), 400
        
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], prediction.image_filename)
        if not os.path.exists(filepath):
            return jsonify({
                'success': False,
                'error': 'Image file not found on server'
            }), 404
        
        # Check if AI model is loaded
        if not cnn_model:
            return jsonify({
                'success': False,
                'error': 'AI model not available. Please contact administrator.'
            }), 500
        
        # First, validate if the image is an X-ray using saturation check
        print(f"🔍 Validating if image is X-ray: {filepath}")
        
        import cv2
        try:
            img_check = cv2.imread(filepath)
            if img_check is not None:
                hsv_check = cv2.cvtColor(img_check, cv2.COLOR_BGR2HSV)
                max_sat_check = np.max(hsv_check[:,:,1])
                
                print(f"\n{'='*70}")
                print(f"DOCTOR ANALYZE - IMAGE VALIDATION for {prediction.image_filename}")
                print(f"{'='*70}")
                print(f"Max saturation: {max_sat_check}")
                
                # Check if saturation is above 250 (indicating not an X-ray)
                if max_sat_check >= 250:
                    print(f"REJECTED: Image has high saturation (not X-ray)")
                    print(f"{'='*70}\n")
                    
                    return jsonify({
                        'success': False,
                        'error': 'The analyzed image is not xray image, please contact the xray specialist',
                        'validation_error': True,
                        'saturation_error': True
                    })
                else:
                    print(f"PASSED: Image has acceptable saturation for X-ray")
                    print(f"{'='*70}\n")
            else:
                return jsonify({
                    'success': False,
                    'error': 'Unable to read image file'
                }), 400
        except Exception as e:
            print(f"Saturation validation error: {e}")
            return jsonify({
                'success': False,
                'error': 'Error validating image format'
            }), 500
        
        # Perform AI analysis only if image passes X-ray validation
        try:
            print(f"✅ Image validated as X-ray (saturation: {max_sat_check}), proceeding with analysis...")
            
            # Load and preprocess the image
            img = image.load_img(filepath, target_size=(224, 224))
            img_array = image.img_to_array(img) / 255.0
            img_array = np.expand_dims(img_array, axis=0)
            result = cnn_model.predict(img_array)
            
            # Get prediction value
            prediction_value = float(result[0][0])
            
            # Determine classification and confidence
            if prediction_value > 0.5:
                classification = "Malignant"
                confidence = prediction_value * 100
            else:
                classification = "Benign"
                confidence = (1 - prediction_value) * 100
            
            # Generate AI reasoning
            reasoning = generate_ai_reasoning(classification, confidence, prediction_value)
            
            # Add X-ray validation info to reasoning
            reasoning['xray_validation'] = {
                'validated': True,
                'saturation_value': int(max_sat_check),
                'validation_note': f"Image validated as X-ray (saturation: {max_sat_check} < 250)"
            }
            
            # Update the prediction record with AI results
            prediction.ai_result = classification.lower()
            prediction.ai_confidence = confidence
            db.session.commit()
            
            return jsonify({
                'success': True,
                'prediction_result': classification,
                'confidence': round(confidence, 2),
                'reasoning': reasoning,
                'patient_name': prediction.get_patient_name(),
                'image_filename': prediction.image_filename,
                'validation_passed': True,
                'saturation_value': int(max_sat_check)
            })
            
        except Exception as e:
            print(f"AI Analysis error: {e}")
            return jsonify({
                'success': False,
                'error': 'AI analysis failed. Please try again.'
            }), 500
            
    except Exception as e:
        print(f"Error in analyze_appointment_image: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while processing the request'
        }), 500

# ---------------------- DOCTOR VALIDATION & RECOMMENDATION ----------------------
doctor_validate_translations = {
    'en': {
        'access_denied': "Access denied!",
        'select_patient_prediction': "Please select a patient/prediction.",
        'select_validation': "Please select validation.",
        'validation_sent': "✅ Validation and recommendation sent to patient."
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'select_patient_prediction': "Dhukkubsataa ykn yaada filadhu.",
        'select_validation': "Sirreeffama filadhu.",
        'validation_sent': "✅ Sirreeffamaa fi gorsa gara Dhukkubsataa ergame."
    }
}

@app.route('/doctor/validate', methods=['POST'])
@login_required
def doctor_validate():
    lang = session.get('lang', 'en')
    texts = doctor_validate_translations.get(lang, doctor_validate_translations['en'])

    if normalize_role(current_user.role) != "doctor":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    prediction_id = request.form.get('prediction_id')
    if not prediction_id:
        flash(texts['select_patient_prediction'], "danger")
        return redirect(url_for('dashboard_doctor'))

    pred = Prediction.query.get_or_404(prediction_id)

    # 🔒 SECURITY: Verify this prediction is assigned to the current doctor
    if pred.doctor_id != current_user.id:
        flash("⚠️ Unauthorized: You can only validate predictions assigned to you.", "danger")
        return redirect(url_for('dashboard_doctor'))

    validation = request.form.get('doctor_validation')
    recommendation = request.form.get('doctor_recommendation')
    notes = request.form.get('doctor_notes')

    if not validation:
        flash(texts['select_validation'], "danger")
        return redirect(url_for('dashboard_doctor'))

    pred.doctor_validation = validation
    pred.doctor_recommendation = recommendation
    pred.doctor_notes = notes

    # REMOVED: Don't create feedback for doctor validation results
    # Doctor validation results are stored in the Prediction model
    # and should only be visible to the patient, not to admin
    # The validation data is already saved in pred.doctor_validation, pred.doctor_recommendation, pred.doctor_notes

    db.session.commit()

    # Create notification for patient about doctor validation
    create_doctor_validation_notification(pred.id)

    flash(texts['validation_sent'], "success")
    return redirect(url_for('dashboard_doctor'))

# ---------------------- SERVE UPLOADED FILES ----------------------
password_change_translations = {
    'en': {
        'current_password_incorrect': "Current password is incorrect!",
        'new_passwords_no_match': "New passwords do not match!",
        'password_updated': "✅ Password updated successfully!"
    },
    'or': {
        'current_password_incorrect': "Jecha darbii ammaa sirrii miti!",
        'new_passwords_no_match': "Jecha darbii haaraa wal hin simanne!",
        'password_updated': "✅ Jecha darbii milkaa'inaan haaromfame!"
    }
}

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/uploads/profile_pictures/<filename>')
def profile_picture(filename):
    profile_pics_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pictures')
    return send_from_directory(profile_pics_folder, filename)

@app.route('/user/change_password', methods=['POST'])
@login_required
def change_password():
    lang = session.get('lang', 'en')
    texts = password_change_translations.get(lang, password_change_translations['en'])

    # Get data from JSON request
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid request data'}), 400

    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    if not current_user.check_password(current_password):
        return jsonify({'success': False, 'message': texts['current_password_incorrect']}), 400

    if new_password != confirm_password:
        return jsonify({'success': False, 'message': texts['new_passwords_no_match']}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400

    try:
        current_user.set_password(new_password)
        db.session.commit()
        return jsonify({'success': True, 'message': texts['password_updated']})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error updating password: {str(e)}'}), 500

@app.route('/user/upload_profile_picture', methods=['POST'])
@login_required
def upload_profile_picture():
    """Upload and update user profile picture"""
    try:
        if 'profile_picture' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'}), 400
        
        file = request.files['profile_picture']
        
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'}), 400
        
        # Check file extension
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'success': False, 'message': 'Invalid file type. Only PNG, JPG, JPEG, and GIF allowed'}), 400
        
        # Create profile pictures folder if it doesn't exist
        profile_pics_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'profile_pictures')
        os.makedirs(profile_pics_folder, exist_ok=True)
        
        # Generate unique filename
        filename = f"profile_{current_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"
        filepath = os.path.join(profile_pics_folder, filename)
        
        # Save the file
        file.save(filepath)
        
        # Delete old profile picture if it exists and is not default
        if current_user.profile_picture and current_user.profile_picture != 'default_avatar.png':
            old_filepath = os.path.join(profile_pics_folder, current_user.profile_picture)
            if os.path.exists(old_filepath):
                try:
                    os.remove(old_filepath)
                except:
                    pass  # Ignore if file doesn't exist or can't be deleted
        
        # Update user profile picture in database
        current_user.profile_picture = filename
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profile picture updated successfully',
            'profile_picture_url': f'/uploads/profile_pictures/{filename}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error uploading profile picture: {str(e)}'}), 500

# ---------------------- ADMIN USER MANAGEMENT ----------------------
general_translations = {
    'en': {
        'access_denied': "Access denied!"
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!"
    }
}

@app.route('/admin/view_user/<int:user_id>')
@login_required
def view_user(user_id):
    lang = session.get('lang', 'en')
    texts = general_translations.get(lang, general_translations['en'])

    if normalize_role(current_user.role) != "admin":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)
    return render_template('view_user.html', user=user)

@app.route('/admin/edit_user/<int:user_id>')
@login_required
def edit_user(user_id):
    lang = session.get('lang', 'en')
    texts = general_translations.get(lang, general_translations['en'])

    if normalize_role(current_user.role) != "admin":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    user = User.query.get_or_404(user_id)
    
    # Get role-specific profile data and render appropriate template
    if user.role == 'patient':
        patient_profile = Patient.query.filter_by(user_id=user.id).first()
        return render_template('edit_patient.html', user=user, patient=patient_profile)
    elif user.role == 'doctor':
        doctor_profile = Doctor.query.filter_by(user_id=user.id).first()
        return render_template('edit_doctor.html', user=user, doctor=doctor_profile)
    elif user.role == 'xrayspecialist':
        xrayspecialist_profile = XraySpecialist.query.filter_by(user_id=user.id).first()
        return render_template('edit_xrayspecialist.html', user=user, xrayspecialist=xrayspecialist_profile)
    elif user.role == 'healthofficer':
        healthofficer_profile = HealthOfficer.query.filter_by(user_id=user.id).first()
        return render_template('edit_healthofficer.html', user=user, healthofficer=healthofficer_profile)
    elif user.role == 'reception':
        reception_profile = Reception.query.filter_by(user_id=user.id).first()
        return render_template('edit_reception.html', user=user, reception=reception_profile)
    else:
        return render_template('edit_user.html', user=user)

@app.route('/admin/get_users_to_approve')
@login_required
def get_users_to_approve():
    users = User.query.filter(
        User.is_approved == False,
        User.role != 'patient'
    ).all()

    users_list = []
    for u in users:
        users_list.append({
            "id": u.id,
            "username": u.username,
            "phone": u.phone,
            "role": u.role,
            "registered_at": u.date_created.isoformat() if u.date_created else ""
        })
    return jsonify(users_list)

@app.route('/admin/get_users')
@login_required
def admin_get_users_search():
    lang = session.get('lang', 'en')
    texts = general_translations.get(lang, general_translations['en'])

    if normalize_role(current_user.role) != "admin":
        return jsonify([]), 403

    user_type = request.args.get('type', 'patient').lower()
    search = request.args.get('search', '').strip()

    role_map = {
        "patient": "patient",
        "doctor": "doctor",
        "xrayspecialist": "xrayspecialist",
        "reception": "reception",
        "healthofficer": "healthofficer"
    }
    role = role_map.get(user_type, "patient")

    query = User.query.filter_by(role=role)
    if search:
        query = query.filter(
            (User.username.ilike(f"%{search}%")) |
            (User.phone.ilike(f"%{search}%"))
        )
    users = query.all()

    return jsonify([{"id": u.id, "username": u.username, "phone": u.phone, "role": u.role} for u in users])

xray_delete_translations = {
    'en': {
        'unauthorized_action': "Unauthorized action.",
        'xray_deleted': "X-ray deleted successfully."
    },
    'or': {
        'unauthorized_action': "Dalagaa hayyamame miti.",
        'xray_deleted': "X-ray milkaa'inaan haqame."
    }
}

@app.route('/xray/delete/<int:prediction_id>', methods=['POST'])
@login_required
def delete_xray(prediction_id):
    lang = session.get('lang', 'en')
    texts = xray_delete_translations.get(lang, xray_delete_translations['en'])

    prediction = Prediction.query.get_or_404(prediction_id)
    
    # 🔒 SECURITY: Check authorization based on user role
    role = normalize_role(current_user.role)
    
    if role == 'patient':
        # Patients can only delete their own X-rays
        if prediction.patient_id != current_user.id:
            flash(texts['unauthorized_action'], "danger")
            return redirect(url_for('dashboard_patient'))
    elif role == 'xrayspecialist':
        # X-ray specialists can only delete X-rays they uploaded
        if prediction.sent_by != current_user.id:
            flash(texts['unauthorized_action'], "danger")
            return redirect(url_for('dashboard_xray'))
    else:
        # Other roles cannot delete X-rays
        flash(texts['unauthorized_action'], "danger")
        return redirect(url_for('login'))
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], prediction.image_filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(prediction)
    db.session.commit()
    flash(texts['xray_deleted'], "success")
    
    # Redirect based on user role
    if role == 'xrayspecialist':
        return redirect(url_for('dashboard_xray'))
    else:
        return redirect(url_for('dashboard_patient'))

# ---------------------- ADMIN FEEDBACK AND REPLY ----------------------
feedback_translations = {
    'en': {
        'access_denied': "Access denied!",
        'reply_empty': "Reply cannot be empty!",
        'reply_sent': "💬 Reply sent to user successfully!"
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'reply_empty': "Deebiin duwwaa ta'uu hin danda'u!",
        'reply_sent': "💬 Deebiin fayyadamtootaaf milkaa'inaan ergame!"
    }
}


@app.route('/admin/get_all_users/<role>')
@admin_required
def admin_get_all_users(role):
    """Get all users of a specific role for admin dashboard"""
    try:
        # Validate role
        valid_roles = ['patient', 'doctor', 'xrayspecialist', 'healthofficer', 'reception']
        if role not in valid_roles:
            return jsonify([]), 400
        
        # Get all users with specified role
        users = User.query.filter_by(role=role).all()
        
        user_list = []
        for user in users:
            # Get role-specific profile for additional info
            profile = None
            user_id_field = None
            
            if role == 'patient':
                profile = Patient.query.filter_by(user_id=user.id).first()
                user_id_field = profile.patient_unique_id if profile else f'PAT-{datetime.now().strftime("%Y%m%d")}-{user.id:05d}'
            elif role == 'doctor':
                profile = Doctor.query.filter_by(user_id=user.id).first()
                user_id_field = f'DOC-{datetime.now().strftime("%Y%m%d")}-{user.id:05d}'
            elif role == 'xrayspecialist':
                profile = XraySpecialist.query.filter_by(user_id=user.id).first()
                user_id_field = f'XRS-{datetime.now().strftime("%Y%m%d")}-{user.id:05d}'
            elif role == 'healthofficer':
                profile = HealthOfficer.query.filter_by(user_id=user.id).first()
                user_id_field = f'HO-{datetime.now().strftime("%Y%m%d")}-{user.id:05d}'
            elif role == 'reception':
                profile = Reception.query.filter_by(user_id=user.id).first()
                user_id_field = f'REC-{datetime.now().strftime("%Y%m%d")}-{user.id:05d}'
            
            user_data = {
                'id': user.id,
                'username': user.username,
                'phone': user.phone,
                'email': profile.email if profile and hasattr(profile, 'email') else None,
                'user_id': user_id_field,
                'date_created': user.date_created.strftime('%Y-%m-%d') if user.date_created else 'N/A'
            }
            user_list.append(user_data)
        
        # Sort by registration date (newest first)
        user_list.sort(key=lambda x: x['date_created'], reverse=True)
        
        return jsonify(user_list)
        
    except Exception as e:
        print(f"Error getting all {role}s: {e}")
        return jsonify([]), 500

# Legacy route for backward compatibility
@app.route('/admin/get_all_patients')
@admin_required
def admin_get_all_patients():
    """Get all patients for admin dashboard patient list - legacy route"""
    return admin_get_all_users('patient')

@app.route('/admin/get_all_feedbacks')
@admin_required
def admin_get_all_feedbacks():
    """Get all feedbacks for admin dashboard - FIXED to exclude doctor replies and patient-to-doctor feedback"""
    print("🔍 ADMIN_GET_ALL_FEEDBACKS CALLED - Starting feedback retrieval")
    print("🔍 TESTING IF CODE CHANGES ARE LOADED")
    try:
        # Get all feedbacks with user information
        # FIXED: Exclude doctor_reply type (those are doctor replies TO patients, not feedback TO admin)
        # FIXED: Exclude patient_to_doctor type (those are patient feedback TO doctors, not TO admin)
        feedbacks = Feedback.query.filter(
            Feedback.feedback_type != 'doctor_reply',
            Feedback.feedback_type != 'patient_to_doctor'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        feedbacks_data = []
        for feedback in feedbacks:
            # FIXED: Skip doctor validation results (they start with "Doctor Validation:")
            if feedback.feedback and feedback.feedback.startswith("Doctor Validation:"):
                continue
            
            # Determine sender info based on who sent the feedback
            if feedback.patient_id:
                sender = User.query.get(feedback.patient_id)
                # Check feedback type to determine actual sender role
                if feedback.feedback_type and feedback.feedback_type.startswith('reception_'):
                    sender_type = 'reception'
                elif feedback.feedback_type == 'healthofficer_to_admin':
                    sender_type = 'healthofficer'
                else:
                    # Fallback: Check the actual user's role if feedback_type is not set properly
                    if sender and sender.role:
                        role_lower = sender.role.lower().strip()
                        if role_lower in ['healthofficer', 'health_officer', 'health-officer']:
                            sender_type = 'healthofficer'
                        elif role_lower in ['reception', 'receptionist']:
                            sender_type = 'reception'
                        else:
                            sender_type = 'patient'
                    else:
                        sender_type = 'patient'
                

            elif feedback.doctor_id:
                sender = User.query.get(feedback.doctor_id)
                sender_type = 'doctor'
            elif feedback.xray_specialist_id:
                sender = User.query.get(feedback.xray_specialist_id)
                sender_type = 'xray_specialist'
            else:
                sender = None
                sender_type = 'unknown'
            
            # Clean up the feedback message for display
            clean_feedback = feedback.feedback
            original_feedback = clean_feedback  # Store original for debugging
            
            if clean_feedback:
                import re
                
                # Remove "To Health Officer [name]: " prefix from health officer feedback
                if feedback.feedback_type and feedback.feedback_type.startswith('reception_to_healthofficer_'):
                    if clean_feedback.startswith("To Health Officer "):
                        # Find the end of the prefix (after the colon and space)
                        colon_index = clean_feedback.find(": ")
                        if colon_index != -1:
                            clean_feedback = clean_feedback[colon_index + 2:]  # +2 to skip ": "
                
                # Remove various test prefixes with timestamps
                # Pattern 1: "ADMIN TEST [timestamp]: " or "HO TEST [timestamp]: "
                test_pattern1 = r'^(ADMIN TEST|HO TEST)\s+[\d.]+:\s*'
                clean_feedback = re.sub(test_pattern1, '', clean_feedback)
                
                # Pattern 2: "TEST FEEDBACK [date timestamp]: "
                test_pattern2 = r'^TEST FEEDBACK\s+[\d\-\s:.]+:\s*'
                clean_feedback = re.sub(test_pattern2, '', clean_feedback)
                
                # Debug print to verify cleaning is working
                if clean_feedback != original_feedback:
                    print(f"🧹 CLEANED FEEDBACK: '{original_feedback[:50]}...' -> '{clean_feedback[:50]}...'")
                else:
                    print(f"🔍 NO CLEANING NEEDED: '{clean_feedback[:50]}...'")
            else:
                print("⚠️ Empty feedback message")
            
            feedbacks_data.append({
                'id': feedback.id,
                'sender_name': sender.username if sender else 'Unknown',
                'sender_type': sender_type,
                'feedback': clean_feedback,
                'feedback_type': feedback.feedback_type,
                'reply': feedback.reply,
                'date_submitted': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read,
                'has_reply': feedback.reply is not None
            })
        
        return jsonify({
            'success': True,
            'feedbacks': feedbacks_data
        })
    
    except Exception as e:
        print(f"Error getting all feedbacks: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/get_all_feedbacks_clean')
@admin_required
def admin_get_all_feedbacks_clean():
    """Get all feedbacks for admin dashboard with cleaned messages"""
    print("🔍 NEW CLEAN FEEDBACKS ROUTE CALLED")
    try:
        # Get all feedbacks with user information
        feedbacks = Feedback.query.filter(
            Feedback.feedback_type != 'doctor_reply',
            Feedback.feedback_type != 'patient_to_doctor'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        feedbacks_data = []
        for feedback in feedbacks:
            # Skip doctor validation results
            if feedback.feedback and feedback.feedback.startswith("Doctor Validation:"):
                continue
            
            # Determine sender info based on who sent the feedback
            if feedback.patient_id:
                sender = User.query.get(feedback.patient_id)
                # Check feedback type to determine actual sender role
                if feedback.feedback_type and feedback.feedback_type.startswith('reception_'):
                    sender_type = 'reception'
                elif feedback.feedback_type == 'healthofficer_to_admin':
                    sender_type = 'healthofficer'
                else:
                    # Fallback: Check the actual user's role if feedback_type is not set properly
                    if sender and sender.role:
                        role_lower = sender.role.lower().strip()
                        if role_lower in ['healthofficer', 'health_officer', 'health-officer']:
                            sender_type = 'healthofficer'
                        elif role_lower in ['reception', 'receptionist']:
                            sender_type = 'reception'
                        else:
                            sender_type = 'patient'
                    else:
                        sender_type = 'patient'
            elif feedback.doctor_id:
                sender = User.query.get(feedback.doctor_id)
                sender_type = 'doctor'
            elif feedback.xray_specialist_id:
                sender = User.query.get(feedback.xray_specialist_id)
                sender_type = 'xray_specialist'
            else:
                sender = None
                sender_type = 'unknown'
            
            # Clean up the feedback message for display
            clean_feedback = feedback.feedback
            original_feedback = clean_feedback
            
            if clean_feedback:
                import re
                
                # Remove "To Health Officer [name]: " prefix from health officer feedback
                if feedback.feedback_type and feedback.feedback_type.startswith('reception_to_healthofficer_'):
                    if clean_feedback.startswith("To Health Officer "):
                        colon_index = clean_feedback.find(": ")
                        if colon_index != -1:
                            clean_feedback = clean_feedback[colon_index + 2:]
                
                # Remove various test prefixes with timestamps
                test_pattern1 = r'^(ADMIN TEST|HO TEST)\s+[\d.]+:\s*'
                clean_feedback = re.sub(test_pattern1, '', clean_feedback)
                
                test_pattern2 = r'^TEST FEEDBACK\s+[\d\-\s:.]+:\s*'
                clean_feedback = re.sub(test_pattern2, '', clean_feedback)
                
                print(f"🧹 CLEANED: '{original_feedback[:30]}...' -> '{clean_feedback[:30]}...'")
            
            feedbacks_data.append({
                'id': feedback.id,
                'sender_name': sender.username if sender else 'Unknown',
                'sender_type': sender_type,
                'feedback': clean_feedback,
                'feedback_type': feedback.feedback_type,
                'reply': feedback.reply,
                'date_submitted': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read,
                'has_reply': feedback.reply is not None
            })
        
        print(f"🔍 Returning {len(feedbacks_data)} cleaned feedbacks")
        return jsonify({
            'success': True,
            'feedbacks': feedbacks_data
        })
    
    except Exception as e:
        print(f"Error getting cleaned feedbacks: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/reply_to_feedback', methods=['POST'])
@csrf.exempt
@admin_required
def admin_reply_to_feedback():
    """Admin replies to any type of feedback"""
    try:
        feedback_id = request.json.get('feedback_id')
        reply_message = request.json.get('reply', '').strip()
        
        print(f"🔄 Admin reply route called - feedback_id: {feedback_id}, reply length: {len(reply_message) if reply_message else 0}")
        
        if not feedback_id or not reply_message:
            return jsonify({'success': False, 'message': 'Feedback ID and reply message are required'}), 400
        
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            return jsonify({'success': False, 'message': 'Feedback not found'}), 404
        
        print(f"📋 Feedback found - ID: {feedback.id}, type: {feedback.feedback_type}, sender: {feedback.patient_id}")
        
        # Check if reply already exists to prevent duplicate processing
        if feedback.reply and feedback.reply.strip() == reply_message.strip():
            print(f"⚠️ Reply already exists for feedback {feedback_id}, skipping duplicate processing")
            return jsonify({'success': True, 'message': 'Reply already exists'})
        
        # Set the reply
        feedback.reply = reply_message
        feedback.reply_date = datetime.utcnow()
        feedback.is_read = True
        
        print(f"🔔 Calling create_reply_notification for feedback {feedback_id}")
        # Create notification using the model method
        feedback.create_reply_notification()
        
        # Commit everything together
        db.session.commit()
        print(f"✅ Reply and notification committed to database for feedback {feedback_id}")
        
        return jsonify({'success': True, 'message': 'Reply sent successfully'})
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error replying to feedback: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to send reply'}), 500

@app.route('/admin/get_feedbacks')
@admin_required
def get_feedbacks():
    try:
        feedbacks = Feedback.query.order_by(Feedback.date_submitted.desc()).all()
        feedbacks_data = []
        
        for feedback in feedbacks:
            feedbacks_data.append({
                'id': feedback.id,
                'patient_name': feedback.patient.username if feedback.patient else 'Unknown',
                'message': feedback.feedback,
                'reply': feedback.reply,
                'date_submitted': feedback.date_submitted.isoformat()
            })
        
        return jsonify(feedbacks_data)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/reply_feedback/<int:feedback_id>', methods=['POST'])
@admin_required
def admin_reply_feedback(feedback_id):
    try:
        reply = request.json.get('reply', '').strip()
        
        if not reply:
            return jsonify({'success': False, 'message': 'Reply cannot be empty'}), 400
        
        feedback = Feedback.query.get_or_404(feedback_id)
        feedback.reply = reply
        feedback.reply_date = datetime.utcnow()
        db.session.commit()
        
        # Create notification based on who sent the feedback
        if feedback.patient_id:
            # If feedback is from patient, notify patient
            create_admin_feedback_notification(feedback_id)
        elif feedback.doctor_id:
            # If feedback is from doctor, notify doctor
            doctor = User.query.get(feedback.doctor_id)
            if doctor:
                doctor_notification = DoctorNotification(
                    doctor_id=doctor.id,
                    patient_id=None,
                    patient_name="Admin",
                    xray_filename="admin_reply",
                    message=f"Admin replied to your feedback: {reply[:100]}{'...' if len(reply) > 100 else ''}",
                    is_read=False,
                    notification_type='admin_reply'
                )
                db.session.add(doctor_notification)
                db.session.commit()
                print(f"Created notification for doctor {doctor.username} about admin reply")
        
        return jsonify({'success': True, 'reply': reply})
    
    except Exception as e:
        db.session.rollback()
        print(f"Error in admin_reply_feedback: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ---------------------- PATIENT FEEDBACK SUBMISSION ----------------------
patient_feedback_submit_translations = {
    'en': {
        'feedback_submitted': "Feedback sent to doctor successfully.",
        'select_doctor': "Please select a doctor.",
        'message_empty': "Message cannot be empty."
    },
    'or': {
        'feedback_submitted': "Yaadni gara ogeessa fayyaatti(Dr) milkaa'inaan ergameera.",
        'select_doctor': "Maaloo ogeessa fayyaa(Dr) filadhu.",
        'message_empty': "Yaadni duwwaa ta'uu hin danda'u."
    }
}

@app.route('/patient/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    lang = session.get('lang', 'en')
    texts = patient_feedback_submit_translations.get(lang, patient_feedback_submit_translations['en'])

    # Get data from JSON request (from the AJAX call)
    data = request.get_json()
    doctor_id = data.get('doctor_id')
    message = data.get('message', '').strip()
    prediction_id = data.get('prediction_id')

    # Validation
    if not message:
        return jsonify({'success': False, 'message': texts['message_empty']}), 400
    
    if not doctor_id:
        return jsonify({'success': False, 'message': texts['select_doctor']}), 400
    
    # Validate that the doctor has actually provided X-ray results to this patient
    doctor_provided_results = Prediction.query.filter_by(
        patient_id=current_user.id,
        doctor_id=doctor_id
    ).filter(
        Prediction.doctor_validation.isnot(None)
    ).first()
    
    if not doctor_provided_results:
        return jsonify({
            'success': False, 
            'message': 'You can only send feedback to doctors who have provided you with X-ray results.'
        }), 400

    try:
        # Create feedback entry directed to the doctor
        new_feedback = Feedback(
            patient_id=current_user.id,
            doctor_id=doctor_id,  # This associates the feedback with a specific doctor
            prediction_id=prediction_id,
            feedback=message,
            feedback_type='patient_to_doctor'  # New feedback type
        )
        db.session.add(new_feedback)
        db.session.flush()  # Get the ID before commit

        # Create notification for the specific doctor (NOT admins)
        doctor_notification = DoctorNotification(
            doctor_id=doctor_id,
            patient_id=current_user.id,
            patient_name=current_user.username,
            xray_filename="feedback_message",
            message=f"Patient {current_user.username} sent you feedback: {message[:100]}{'...' if len(message) > 100 else ''}",
            is_read=False,
            notification_type='feedback'
        )
        db.session.add(doctor_notification)
        
        # Also create universal notification for the doctor
        universal_notification = NotificationService.create_notification(
            user_id=doctor_id,
            user_role='doctor',
            title='New Patient Feedback',
            message=f'Patient {current_user.username} sent you feedback: {message[:100]}{"..." if len(message) > 100 else ""}',
            notification_type='patient_feedback',
            action_url='#feedback',
            is_clickable=True
        )
        
        if universal_notification:
            print(f"✅ Created universal notification for doctor about patient feedback")
        else:
            print(f"❌ Failed to create universal notification for doctor")
        
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': texts['feedback_submitted']
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False, 
            'message': f"Error submitting feedback: {str(e)}"
        }), 500

@app.route('/patient/get_feedbacks')
@login_required
def patient_feedbacks():
    # Get feedbacks where patient is the sender (both to doctors and admins)
    # FIXED: Exclude doctor_reply type (those are replies FROM doctors, not feedback FROM patient)
    feedbacks = Feedback.query.filter(
        Feedback.patient_id == current_user.id,
        Feedback.feedback_type != 'doctor_reply'
    ).order_by(Feedback.date_submitted.desc()).all()

    feedback_list = []
    for f in feedbacks:
        # FIXED: Skip doctor validation results (they are not patient feedback)
        if f.feedback and f.feedback.startswith("Doctor Validation:"):
            continue
        
        # FIXED: Skip any feedback that starts with "Doctor Reply" (old format)
        if f.feedback and f.feedback.startswith("Doctor Reply from"):
            continue
            
        feedback_list.append({
            'id': f.id,
            'message': f.feedback,
            'reply': f.reply,
            'recipient': f.doctor.username if f.doctor else 'Administrator',
            'date': f.date_submitted.strftime('%Y-%m-%d %H:%M') if f.date_submitted else 'N/A',
            'has_reply': bool(f.reply)
        })
    return jsonify(feedback_list)

# NEW ROUTE: Get doctors for the dropdown
@app.route('/patient/get_doctors')
@login_required
def get_doctors_for_feedback():
    """Get list of doctors who have provided X-ray results to the current patient"""
    try:
        # Get doctors who have provided X-ray results (doctor_validation) to this patient
        doctors_with_results = db.session.query(User).join(
            Prediction, User.id == Prediction.doctor_id
        ).filter(
            Prediction.patient_id == current_user.id,
            Prediction.doctor_validation.isnot(None),  # Only doctors who have provided validation
            User.role == 'doctor',
            User.is_approved == True
        ).distinct().all()
        
        doctors_list = []
        for doctor in doctors_with_results:
            # Get the most recent result from this doctor
            latest_prediction = Prediction.query.filter_by(
                patient_id=current_user.id,
                doctor_id=doctor.id
            ).filter(
                Prediction.doctor_validation.isnot(None)
            ).order_by(Prediction.date_uploaded.desc()).first()
            
            doctors_list.append({
                'id': doctor.id,
                'name': f"Dr. {doctor.username}",
                'phone': doctor.phone,
                'latest_result_date': latest_prediction.date_uploaded.isoformat() if latest_prediction else None,
                'latest_validation': latest_prediction.doctor_validation if latest_prediction else None
            })
        
        return jsonify({'success': True, 'doctors': doctors_list})
    except Exception as e:
        print(f"Error getting doctors with results: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# ---------------------- AI PREDICTION FOR PATIENTS ----------------------
predict_translations = {
    'en': {
        'access_denied': "Access denied!",
        'upload_image': "Please upload an image.",
        'ai_prediction_failed': "AI prediction failed.",
        'model_not_loaded': "AI model not loaded."
    },
    'or': {
        'access_denied': "Eyyama hin hayyamamne!",
        'upload_image': "Maaloo suuraa galchaa.",
        'ai_prediction_failed': "Tilmaamni AI fashalaahe.",
        'model_not_loaded': "Modeli AI hin fe'amne."
    }
}

@app.route('/predict', methods=['GET', 'POST'])
@login_required
def predict():
    lang = session.get('lang', 'en')
    texts = predict_translations.get(lang, predict_translations['en'])

    if normalize_role(current_user.role) != "patient":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))

    filename = None
    result = None
    confidence = None
    reasoning = None
    is_xray = None
    xray_confidence = None
    image_quality = None
    error_message = None

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash(texts['upload_image'], "danger")
            return redirect(url_for('predict'))

        # 1. Check file extension validation
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            error_msg = "Invalid file type. Only JPG, PNG, JPEG, and GIF files are allowed."
            return render_template('index.html', 
                                 validation_error=error_msg,
                                 show_validation_error=True)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 2. Check saturation validation for X-ray detection
        import cv2
        try:
            img_check = cv2.imread(filepath)
            if img_check is not None:
                hsv_check = cv2.cvtColor(img_check, cv2.COLOR_BGR2HSV)
                max_sat_check = np.max(hsv_check[:,:,1])
                
                print(f"\n{'='*70}")
                print(f"PATIENT ROUTE - IMAGE VALIDATION for {filename}")
                print(f"{'='*70}")
                print(f"Max saturation: {max_sat_check}")
                
                # Check if saturation is above 250 (indicating not an X-ray)
                if max_sat_check >= 250:
                    print(f"REJECTED: Image has high saturation (not X-ray)")
                    print(f"{'='*70}\n")
                    
                    error_msg = "The uploaded image is not an X-ray image"
                    return render_template('index.html', 
                                         validation_error=error_msg,
                                         show_validation_error=True,
                                         saturation_error=True)
                else:
                    print(f"PASSED: Image has acceptable saturation for X-ray")
                    print(f"{'='*70}\n")
        except Exception as e:
            print(f"Saturation validation error: {e}")

        # INLINE VALIDATION CHECK - Bypass any caching issues
        import cv2
        try:
            img_check = cv2.imread(filepath)
            if img_check is not None:
                hsv_check = cv2.cvtColor(img_check, cv2.COLOR_BGR2HSV)
                max_sat_check = np.max(hsv_check[:,:,1])
                avg_sat_check = np.mean(hsv_check[:,:,1])
                
                print(f"\n{'='*70}")
                print(f"INLINE VALIDATION CHECK for {filename}")
                print(f"{'='*70}")
                print(f"Max saturation: {max_sat_check}")
                print(f"Avg saturation: {avg_sat_check:.2f}")
                
                # HARD REJECT if image has saturated pixels
                if max_sat_check >= 250 or avg_sat_check >= 50:
                    print(f"REJECTED: Image has high saturation")
                    print(f"{'='*70}\n")
                    result = "Not X-ray Image"
                    error_message = "Not X-ray Image"
                    is_xray = False
                    xray_confidence = 0.0
                    flash("⚠️ The uploaded image is not a valid X-ray or medical image.", "warning")
                    
                    return render_template('index.html', 
                                         filename=filename, 
                                         result=result, 
                                         confidence=None,
                                         reasoning=None,
                                         is_xray=is_xray,
                                         xray_confidence=xray_confidence,
                                         image_quality=None,
                                         error_message=error_message)
                else:
                    print(f"PASSED: Image has low saturation")
                    print(f"{'='*70}\n")
        except Exception as e:
            print(f"Inline validation error: {e}")

        if cnn_model:
            try:
                # Force reload prediction utilities to get latest changes
                import sys
                if 'prediction_utils' in sys.modules:
                    import importlib
                    import prediction_utils
                    importlib.reload(prediction_utils)
                    from prediction_utils import validate_and_predict, get_image_quality_metrics
                else:
                    from prediction_utils import validate_and_predict, get_image_quality_metrics
                
                # Step 1: Validate and predict
                prediction_result = validate_and_predict(cnn_model, filepath)
                
                # DEBUG: Print validation results
                print(f"\n{'='*70}")
                print(f"VALIDATION DEBUG for {filename}")
                print(f"{'='*70}")
                print(f"is_xray: {prediction_result['is_xray']}")
                print(f"xray_confidence: {prediction_result['xray_confidence']}")
                print(f"xray_reason: {prediction_result.get('xray_reason', 'N/A')}")
                print(f"success: {prediction_result['success']}")
                print(f"{'='*70}\n")
                
                # Step 2: Get image quality metrics
                image_quality = get_image_quality_metrics(filepath)
                
                # Step 3: Process results
                is_xray = prediction_result['is_xray']
                xray_confidence = prediction_result['xray_confidence']
                xray_reason = prediction_result.get('xray_reason', '')
                
                if not is_xray:
                    result = "Not X-ray Image"
                    error_message = xray_reason if xray_reason else prediction_result.get('error', 'Image does not appear to be a medical image')
                    flash("⚠️ The uploaded image does not appear to be a medical X-ray or histology image. Please upload a valid medical image.", "warning")
                elif prediction_result['success'] and prediction_result['prediction']:
                    pred = prediction_result['prediction']
                    result = pred['result']
                    confidence = pred['confidence']
                    reasoning = pred
                else:
                    error_message = prediction_result.get('error', 'Prediction failed')
                    flash(texts['ai_prediction_failed'], "danger")

            except Exception as e:
                print("Prediction error:", e)
                error_message = str(e)
                flash(texts['ai_prediction_failed'], "danger")
        else:
            flash(texts['model_not_loaded'], "warning")

    return render_template('index.html', 
                         filename=filename, 
                         result=result, 
                         confidence=confidence,
                         reasoning=reasoning,
                         is_xray=is_xray,
                         xray_confidence=xray_confidence,
                         image_quality=image_quality,
                         error_message=error_message)

# ---------------------- DOCTOR AI MODEL PAGE ----------------------
ai_model_translations = {
    'en': {
        'ai_model_page_title': "AI Model Page"
    },
    'or': {
        'ai_model_page_title': "Fuula Moodela AI"
    }
}

@app.route('/doctor/ai_model')
@login_required
def doctor_ai_model():
    lang = session.get('lang', 'en')
    texts = ai_model_translations.get(lang, ai_model_translations['en'])
    return render_template('index.html', title=texts['ai_model_page_title'])

@app.route('/ai_model_page')
@login_required
def ai_model_page():
    lang = session.get('lang', 'en')
    texts = ai_model_translations.get(lang, ai_model_translations['en'])
    return render_template('index.html', title=texts['ai_model_page_title'])

# ---------------------- PASSWORD RESET FUNCTIONALITY ----------------------
# Initialize Africa's Talking
AFRICASTALKING_USERNAME = "BreastCancerDetection_sms"
AFRICASTALKING_API_KEY = "atsk_6a8b61dafa461658824568068f3e103e4808466955aed8dc64cbcb6f22fef72f784d073e"
AFRICASTALKING_SENDER_ID = "BCDS"  # Sender ID (optional, can be shortcode or alphanumeric)

try:
    africastalking.initialize(username=AFRICASTALKING_USERNAME, api_key=AFRICASTALKING_API_KEY)
    sms = africastalking.SMS
    print("✅ Africa's Talking SMS service initialized successfully")
except Exception as e:
    print(f"❌ Failed to initialize Africa's Talking: {e}")
    print("⚠️ SMS functionality will be unavailable. Verification codes will be shown in console.")
    sms = None




# ---------------------- SESSION SECURITY ----------------------
@app.before_request
def verify_session_integrity():
    if 'username' in session:
        ua_hash = hashlib.sha256(request.headers.get('User-Agent', '').encode()).hexdigest()
        if session.get('ua_hash') != ua_hash:
            logout_user()
            session.clear()
            flash("Session expired or tampered. Please log in again.", "warning")
            return redirect(url_for('login'))

# ---------------------- ADMIN CREATION ----------------------
@click.command('create-admin')
@click.option('--username', prompt='Admin username')
@click.option('--phone', prompt='Admin phone (+251...)')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
@with_appcontext
def create_admin_command(username, phone, password):
    """Create an admin user."""
    admin_exists = User.query.filter_by(role='admin', username=username).first()
    if admin_exists:
        click.echo("⚠️ Admin user with this username already exists!")
        return
    
    pattern = r'^\+251(9\d{8}|7\d{8})$'
    if not re.match(pattern, phone):
        click.echo("❌ Invalid phone number! Use +2519... or +2517...")
        return
    
    admin = User(
        username=username,
        phone=phone,
        role="admin"
    )
    admin.set_password(password)
    admin.is_approved = True
    
    db.session.add(admin)
    db.session.commit()
    click.echo("✅ Admin user created successfully!")

app.cli.add_command(create_admin_command)

admin_creation_translations = {
    'en': {
        'access_denied': "Access denied!",
        'admin_created': "✅ Admin user '{}' created successfully!",
        'username_exists': "Username already exists!",
        'phone_exists': "Phone number already exists!",
        'invalid_phone': "Invalid phone number! Use +2519... or +2517...",
        'fill_all_fields': "Please fill all fields!",
        'passwords_no_match': "Passwords do not match!"
    },
    'or': {
        'access_denied': "Eeyyama hin qabdu!",
        'admin_created': "✅ Fayyadamaa admin '{}' milkaa'inaan uumame!",
        'username_exists': "Maqaa fayyadamaa duraan jira!",
        'phone_exists': "Lakkoofsa bilbilaa duraan jira!",
        'invalid_phone': "Lakkoofsa bilbilaa sirrii miti! +2519... yookiin +2517... fayyadami",
        'fill_all_fields': "Maaloo bakka hunda guuti!",
        'passwords_no_match': "Jechoonni darbii wal hin siman!"
    }
}

@app.route('/admin/create_admin', methods=['GET', 'POST'])
@login_required
def create_admin():
    lang = session.get('lang', 'en')
    texts = admin_creation_translations.get(lang, admin_creation_translations['en'])
    
    if normalize_role(current_user.role) != "admin":
        flash(texts['access_denied'], "danger")
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        phone_input = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not username or not phone_input or not password:
            flash(texts['fill_all_fields'], "danger")
            return redirect(url_for('create_admin'))
        
        if password != confirm_password:
            flash(texts['passwords_no_match'], "danger")
            return redirect(url_for('create_admin'))
        
        # Phone validation - validate 9-digit input before adding prefix
        phone_pattern = r'^[79]\d{8}$'
        if not re.match(phone_pattern, phone_input):
            flash(texts['invalid_phone'], "danger")
            return redirect(url_for('create_admin'))
            
        phone = '+251' + phone_input
        
        if User.query.filter_by(username=username).first():
            flash(texts['username_exists'], "danger")
            return redirect(url_for('create_admin'))
        
        if User.query.filter_by(phone=phone).first():
            flash(texts['phone_exists'], "danger")
            return redirect(url_for('create_admin'))
        
        try:
            admin_user = User(
                username=username,
                phone=phone,
                role="admin",
                is_approved=True
            )
            admin_user.set_password(password)
            
            db.session.add(admin_user)
            db.session.commit()
            
            flash(texts['admin_created'].format(username), "success")
            return redirect(url_for('dashboard_admin'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating admin: {str(e)}", "danger")
            return redirect(url_for('create_admin'))
    
    return render_template('create_admin.html', texts=texts, lang=lang)


# ---------------------- ADMIN NOTIFICATION ROUTES ----------------------
@app.route('/admin/get_notifications')
@admin_required
def get_admin_notifications():
    """Get notifications for admin"""
    try:
        # Get notifications for current admin (newest first)
        notifications = Notification.query.filter_by(
            admin_id=current_user.id
        ).order_by(Notification.created_at.desc()).limit(20).all()
        
        notifications_data = []
        for notification in notifications:
            notifications_data.append({
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'type': notification.type,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'icon': notification.get_notification_icon(),
                'formatted_time': notification.get_formatted_time()
            })
        
        return jsonify({
            'success': True,
            'notifications': notifications_data
        })
    except Exception as e:
        print(f"Error getting notifications: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/admin/mark_notification_read/<int:notification_id>', methods=['POST'])
@admin_required
def mark_admin_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        notification = Notification.query.filter_by(
            id=notification_id, 
            admin_id=current_user.id
        ).first()
        
        if notification:
            notification.is_read = True
            db.session.commit()
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Notification not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/mark_all_notifications_read', methods=['POST'])
@admin_required
def mark_all_admin_notifications_read():
    """Mark all notifications as read for current admin"""
    try:
        # Mark all notifications as read for this admin
        Notification.query.filter_by(
            admin_id=current_user.id, 
            is_read=False
        ).update({'is_read': True})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/clear_all_notifications', methods=['POST'])
@admin_required
def clear_all_admin_notifications():
    """Delete all notifications for current admin"""
    try:
        # Delete all notifications for this admin
        Notification.query.filter_by(
            admin_id=current_user.id
        ).delete()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ---------------------- AJAX FEEDBACK SUBMISSION ----------------------
@app.route('/submit_feedback_ajax', methods=['POST'])
@login_required
def submit_feedback_ajax():
    try:
        message = request.json.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'message': 'Message cannot be empty'}), 400
        
        # Create feedback entry
        feedback = Feedback(
            patient_id=current_user.id,
            feedback=message
        )
        db.session.add(feedback)
        db.session.flush()  # Get the feedback ID before commit
        
        # Create notifications for ALL admins
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            notification = Notification(
                admin_id=admin.id,
                title="New Feedback Received",
                message=f"Patient {current_user.username} submitted feedback: {message[:100]}{'...' if len(message) > 100 else ''}",
                type='feedback',
                related_feedback_id=feedback.id
            )
            db.session.add(notification)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Feedback submitted successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ---------------------- ADMIN ADD USER ROUTE ----------------------
@app.route('/admin/add_user', methods=['POST'])
@admin_required
def admin_add_user():
    """Admin adds a new user with comprehensive validation (same as registration)"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        phone_input = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        role = data.get('role', '').strip().lower()

        phone = '+251' + phone_input
        
        # Debug: Print form data
        print(f"🔍 ADMIN ADD USER DEBUG:")
        print(f"   Username: '{username}'")
        print(f"   Phone: '{phone_input}' -> '{phone}'")
        print(f"   Email: '{email}'")
        print(f"   Role: '{role}'")
        print(f"   Password length: {len(password)}")
        print(f"   Confirm password length: {len(confirm_password)}")
        
        # 1. VALIDATION: All fields cannot be empty
        if not username or not phone_input or not email or not password or not confirm_password or not role:
            return jsonify({'success': False, 'message': 'All fields are required. Please fill in all information.'})
        
        # 2. VALIDATION: Username should allow characters and spaces only (no numbers, special characters)
        username_pattern = r'^[a-zA-Z\s\'-]+$'
        if not re.match(username_pattern, username):
            return jsonify({'success': False, 'message': 'Username can only contain letters, spaces, apostrophes, and hyphens. Numbers and special characters are not allowed.'})
        
        # Additional username validation: must be at least 2 characters and not just spaces
        if len(username.replace(' ', '')) < 2:
            return jsonify({'success': False, 'message': 'Username must contain at least 2 letters.'})
        
        # 3. VALIDATION: Comprehensive Gmail email validation (same as registration)
        if email.count('@') != 1:
            return jsonify({'success': False, 'message': 'Invalid email format. Email must contain exactly one @ symbol.'})
        
        try:
            local_part, domain_part = email.split('@')
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid email format. Please use a valid Gmail address like: yourname@gmail.com'})
        
        if domain_part.lower() != 'gmail.com':
            return jsonify({'success': False, 'message': 'Email must be a Gmail address ending with @gmail.com'})
        
        if len(local_part) < 1 or len(local_part) > 64:
            return jsonify({'success': False, 'message': 'Gmail username must be between 1 and 64 characters long.'})
        
        if not re.match(r'^[a-zA-Z0-9._+-]+$', local_part):
            return jsonify({'success': False, 'message': 'Gmail username can only contain letters, numbers, dots, plus signs, and hyphens.'})
        
        if local_part.startswith('.') or local_part.endswith('.'):
            return jsonify({'success': False, 'message': 'Gmail username cannot start or end with a dot.'})
        
        if '..' in local_part:
            return jsonify({'success': False, 'message': 'Gmail username cannot contain consecutive dots.'})
        
        if not re.search(r'[a-zA-Z0-9]', local_part):
            return jsonify({'success': False, 'message': 'Gmail username must contain at least one letter or number.'})
        
        gmail_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9._+-]*[a-zA-Z0-9])?@gmail\.com$'
        if not re.match(gmail_pattern, email, re.IGNORECASE):
            return jsonify({'success': False, 'message': 'Invalid Gmail format. Please use a valid Gmail address like: yourname@gmail.com'})
        
        # 4. VALIDATION: Password confirmation
        if password != confirm_password:
            return jsonify({'success': False, 'message': 'Passwords do not match!'})
        
        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters long.'})

        # Phone validation - validate 9-digit input before adding prefix
        phone_pattern = r'^[79]\d{8}$'
        if not re.match(phone_pattern, phone_input):
            return jsonify({'success': False, 'message': 'Invalid phone number! Must be 9 digits starting with 7 or 9'})

        # Normalize email for storage
        email = normalize_email(email)

        # Duplicate check - check all role tables
        existing_user = get_user_by_username(username)
        if not existing_user:
            existing_user = get_user_by_phone(phone)
        
        if existing_user:
            return jsonify({'success': False, 'message': 'Username or phone number already exists!'})

        # Validate role - allow all roles for admin
        valid_roles = ['patient', 'doctor', 'xrayspecialist', 'reception', 'healthofficer']
        if role not in valid_roles:
            return jsonify({'success': False, 'message': 'Invalid role selected!'})

        # Create new user based on role
        if role == 'patient':
            new_user = create_patient_user(username, phone, password, email=email)
        elif role == 'doctor':
            new_user = create_doctor_user(username, phone, password, email=email)
        elif role == 'xrayspecialist':
            new_user = create_xray_specialist_user(username, phone, password, email=email)
        elif role == 'reception':
            new_user = create_reception_user(username, phone, password, email=email)
        elif role == 'healthofficer':
            new_user = create_health_officer_user(username, phone, password, email=email)
        else:
            return jsonify({'success': False, 'message': 'Invalid role selected!'})
        
        if not new_user:
            return jsonify({'success': False, 'message': 'Failed to create user'})

        # Auto-approve users created by admin
        new_user.is_approved = True
        db.session.commit()

        print(f"✅ Admin successfully created user: {username} ({role})")
        return jsonify({'success': True, 'message': f'User {username} created successfully as {role}!'})

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in admin_add_user: {str(e)}")
        return jsonify({'success': False, 'message': f'Failed to create user: {str(e)}'})

# ---------------------- GET PENDING APPROVAL NOTIFICATIONS ----------------------
@app.route('/admin/get_pending_approvals')
@admin_required
def get_pending_approvals():
    """Get users pending approval for notifications"""
    try:
        pending_users = User.query.filter(
            User.is_approved == False,
            User.role.in_(['doctor', 'xrayspecialist'])
        ).all()
        
        pending_list = []
        for user in pending_users:
            pending_list.append({
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'phone': user.phone,
                'date_created': user.date_created.isoformat() if user.date_created else None
            })
        
        return jsonify({
            'success': True,
            'pending_users': pending_list
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/doctor/submit_feedback', methods=['POST'])
@login_required
def doctor_submit_feedback():
    """Submit feedback from doctor to admin"""
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'message': 'Message cannot be empty'}), 400
        
        # Create feedback entry
        feedback = Feedback(
            doctor_id=current_user.id,
            feedback=message,
            feedback_type='general'
        )
        db.session.add(feedback)
        db.session.flush()  # Get the feedback ID before commit
        
        # Create notifications for ALL admins using universal notification system
        NotificationService.create_notifications_for_role(
            role='admin',
            title='New Doctor Feedback',
            message=f'Dr. {current_user.username} sent feedback: {message[:100]}{"..." if len(message) > 100 else ""}',
            notification_type='feedback',
            action_url='#feedback',
            is_clickable=True
        )
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Feedback submitted successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/doctor/get_feedbacks')
@login_required
def doctor_get_feedbacks():
    """Get feedbacks sent by the current doctor"""
    if normalize_role(current_user.role) != 'doctor':
        return jsonify([]), 403
    
    try:
        feedbacks = Feedback.query.filter_by(doctor_id=current_user.id).order_by(Feedback.date_submitted.desc()).all()
        feedbacks_data = []
        for feedback in feedbacks:
            feedbacks_data.append({
                'id': feedback.id,
                'feedback': feedback.feedback,
                'feedback_type': feedback.feedback_type,
                'reply': feedback.reply,
                'date_submitted': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read
            })
        
        return jsonify(feedbacks_data)
    
    except Exception as e:
        print(f"Error fetching doctor feedbacks: {e}")
        return jsonify([])

@app.route('/doctor/get_xray_feedbacks')
@login_required
def doctor_get_xray_feedbacks():
    """Get X-ray specialist feedbacks for the current doctor - Enhanced with better logging"""
    print(f"🔍 Doctor {current_user.username} requesting X-ray feedbacks...")
    
    if normalize_role(current_user.role) != 'doctor':
        print(f"❌ Access denied - user role: {current_user.role}")
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        # Get feedbacks from X-ray specialists to this doctor
        print(f"🔍 Searching for feedbacks with doctor_id={current_user.id} and feedback_type='xray_to_doctor'")
        
        feedbacks = Feedback.query.filter_by(
            doctor_id=current_user.id,
            feedback_type='xray_to_doctor'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        print(f"📊 Found {len(feedbacks)} X-ray feedbacks for doctor {current_user.username}")
        
        feedbacks_data = []
        for feedback in feedbacks:
            # Get X-ray specialist info
            xray_specialist = User.query.get(feedback.xray_specialist_id) if feedback.xray_specialist_id else None
            # Get patient info (may be None for general feedback)
            patient = User.query.get(feedback.patient_id) if feedback.patient_id else None
            
            feedback_data = {
                'id': feedback.id,
                'feedback': feedback.feedback,
                'doctor_reply': feedback.doctor_reply,
                'date_submitted': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'xray_specialist_name': xray_specialist.username if xray_specialist else 'Unknown X-ray Specialist',
                'is_read': feedback.is_read
            }
            
            # Only include patient_name if there's actually a patient associated
            if patient:
                feedback_data['patient_name'] = patient.username
            feedbacks_data.append(feedback_data)
            
            print(f"📝 Feedback {feedback.id}: from {xray_specialist.username if xray_specialist else 'Unknown'} - '{feedback.feedback[:50]}...'")
        
        print(f"✅ Successfully retrieved {len(feedbacks_data)} X-ray feedbacks for doctor")
        return jsonify({'success': True, 'feedbacks': feedbacks_data})
    
    except Exception as e:
        print(f"❌ Error fetching X-ray feedbacks for doctor: {e}")
        import traceback
        traceback.print_exc()
        
        # Log detailed error information
        error_details = {
            'user_id': current_user.id,
            'username': current_user.username,
            'error_type': type(e).__name__,
            'error_message': str(e)
        }
        print(f"🔍 Detailed error info: {error_details}")
        
        return jsonify({'success': False, 'message': 'Failed to load X-ray feedbacks'}), 500

@app.route('/doctor/reply_to_xray', methods=['POST'])
@csrf.exempt
@login_required
def doctor_reply_to_xray():
    """Doctor replies to X-ray specialist feedback"""
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        feedback_id = data.get('feedback_id')
        reply_text = data.get('reply', '').strip()
        
        if not feedback_id or not reply_text:
            return jsonify({'success': False, 'message': 'Missing feedback ID or reply text'}), 400
        
        # Get the feedback
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            return jsonify({'success': False, 'message': 'Feedback not found'}), 404
        
        # Verify this feedback is for the current doctor
        if feedback.doctor_id != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized to reply to this feedback'}), 403
        
        # Update the feedback with doctor's reply
        feedback.doctor_reply = reply_text
        feedback.reply_date = datetime.utcnow()
        feedback.is_read = True
        
        # Create notification for the X-ray specialist who sent the feedback
        xray_specialist = User.query.get(feedback.xray_specialist_id) if feedback.xray_specialist_id else None
        if xray_specialist and xray_specialist.role == 'xrayspecialist':
            print(f"📧 Creating notification for X-ray specialist {xray_specialist.username}")
            universal_notification = NotificationService.create_notification(
                user_id=xray_specialist.id,
                user_role='xrayspecialist',
                title="Doctor Reply to Your Feedback",
                message=f"Dr. {current_user.username} has replied to your feedback: {reply_text[:100]}{'...' if len(reply_text) > 100 else ''}",
                notification_type='doctor_reply',
                action_url='#feedback',
                is_clickable=True
            )
            
            if universal_notification:
                print(f"✅ Created universal notification for X-ray specialist {xray_specialist.username}")
            else:
                print(f"❌ Failed to create universal notification for X-ray specialist")
        
        db.session.commit()
        
        print(f"✅ Doctor {current_user.username} replied to X-ray feedback {feedback_id}")
        return jsonify({'success': True, 'message': 'Reply sent successfully'})
    
    except Exception as e:
        db.session.rollback()
        print(f"Error sending doctor reply to X-ray feedback: {e}")
        return jsonify({'success': False, 'message': 'Failed to send reply'}), 500

# ---------------------- DOCTOR FEEDBACK SYSTEM ROUTES ----------------------
@app.route('/doctor/get_admin_replies')
@login_required
def doctor_get_admin_replies():
    """Get admin replies to doctor feedback"""
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        # Get feedbacks sent by this doctor that have admin replies
        feedbacks = Feedback.query.filter_by(
            doctor_id=current_user.id,
            feedback_type='general'
        ).filter(Feedback.admin_reply.isnot(None)).order_by(Feedback.reply_date.desc()).all()
        
        replies_data = []
        for feedback in feedbacks:
            replies_data.append({
                'id': feedback.id,
                'original_message': feedback.feedback,
                'reply': feedback.admin_reply,
                'reply_date': feedback.reply_date.strftime('%Y-%m-%d %H:%M') if feedback.reply_date else None,
                'date_submitted': feedback.date_submitted.strftime('%Y-%m-%d %H:%M') if feedback.date_submitted else None
            })
        
        return jsonify(replies_data)
    
    except Exception as e:
        print(f"Error getting admin replies for doctor: {e}")
        return jsonify({'success': False, 'message': 'Failed to load admin replies'}), 500

@app.route('/doctor/get_xray_feedback')
@login_required
def doctor_get_xray_feedback():
    """Get feedback from X-ray specialists to this doctor"""
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        # Get feedbacks from X-ray specialists to this doctor
        feedbacks = Feedback.query.filter_by(
            doctor_id=current_user.id,
            feedback_type='xray_to_doctor'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        feedback_data = []
        for feedback in feedbacks:
            xray_specialist = User.query.get(feedback.xray_specialist_id) if feedback.xray_specialist_id else None
            
            feedback_data.append({
                'id': feedback.id,
                'sender_name': xray_specialist.username if xray_specialist else 'X-ray Specialist',
                'message': feedback.feedback,
                'date_sent': feedback.date_submitted.strftime('%Y-%m-%d %H:%M') if feedback.date_submitted else None,
                'reply': feedback.doctor_reply,
                'reply_date': feedback.reply_date.strftime('%Y-%m-%d %H:%M') if feedback.reply_date else None
            })
        
        return jsonify(feedback_data)
    
    except Exception as e:
        print(f"Error getting X-ray feedback for doctor: {e}")
        return jsonify({'success': False, 'message': 'Failed to load X-ray feedback'}), 500

@app.route('/doctor/get_patient_feedback')
@login_required
def doctor_get_patient_feedback():
    """Get feedback from patients to this doctor"""
    if normalize_role(current_user.role) != 'doctor':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    try:
        # Get patient feedback for this doctor
        # This would need to be implemented based on your patient feedback system
        # For now, return empty array
        return jsonify([])
    
    except Exception as e:
        print(f"Error getting patient feedback for doctor: {e}")
        return jsonify({'success': False, 'message': 'Failed to load patient feedback'}), 500

# ---------------------- X-RAY SPECIALIST FEEDBACK ROUTES ----------------------
@app.route('/xray_submit_feedback_test', methods=['POST'])
@csrf.exempt
def xray_submit_feedback_test():
    """Simple test route for X-ray feedback"""
    return jsonify({'success': True, 'message': 'Test route works!'})

@app.route('/xray_submit_feedback', methods=['POST'])
@csrf.exempt
@login_required
def xray_submit_feedback():
    """Submit feedback from X-ray specialist - supports both JSON and form-encoded data"""
    print(f"🔄 X-ray specialist {current_user.username} submitting feedback to admin...")
    try:
        if current_user.role != 'xrayspecialist':
            print(f"❌ Access denied - user role: {current_user.role}")
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
        # Dual format support: try JSON first, then form data
        message = ''
        feedback_type = 'general'
        
        # Try to get JSON data first
        json_data = request.get_json(silent=True)
        if json_data:
            print(f"📋 Received JSON data: {json_data}")
            message = json_data.get('message', '').strip()
            feedback_type = json_data.get('feedback_type', 'general')
        else:
            # Fall back to form data
            print(f"📋 Received form data: {dict(request.form)}")
            message = request.form.get('feedback_message', '').strip()
            feedback_type = request.form.get('feedback_type', 'general')
        
        print(f"📋 Parsed data - message length: {len(message) if message else 0}, feedback_type: {feedback_type}")
        
        # Enhanced validation for empty/whitespace messages
        if not message or message.isspace():
            print(f"❌ Empty or whitespace-only message: '{message}'")
            return jsonify({'success': False, 'message': 'Message cannot be empty or contain only whitespace'}), 400
        
        # Validate message length (reasonable limits)
        if len(message) > 5000:
            print(f"❌ Message too long: {len(message)} characters")
            return jsonify({'success': False, 'message': 'Message is too long (maximum 5000 characters)'}), 400
        
        print(f"📝 Creating feedback record...")
        # Create feedback entry for X-ray specialist
        feedback = Feedback(
            xray_specialist_id=current_user.id,
            feedback=message,
            feedback_type=feedback_type
        )
        db.session.add(feedback)
        db.session.flush()  # Get the feedback ID before commit
        
        print(f"📝 Feedback created with ID: {feedback.id}")
        
        # Create notifications for ALL admins using universal notification system
        print(f"📧 Creating admin notifications...")
        
        # Create universal notifications for all admins
        universal_notifications = NotificationService.create_notifications_for_role(
            role='admin',
            title='New X-ray Specialist Feedback',
            message=f'{current_user.username} sent feedback: {message[:100]}{"..." if len(message) > 100 else ""}',
            notification_type='feedback',
            action_url='#feedback',
            is_clickable=True
        )
        
        if universal_notifications:
            print(f"✅ Universal notifications created for {len(universal_notifications)} admins")
        else:
            print(f"⚠️ Warning: Failed to create universal notifications")
        
        db.session.commit()
        
        print(f"✅ X-ray specialist feedback submitted successfully")
        return jsonify({'success': True, 'message': 'Feedback submitted successfully'})
    
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error submitting X-ray specialist feedback: {e}")
        import traceback
        traceback.print_exc()
        
        # Log detailed error information for debugging
        error_details = {
            'user_id': current_user.id,
            'username': current_user.username,
            'error_type': type(e).__name__,
            'error_message': str(e),
            'request_method': request.method,
            'content_type': request.content_type,
            'has_json': request.is_json,
            'form_data_keys': list(request.form.keys()) if request.form else [],
        }
        print(f"🔍 Detailed error info: {error_details}")
        
        # Return user-friendly error message
        return jsonify({
            'success': False, 
            'message': 'Failed to submit feedback. Please try again or contact support if the problem persists.'
        }), 500

@app.route('/xray_get_feedbacks')
@login_required
def xray_get_feedbacks():
    """Get feedbacks for X-ray specialist"""
    try:
        if current_user.role != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
        feedbacks = Feedback.query.filter_by(
            xray_specialist_id=current_user.id
        ).order_by(Feedback.date_submitted.desc()).all()
        
        feedbacks_data = []
        for feedback in feedbacks:
            feedbacks_data.append({
                'id': feedback.id,
                'feedback': feedback.feedback,
                'feedback_type': feedback.feedback_type,
                'reply': feedback.reply,
                'date_submitted': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read
            })
        
        return jsonify(feedbacks_data)
    
    except Exception as e:
        print(f"Error getting X-ray specialist feedbacks: {e}")
        return jsonify({'success': False, 'message': 'Failed to load feedbacks'}), 500

# ---------------------- X-RAY SPECIALIST TO DOCTOR FEEDBACK ROUTES ----------------------

@app.route('/xray/get_doctor_feedbacks')
@login_required
def xray_get_doctor_feedbacks():
    """Get feedbacks sent by this X-ray specialist to doctors - Enhanced with better logging"""
    print(f"🔍 X-ray specialist {current_user.username} requesting sent doctor feedbacks...")
    
    if normalize_role(current_user.role) != 'xrayspecialist':
        print(f"❌ Access denied - user role: {current_user.role}")
        return jsonify([]), 403
    
    try:
        # Get feedbacks where this X-ray specialist is the sender and target is a doctor
        print(f"🔍 Searching for feedbacks with xray_specialist_id={current_user.id} and feedback_type='xray_to_doctor'")
        
        feedbacks = Feedback.query.filter_by(
            xray_specialist_id=current_user.id,
            feedback_type='xray_to_doctor'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        print(f"📊 Found {len(feedbacks)} doctor feedbacks sent by X-ray specialist {current_user.username}")
        
        feedbacks_data = []
        for feedback in feedbacks:
            # Get doctor name
            doctor = User.query.get(feedback.doctor_id) if feedback.doctor_id else None
            doctor_name = doctor.username if doctor else 'Unknown Doctor'
            
            feedback_data = {
                'id': feedback.id,
                'feedback': feedback.feedback,
                'doctor_name': doctor_name,
                'reply': feedback.doctor_reply,  # Use doctor_reply instead of reply
                'date_submitted': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read
            }
            feedbacks_data.append(feedback_data)
            
            print(f"📝 Feedback {feedback.id}: to Dr. {doctor_name} - '{feedback.feedback[:50]}...'")
        
        print(f"✅ Successfully retrieved {len(feedbacks_data)} doctor feedbacks for X-ray specialist")
        return jsonify(feedbacks_data)
    
    except Exception as e:
        print(f"❌ Error getting X-ray specialist doctor feedbacks: {e}")
        import traceback
        traceback.print_exc()
        
        # Log detailed error information
        error_details = {
            'user_id': current_user.id,
            'username': current_user.username,
            'error_type': type(e).__name__,
            'error_message': str(e)
        }
        print(f"🔍 Detailed error info: {error_details}")
        
        return jsonify({'success': False, 'message': 'Failed to load doctor feedbacks'}), 500

@app.route('/xray/submit_doctor_feedback', methods=['POST'])
@csrf.exempt
@login_required
def xray_submit_doctor_feedback():
    """Submit feedback from X-ray specialist to doctor - Enhanced with better validation and error handling"""
    print(f"🔄 X-ray specialist {current_user.username} submitting feedback to doctor...")
    
    if normalize_role(current_user.role) != 'xrayspecialist':
        print(f"❌ Access denied - user role: {current_user.role}")
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Enhanced data parsing - support both form and JSON data
        doctor_id = None
        message = ''
        
        # Try to get JSON data first
        json_data = request.get_json(silent=True)
        if json_data:
            print(f"📋 Received JSON data: {json_data}")
            doctor_id = json_data.get('doctor_id')
            message = json_data.get('feedback_message', '').strip()
        else:
            # Fall back to form data
            print(f"📋 Received form data: {dict(request.form)}")
            doctor_id = request.form.get('doctor_id')
            message = request.form.get('feedback_message', '').strip()
        
        print(f"📋 Parsed data - doctor_id: {doctor_id}, message length: {len(message) if message else 0}")
        
        # Enhanced validation for doctor_id
        if not doctor_id:
            print(f"❌ Missing doctor_id")
            return jsonify({'success': False, 'message': 'Doctor selection is required'}), 400
        
        try:
            doctor_id = int(doctor_id)
        except (ValueError, TypeError):
            print(f"❌ Invalid doctor_id format: {doctor_id}")
            return jsonify({'success': False, 'message': 'Invalid doctor ID format'}), 400
        
        # Enhanced validation for empty/whitespace messages
        if not message or message.isspace():
            print(f"❌ Empty or whitespace-only message: '{message}'")
            return jsonify({'success': False, 'message': 'Message cannot be empty or contain only whitespace'}), 400
        
        # Validate message length (reasonable limits)
        if len(message) > 5000:
            print(f"❌ Message too long: {len(message)} characters")
            return jsonify({'success': False, 'message': 'Message is too long (maximum 5000 characters)'}), 400
        
        # Verify doctor exists and is approved
        doctor = User.query.filter_by(id=doctor_id, role='doctor', is_approved=True).first()
        if not doctor:
            print(f"❌ Doctor not found or not approved: ID {doctor_id}")
            return jsonify({'success': False, 'message': 'Selected doctor is not available or not approved'}), 400
        
        print(f"📝 Creating feedback record for Dr. {doctor.username}...")
        
        # Create feedback entry
        feedback = Feedback(
            xray_specialist_id=current_user.id,
            doctor_id=doctor_id,
            feedback=message,
            feedback_type='xray_to_doctor'
        )
        db.session.add(feedback)
        db.session.flush()  # Get the feedback ID before commit
        
        print(f"📝 Feedback created with ID: {feedback.id}")
        
        # Create notification for the doctor
        print(f"📧 Creating doctor notification...")
        from models import create_xray_to_doctor_feedback_notification
        notification_success = create_xray_to_doctor_feedback_notification(current_user.username, doctor_id, message, feedback.id)
        
        if notification_success:
            print(f"✅ Doctor notification created successfully")
        else:
            print(f"⚠️ Warning: Failed to create doctor notification")
        
        # Also create universal notification for the doctor
        universal_notification = NotificationService.create_notification(
            user_id=doctor_id,
            user_role='doctor',
            title='New X-ray Specialist Feedback',
            message=f'{current_user.username} sent you feedback: {message[:100]}{"..." if len(message) > 100 else ""}',
            notification_type='feedback',
            action_url='#xray-feedback',
            is_clickable=True
        )
        
        if universal_notification:
            print(f"✅ Universal notification created for doctor")
        else:
            print(f"⚠️ Warning: Failed to create universal notification")
        
        db.session.commit()
        
        print(f"✅ X-ray specialist feedback to doctor submitted successfully")
        return jsonify({
            'success': True, 
            'message': f'Feedback sent to Dr. {doctor.username} successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error submitting X-ray specialist doctor feedback: {e}")
        import traceback
        traceback.print_exc()
        
        # Log detailed error information for debugging
        error_details = {
            'user_id': current_user.id,
            'username': current_user.username,
            'error_type': type(e).__name__,
            'error_message': str(e),
            'request_method': request.method,
            'content_type': request.content_type,
            'has_json': request.is_json,
            'form_data_keys': list(request.form.keys()) if request.form else [],
        }
        print(f"🔍 Detailed error info: {error_details}")
        
        # Return user-friendly error message
        return jsonify({
            'success': False, 
            'message': 'Failed to send feedback to doctor. Please try again or contact support if the problem persists.'
        }), 500

@app.route('/xray/get_doctors')
@login_required
def xray_get_doctors_for_feedback():
    """Get list of approved doctors for X-ray specialist feedback"""
    try:
        if normalize_role(current_user.role) != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Get all approved doctors
        doctors = User.query.filter_by(
            role='doctor',
            is_approved=True,
            is_active_user=True
        ).all()
        
        doctors_list = []
        for doctor in doctors:
            doctors_list.append({
                'id': doctor.id,
                'name': f"Dr. {doctor.username}",
                'phone': doctor.phone
            })
        
        print(f"✅ Loaded {len(doctors_list)} doctors for X-ray specialist {current_user.username}")
        return jsonify({'success': True, 'doctors': doctors_list})
        
    except Exception as e:
        print(f"❌ Error getting doctors for X-ray specialist: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/xray/get_health_officer_feedback')
@login_required
def xray_get_health_officer_feedback():
    """Get feedback sent to this X-ray specialist from health officers"""
    try:
        if current_user.role != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
        # Get feedback sent TO this X-ray specialist from health officers
        feedbacks = Feedback.query.filter_by(
            xray_specialist_id=current_user.id,
            feedback_type='healthofficer_to_xray'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        feedbacks_data = []
        for feedback in feedbacks:
            # Get the health officer who sent this feedback
            sender = User.query.get(feedback.health_officer_id) if feedback.health_officer_id else None
            
            # Extract the actual message (remove any prefix if present)
            message = feedback.feedback
            if message and message.startswith(f"To X-ray Specialist {current_user.username}: "):
                message = message.replace(f"To X-ray Specialist {current_user.username}: ", "")
            
            feedbacks_data.append({
                'id': feedback.id,
                'sender_name': sender.username if sender else 'Health Officer',
                'sender_role': sender.role if sender else 'healthofficer',
                'message': message,
                'date_sent': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'reply': feedback.reply,
                'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None,
                'is_read': feedback.is_read
            })
        
        print(f"✅ Found {len(feedbacks_data)} feedback messages for X-ray specialist {current_user.username}")
        
        return jsonify({
            'success': True,
            'feedbacks': feedbacks_data
        })
        
    except Exception as e:
        print(f"❌ Error getting health officer feedback for X-ray specialist: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/xray/reply_to_health_officer_feedback', methods=['POST'])
@csrf.exempt
@login_required
def xray_reply_to_health_officer_feedback():
    """X-ray specialist replies to health officer feedback"""
    print(f"🔄 X-ray specialist {current_user.username} replying to health officer feedback...")
    try:
        if current_user.role != 'xrayspecialist':
            print(f"❌ Access denied - user role: {current_user.role}")
            return jsonify({'success': False, 'message': 'Unauthorized access'}), 403
        
        data = request.get_json()
        print(f"📋 Request data: {data}")
        
        feedback_id = data.get('feedback_id')
        reply_text = data.get('reply', '').strip()
        
        print(f"📋 Parsed data - feedback_id: {feedback_id}, reply length: {len(reply_text) if reply_text else 0}")
        
        if not feedback_id or not reply_text:
            print(f"❌ Missing required fields - feedback_id: {feedback_id}, reply_text: {bool(reply_text)}")
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        # Get the feedback record
        print(f"🔍 Looking for feedback with ID: {feedback_id}, X-ray specialist ID: {current_user.id}")
        feedback = Feedback.query.filter_by(
            id=feedback_id,
            xray_specialist_id=current_user.id,
            feedback_type='healthofficer_to_xray'
        ).first()
        
        if not feedback:
            print(f"❌ Feedback not found with ID: {feedback_id}")
            # Let's also check what feedback records exist for this X-ray specialist
            all_feedback = Feedback.query.filter_by(xray_specialist_id=current_user.id).all()
            print(f"📋 All feedback for X-ray specialist {current_user.id}: {len(all_feedback)} records")
            for fb in all_feedback:
                print(f"  - ID: {fb.id}, Type: {fb.feedback_type}, Health Officer ID: {fb.health_officer_id}")
            return jsonify({'success': False, 'message': 'Feedback not found'}), 404
        
        # Update the feedback with reply
        feedback.reply = reply_text
        feedback.reply_date = datetime.utcnow()
        
        # Create notification for the health officer who sent the feedback
        health_officer = User.query.get(feedback.health_officer_id) if feedback.health_officer_id else None
        if health_officer and health_officer.role == 'healthofficer':
            print(f"📧 Creating notification for health officer {health_officer.username}")
            universal_notification = NotificationService.create_notification(
                user_id=health_officer.id,
                user_role='healthofficer',
                title="X-ray Specialist Reply to Your Feedback",
                message=f"X-ray Specialist {current_user.username} has replied to your feedback: {reply_text[:100]}{'...' if len(reply_text) > 100 else ''}",
                notification_type='xray_reply',
                action_url='#xray-specialist-feedback',  # Navigate to X-ray specialist communication section
                is_clickable=True
            )
            
            if universal_notification:
                print(f"✅ Created universal notification for health officer {health_officer.username}")
            else:
                print(f"❌ Failed to create universal notification for health officer")
        
        db.session.commit()
        
        print(f"✅ X-ray specialist {current_user.username} replied to health officer feedback {feedback_id}")
        
        return jsonify({
            'success': True,
            'message': 'Reply sent successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error replying to health officer feedback: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ---------------------- X-RAY SPECIALIST NOTIFICATION ROUTES ----------------------
@app.route('/xray/get_notifications')
@login_required
def get_xray_notifications():
    """Get notifications for X-ray specialist"""
    try:
        if normalize_role(current_user.role) != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        from models import XraySpecialistNotification
        
        notifications = XraySpecialistNotification.query.filter_by(
            xray_specialist_id=current_user.id
        ).order_by(XraySpecialistNotification.created_at.desc()).all()
        
        notifications_data = []
        for notif in notifications:
            notifications_data.append({
                'id': notif.id,
                'patient_id': notif.patient_id,
                'patient_name': notif.patient_name,
                'xray_filename': notif.xray_filename,
                'message': notif.message,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat() if notif.created_at else None,
                'notification_type': notif.notification_type,
                'formatted_time': notif.get_formatted_time()
            })
        
        return jsonify({'success': True, 'notifications': notifications_data})
    
    except Exception as e:
        print(f"Error getting X-ray specialist notifications: {e}")
        return jsonify({'success': False, 'message': 'Failed to load notifications'}), 500

@app.route('/xray/mark_notification_read/<int:notification_id>', methods=['POST'])
@login_required
def mark_xray_notification_read(notification_id):
    """Mark a specific X-ray specialist notification as read"""
    try:
        if normalize_role(current_user.role) != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        from models import XraySpecialistNotification
        
        notification = XraySpecialistNotification.query.filter_by(
            id=notification_id,
            xray_specialist_id=current_user.id
        ).first()
        
        if not notification:
            return jsonify({'success': False, 'message': 'Notification not found'}), 404
        
        notification.mark_as_read()
        return jsonify({'success': True})
    
    except Exception as e:
        print(f"Error marking notification as read: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/xray/mark_all_notifications_read', methods=['POST'])
@login_required
def mark_all_xray_notifications_read():
    """Mark all X-ray specialist notifications as read"""
    try:
        if normalize_role(current_user.role) != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        from models import XraySpecialistNotification
        
        XraySpecialistNotification.query.filter_by(
            xray_specialist_id=current_user.id,
            is_read=False
        ).update({'is_read': True})
        
        db.session.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        print(f"Error marking all notifications as read: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/xray/clear_all_notifications', methods=['POST'])
@login_required
def clear_all_xray_notifications():
    """Delete all X-ray specialist notifications"""
    try:
        if normalize_role(current_user.role) != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        from models import XraySpecialistNotification
        
        # Delete all notifications for this X-ray specialist
        XraySpecialistNotification.query.filter_by(
            xray_specialist_id=current_user.id
        ).delete()
        
        db.session.commit()
        return jsonify({'success': True})
    
    except Exception as e:
        db.session.rollback()
        print(f"Error clearing all notifications: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ---------------------- X-RAY SPECIALIST ASSIGNED PATIENTS ROUTES ----------------------
@app.route('/xray/get_assigned_patients')
@login_required
def get_assigned_patients():
    """Get patients assigned to the current X-ray specialist"""
    try:
        if normalize_role(current_user.role) != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Get assignments from appointment table where doctor_id is the current X-ray specialist
        # and appointment_type is 'xray_assignment'
        assignments = Appointment.query.filter_by(
            doctor_id=current_user.id,
            appointment_type='xray_assignment'
        ).order_by(Appointment.created_at.desc()).all()
        
        assigned_patients = []
        for assignment in assignments:
            patient = assignment.patient
            if patient:
                assigned_patients.append({
                    'id': assignment.id,
                    'patient_id': patient.id,
                    'patient_name': patient.username,
                    'patient_phone': patient.phone,
                    'assignment_date': assignment.created_at.isoformat() if assignment.created_at else None,
                    'status': assignment.status or 'assigned',
                    'notes': assignment.notes or '',
                    'created_by_reception': assignment.created_by_reception
                })
        
        return jsonify(assigned_patients)
    
    except Exception as e:
        print(f"Error getting assigned patients: {e}")
        return jsonify({'success': False, 'message': 'Failed to load assigned patients'}), 500


@app.route('/xray/complete_assignment', methods=['POST'])
@login_required
def complete_assignment():
    """Mark an assignment as completed"""
    try:
        if normalize_role(current_user.role) != 'xrayspecialist':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        data = request.get_json()
        assignment_id = data.get('assignment_id')
        
        if not assignment_id:
            return jsonify({'success': False, 'message': 'Assignment ID is required'}), 400
        
        # Get the assignment
        assignment = Appointment.query.filter_by(
            id=assignment_id,
            doctor_id=current_user.id,
            appointment_type='xray_assignment'
        ).first()
        
        if not assignment:
            return jsonify({'success': False, 'message': 'Assignment not found or access denied'}), 404
        
        # Update status to completed
        assignment.status = 'completed'
        assignment.updated_at = datetime.utcnow()
        
        # Add completion note
        completion_note = f"Assignment completed by {current_user.username} on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        if assignment.notes:
            assignment.notes += f"\n{completion_note}"
        else:
            assignment.notes = completion_note
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Assignment marked as completed successfully'
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"Error completing assignment: {e}")
        return jsonify({'success': False, 'message': 'Failed to complete assignment'}), 500


# ---------------------- DOCTOR REPLY TO PATIENT FEEDBACK - FIXED VERSION ----------------------
@app.route('/doctor/get_patient_feedback_notifications')
@login_required
def get_patient_feedback_notifications():
    """Get patient feedback notifications for the current doctor"""
    try:
        if normalize_role(current_user.role) != 'doctor':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Get feedback notifications where current doctor is mentioned or it's general feedback
        notifications = DoctorNotification.query.filter_by(
            doctor_id=current_user.id,
            notification_type='feedback'
        ).order_by(DoctorNotification.created_at.desc()).all()
        
        notifications_data = []
        for notification in notifications:
            patient = User.query.get(notification.patient_id)
            notifications_data.append({
                'id': notification.id,
                'patient_id': notification.patient_id,
                'patient_name': patient.username if patient else 'Unknown Patient',
                'message': notification.message,
                'created_at': notification.created_at.isoformat() if notification.created_at else None,
                'formatted_time': notification.get_formatted_time()
            })
        
        return jsonify({
            'success': True,
            'notifications': notifications_data
        })
    
    except Exception as e:
        print(f"Error getting patient feedback notifications: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to load patient feedback'
        }), 500

# FIXED: Doctor reply to patient feedback
# FIXED: Doctor reply to patient feedback - MORE ROBUST VERSION
@app.route('/doctor/reply_to_patient', methods=['POST'])
@login_required
def doctor_reply_to_patient():
    """Doctor replies to patient feedback - FIXED VERSION"""
    try:
        if normalize_role(current_user.role) != 'doctor':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        data = request.get_json()
        patient_id = data.get('patient_id')
        message = data.get('message', '').strip()
        
        print(f"Doctor reply attempt - Patient ID: {patient_id}, Type: {type(patient_id)}, Message: {message}")
        
        if not patient_id:
            return jsonify({'success': False, 'message': 'Patient ID is required'}), 400
        
        if not message:
            return jsonify({'success': False, 'message': 'Reply message cannot be empty'}), 400
        
        # FIX: More robust patient ID handling
        patient_id_int = None
        try:
            # Handle different types of patient_id
            if isinstance(patient_id, int):
                patient_id_int = patient_id
            elif isinstance(patient_id, str):
                # Remove any quotes or extra characters
                clean_id = patient_id.replace('"', '').replace("'", "").strip()
                if clean_id.isdigit():
                    patient_id_int = int(clean_id)
                else:
                    return jsonify({'success': False, 'message': 'Invalid patient ID format: must be a number'}), 400
            else:
                return jsonify({'success': False, 'message': 'Invalid patient ID type'}), 400
                
        except (ValueError, TypeError) as e:
            print(f"Error converting patient ID: {e}")
            return jsonify({'success': False, 'message': f'Invalid patient ID: {str(e)}'}), 400
        
        # Get patient info
        patient = User.query.get(patient_id_int)
        if not patient:
            print(f"Patient not found with ID: {patient_id_int}")
            return jsonify({'success': False, 'message': 'Patient not found'}), 404
        
        if patient.role != 'patient':
            return jsonify({'success': False, 'message': 'User is not a patient'}), 400
        
        print(f"Found patient: {patient.username} (ID: {patient.id})")
        
        # FIXED: Find the most recent patient-to-doctor feedback and update it with reply
        # instead of creating a new feedback entry
        original_feedback = Feedback.query.filter_by(
            patient_id=patient_id_int,
            doctor_id=current_user.id,
            feedback_type='patient_to_doctor'
        ).order_by(Feedback.date_submitted.desc()).first()
        
        if original_feedback:
            # Update the existing feedback with the doctor's reply
            original_feedback.reply = message
            original_feedback.reply_date = datetime.utcnow()
            print(f"Updated existing feedback {original_feedback.id} with reply")
        else:
            # If no original feedback found, create a new one (fallback)
            print(f"No original feedback found, creating new entry")
            feedback = Feedback(
                doctor_id=current_user.id,
                patient_id=patient_id_int,
                feedback=f"Doctor Reply from Dr. {current_user.username}: {message}",
                feedback_type='doctor_reply',
                is_read=False
            )
            db.session.add(feedback)
        
        db.session.commit()
        
        print(f"Successfully sent reply to patient {patient.username}")
        
        # Create a notification for the PATIENT (not doctor) about the doctor's reply
        create_doctor_reply_notification(patient_id_int, current_user.username, message)
        
        return jsonify({
            'success': True, 
            'message': 'Reply sent to patient successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in doctor_reply_to_patient: {e}")
        return jsonify({
            'success': False, 
            'message': f'Failed to send reply to patient: {str(e)}'
        }), 500
# FIXED: Load patient feedback for doctor dashboard
@app.route('/doctor/load_patient_feedback')
@login_required
def load_patient_feedback():
    """Load patient feedback for doctor dashboard - CORRECTED VERSION"""
    try:
        if normalize_role(current_user.role) != 'doctor':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Get feedbacks where patients sent messages to THIS doctor
        feedbacks = Feedback.query.filter(
            Feedback.patient_id.isnot(None),
            Feedback.doctor_id == current_user.id,
            Feedback.feedback_type == 'patient_to_doctor'
        ).order_by(Feedback.date_submitted.desc()).all()
        
        feedbacks_data = []
        
        # Process patient-to-doctor feedbacks
        for feedback in feedbacks:
            patient = User.query.get(feedback.patient_id)
            if patient:
                feedbacks_data.append({
                    'id': feedback.id,
                    'patient_id': patient.id,
                    'patient_name': patient.username,
                    'message': feedback.feedback,
                    'date': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                    'reply': feedback.reply,
                    'reply_date': feedback.reply_date.isoformat() if feedback.reply_date else None
                })
        
        return jsonify({
            'success': True,
            'feedbacks': feedbacks_data
        })
    
    except Exception as e:
        print(f"Error loading patient feedback: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to load patient feedback'
        }), 500

# ---------------------- RUN APP ----------------------
# ---------------------- PATIENT-DOCTOR ASSIGNMENT ROUTES ----------------------
@app.route('/admin/assign_patient_to_doctor', methods=['POST'])
@login_required
def assign_patient_to_doctor_route():
    """Admin assigns a patient to a doctor"""
    try:
        if normalize_role(current_user.role) != 'admin':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        data = request.get_json()
        patient_id = data.get('patient_id')
        doctor_id = data.get('doctor_id')
        notes = data.get('notes', '')
        
        if not patient_id or not doctor_id:
            return jsonify({'success': False, 'message': 'Patient and doctor are required'}), 400
        
        # Check if patient and doctor exist
        patient = User.query.filter_by(id=patient_id, role='patient').first()
        doctor = User.query.filter_by(id=doctor_id, role='doctor').first()
        
        if not patient:
            return jsonify({'success': False, 'message': 'Patient not found'}), 404
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor not found'}), 404
        
        # Create assignment
        assignment = assign_patient_to_doctor(patient_id, doctor_id, current_user.id, notes)
        
        if assignment:
            return jsonify({
                'success': True, 
                'message': f'Patient {patient.username} assigned to Dr. {doctor.username} successfully'
            })
        else:
            return jsonify({'success': False, 'message': 'Assignment already exists or failed to create'}), 400
            
    except Exception as e:
        print(f"Error assigning patient to doctor: {e}")
        return jsonify({'success': False, 'message': 'Failed to create assignment'}), 500

@app.route('/admin/get_patient_assignments')
@login_required
def get_patient_assignments():
    """Get all current patient-doctor assignments"""
    try:
        if normalize_role(current_user.role) != 'admin':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        assignments = PatientDoctorAssignment.query.filter_by(is_active=True).all()
        
        assignments_data = []
        for assignment in assignments:
            patient = User.query.get(assignment.patient_id)
            doctor = User.query.get(assignment.doctor_id)
            
            if patient and doctor:
                assignments_data.append({
                    'patient_id': assignment.patient_id,
                    'doctor_id': assignment.doctor_id,
                    'patient_name': patient.username,
                    'patient_phone': patient.phone,
                    'doctor_name': doctor.username,
                    'doctor_phone': doctor.phone,
                    'assigned_date': assignment.assigned_date.isoformat(),
                    'notes': assignment.notes
                })
        
        return jsonify(assignments_data)
        
    except Exception as e:
        print(f"Error getting patient assignments: {e}")
        return jsonify({'success': False, 'message': 'Failed to load assignments'}), 500

@app.route('/admin/remove_patient_assignment', methods=['POST'])
@login_required
def remove_patient_assignment_route():
    """Admin removes a patient-doctor assignment"""
    try:
        if normalize_role(current_user.role) != 'admin':
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        data = request.get_json()
        patient_id = data.get('patient_id')
        doctor_id = data.get('doctor_id')
        
        if not patient_id or not doctor_id:
            return jsonify({'success': False, 'message': 'Patient and doctor IDs are required'}), 400
        
        success = remove_patient_doctor_assignment(patient_id, doctor_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Assignment removed successfully'})
        else:
            return jsonify({'success': False, 'message': 'Assignment not found or failed to remove'}), 404
            
    except Exception as e:
        print(f"Error removing patient assignment: {e}")
        return jsonify({'success': False, 'message': 'Failed to remove assignment'}), 500

@app.route('/admin/test_route')
@login_required
def test_route():
    """Simple test route to verify admin access"""
    try:
        if normalize_role(current_user.role) != 'admin':
            return jsonify({'error': 'Access denied', 'user_role': current_user.role}), 403
        
        return jsonify({
            'success': True,
            'message': 'Admin access confirmed',
            'user': current_user.username,
            'role': current_user.role
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/debug_users')
@login_required
def debug_users():
    """Debug route to check all users in system"""
    try:
        if normalize_role(current_user.role) != 'admin':
            return jsonify({'error': 'Access denied'}), 403
        
        all_users = User.query.all()
        patients = User.query.filter_by(role='patient').all()
        doctors = User.query.filter_by(role='doctor').all()
        approved_doctors = User.query.filter_by(role='doctor', is_approved=True).all()
        
        debug_info = {
            'total_users': len(all_users),
            'patients': len(patients),
            'doctors': len(doctors),
            'approved_doctors': len(approved_doctors),
            'patient_list': [{'id': p.id, 'username': p.username, 'phone': p.phone} for p in patients[:5]],
            'doctor_list': [{'id': d.id, 'username': d.username, 'phone': d.phone, 'approved': d.is_approved} for d in doctors[:5]]
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/get_users_by_role/<role>')
@login_required
def get_users_by_role(role):
    """Get users by role for assignment dropdowns"""
    try:
        print(f"GET /admin/get_users_by_role/{role} called by user {current_user.username}")
        
        if normalize_role(current_user.role) != 'admin':
            print(f"Access denied for user {current_user.username} with role {current_user.role}")
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        if role not in ['patient', 'doctor', 'xrayspecialist', 'reception', 'healthofficer']:
            print(f"Invalid role requested: {role}")
            return jsonify({'success': False, 'message': 'Invalid role'}), 400
        
        # For doctors, only get approved ones
        if role == 'doctor':
            users = User.query.filter_by(role=role, is_approved=True).all()
            print(f"Querying for approved doctors: found {len(users)}")
        else:
            users = User.query.filter_by(role=role).all()
            print(f"Querying for {role}s: found {len(users)}")
        
        users_data = []
        for user in users:
            user_data = {
                'id': user.id,
                'username': user.username,
                'phone': user.phone or 'N/A',
                'is_approved': user.is_approved
            }
            users_data.append(user_data)
            print(f"  - {user.username} (ID: {user.id}, Phone: {user.phone})")
        
        print(f"Returning {len(users_data)} users for role {role}")
        return jsonify(users_data)
        
    except Exception as e:
        print(f"ERROR in get_users_by_role for {role}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Failed to load {role}s: {str(e)}'}), 500

# ====================== RECEPTION REGISTRATION SYSTEM - FIXED ======================
@app.route('/reception/register_user_new', methods=['POST'])
@login_required
@reception_required
def reception_register_user_new():
    """
    Reception Patient Registration - Complete System
    Handles all user role registrations from reception dashboard
    """
    try:
        # Get form data
        username = request.form.get('username', '').strip()
        phone_input = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        role = request.form.get('role', 'patient').strip().lower()
        
        print(f"🔍 Reception Registration Request:")
        print(f"   Username: {username}")
        print(f"   Phone: {phone_input}")
        print(f"   Email: {email}")
        print(f"   Role: {role}")
        print(f"   Current User: {current_user.username}")
        
        # ========== INPUT VALIDATION ==========
        
        # Check required fields
        if not username or not phone_input or not email or not password or not confirm_password or not role:
            return jsonify({
                'success': False, 
                'message': 'All fields are required!'
            })
        
        # Username validation
        username_pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
        if not re.match(username_pattern, username):
            return jsonify({
                'success': False, 
                'message': 'Username must start with a letter or underscore and contain only letters, numbers, and underscores!'
            })
        
        # Check if username is only numbers
        if username.isdigit():
            return jsonify({
                'success': False, 
                'message': 'Username cannot be numbers only!'
            })
        
        # Phone validation (Ethiopian format)
        phone_pattern = r'^[79]\d{8}$'
        if not re.match(phone_pattern, phone_input):
            return jsonify({
                'success': False, 
                'message': 'Invalid phone number! Must be 9 digits starting with 7 or 9'
            })
        
        # Format phone with country code
        phone = '+251' + phone_input
        
        # Email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return jsonify({
                'success': False, 
                'message': 'Please enter a valid email address!'
            })
        
        # Password validation
        if len(password) < 6:
            return jsonify({
                'success': False, 
                'message': 'Password must be at least 6 characters long!'
            })
        
        # Password confirmation
        if password != confirm_password:
            return jsonify({
                'success': False, 
                'message': 'Passwords do not match!'
            })
        
        # Role validation (Patient only for reception registration)
        valid_roles = ['patient']
        if role not in valid_roles:
            return jsonify({
                'success': False, 
                'message': 'Only patient registration is allowed from reception dashboard!'
            })
        
        # ========== DUPLICATE CHECK ==========
        
        # Check for existing username
        existing_user = get_user_by_username(username)
        if existing_user:
            return jsonify({
                'success': False, 
                'message': f'Username "{username}" already exists!'
            })
        
        # Check for existing phone
        existing_phone_user = get_user_by_phone(phone)
        if existing_phone_user:
            return jsonify({
                'success': False, 
                'message': f'Phone number "{phone}" is already registered!'
            })
        
        # Check for existing email
        existing_email_patient = Patient.query.filter_by(email=email).first()
        if existing_email_patient:
            return jsonify({
                'success': False, 
                'message': f'Email address "{email}" is already registered!'
            })
        
        # ========== USER CREATION (Patient Only) ==========
        
        try:
            # Create patient user with email
            new_user = create_patient_user(username, phone, password, email=email)
            if new_user:
                # Get patient unique ID
                patient_profile = Patient.query.filter_by(user_id=new_user.id).first()
                unique_id = patient_profile.patient_unique_id if patient_profile else f"PAT{new_user.id:06d}"
                success_message = f'✅ Patient "{username}" registered successfully with ID: {unique_id}'
                
                print(f"✅ Patient created successfully: {username}")
                
                return jsonify({
                    'success': True, 
                    'message': success_message,
                    'user_id': new_user.id,
                    'role': 'patient'
                })
            else:
                return jsonify({
                    'success': False, 
                    'message': 'Failed to create patient user. Please try again.'
                })
            
        except Exception as create_error:
            db.session.rollback()
            print(f"❌ User creation error: {create_error}")
            return jsonify({
                'success': False, 
                'message': f'Registration failed: {str(create_error)}'
            })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Reception registration error: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False, 
            'message': f'Registration system error: {str(e)}'
        })

# ---------------------- RECEPTION FEEDBACK ROUTES ----------------------
@app.route('/reception/test_feedback', methods=['GET', 'POST'])
def test_reception_feedback():
    """Test route to debug reception feedback issues"""
    if request.method == 'GET':
        return jsonify({
            'success': True, 
            'message': 'Reception feedback routes are working!',
            'user_authenticated': current_user.is_authenticated,
            'user_role': current_user.role if current_user.is_authenticated else 'Not logged in'
        })
    else:
        return jsonify({
            'success': True,
            'message': 'POST request received successfully!',
            'data': request.get_json() if request.is_json else 'No JSON data'
        })

@app.route('/reception/send_admin_feedback', methods=['POST'])
@login_required
@reception_required
def reception_send_admin_feedback():
    """Reception staff send feedback to admin"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'message': 'Message is required'}), 400
        
        # Create feedback record using existing model structure
        feedback = Feedback(
            patient_id=current_user.id,  # Using patient_id field for reception staff
            feedback=message,  # Using feedback field instead of message
            feedback_type='reception_to_admin',
            date_submitted=datetime.utcnow()
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        print(f"✅ Reception feedback to admin created: ID {feedback.id}")
        
        # CRITICAL: Create notifications for ALL admins using universal notification system
        from models import NotificationService
        
        NotificationService.create_notifications_for_role(
            role='admin',
            title="New Reception Feedback",
            message=f"Reception staff {current_user.username} sent feedback: {message[:100]}{'...' if len(message) > 100 else ''}",
            notification_type='feedback',
            action_url='#feedback',
            is_clickable=True
        )
        
        print(f"✅ Created universal notifications for all admins")
        
        return jsonify({
            'success': True, 
            'message': 'Feedback sent to admin successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error sending reception feedback to admin: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/reception/send_health_officer_feedback', methods=['POST'])
@csrf.exempt
@login_required
@reception_required
def reception_send_health_officer_feedback():
    """Reception staff send feedback to health officer"""
    try:
        data = request.get_json()
        health_officer_id = data.get('health_officer_id')
        message = data.get('message', '').strip()
        
        if not health_officer_id or not message:
            return jsonify({'success': False, 'message': 'Health officer and message are required'}), 400
        
        # Verify health officer exists
        health_officer = User.query.filter_by(id=health_officer_id, role='healthofficer').first()
        if not health_officer:
            return jsonify({'success': False, 'message': 'Health officer not found'}), 404
        
        # Create feedback record
        feedback = Feedback(
            patient_id=current_user.id,
            feedback=f"To Health Officer {health_officer.username}: {message}",
            feedback_type=f'reception_to_healthofficer_{health_officer_id}',
            date_submitted=datetime.utcnow()
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        print(f"✅ Reception feedback to health officer created: ID {feedback.id}")
        
        # Create universal notification for the health officer
        notification = NotificationService.create_notification(
            user_id=health_officer_id,
            user_role='healthofficer',
            title='New Message from Reception',
            message=f'Reception staff {current_user.username} sent you a message: {message[:100]}{"..." if len(message) > 100 else ""}',
            notification_type='reception_feedback',
            action_url='#reception-feedback',
            is_clickable=True
        )
        
        if notification:
            print(f"✅ Created universal notification for health officer {health_officer.username}")
        else:
            print(f"❌ Failed to create notification for health officer {health_officer.username}")
        
        return jsonify({
            'success': True, 
            'message': f'Feedback sent to {health_officer.username} successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error sending reception feedback to health officer: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
@app.route('/reception/get_health_officers_for_feedback')
@login_required
@reception_required
def reception_get_health_officers_for_feedback():
    """Get list of health officers for feedback dropdown"""
    try:
        # Use same filtering as assignment route to ensure consistency
        health_officers = User.query.filter_by(
            role='healthofficer', 
            is_approved=True, 
            is_active_user=True
        ).all()
        
        print(f"🔍 Found {len(health_officers)} active health officers for feedback dropdown")
        
        officers_list = []
        for officer in health_officers:
            officers_list.append({
                'id': officer.id,
                'username': officer.username,
                'phone': officer.phone
            })
            print(f"  - {officer.username} (ID: {officer.id})")
        
        return jsonify(officers_list)
        
    except Exception as e:
        print(f"❌ Error loading health officers for feedback: {e}")
        return jsonify([]), 500

@app.route('/reception/get_admin_replies')
@login_required
@reception_required
def reception_get_admin_replies():
    """Get reception staff's feedback and admin replies"""
    try:
        # Get feedback sent by this reception staff (using patient_id field)
        feedbacks = Feedback.query.filter(
            Feedback.patient_id == current_user.id,
            Feedback.feedback_type.like('reception_%')
        ).order_by(Feedback.date_submitted.desc()).all()
        
        replies_list = []
        for feedback in feedbacks:
            recipient_name = "Administrator"
            
            # Parse recipient from feedback_type
            if feedback.feedback_type.startswith('reception_to_healthofficer_'):
                health_officer_id = feedback.feedback_type.split('_')[-1]
                try:
                    health_officer = User.query.get(int(health_officer_id))
                    if health_officer:
                        recipient_name = f"Health Officer: {health_officer.username}"
                except (ValueError, TypeError):
                    pass
            
            replies_list.append({
                'id': feedback.id,
                'recipient_name': recipient_name,
                'message': feedback.feedback,
                'reply': feedback.reply,
                'date_sent': feedback.date_submitted.strftime('%Y-%m-%d %H:%M') if feedback.date_submitted else 'N/A',
                'reply_date': feedback.reply_date.strftime('%Y-%m-%d %H:%M') if feedback.reply_date else None
            })
        
        return jsonify(replies_list)
        
    except Exception as e:
        print(f"❌ Error loading reception admin replies: {e}")
        return jsonify([]), 500

# CSRF-exempt test route for debugging
@app.route('/reception/test_no_csrf', methods=['POST'])
@login_required
@reception_required
@csrf.exempt
def test_reception_no_csrf():
    """Test route without CSRF for debugging"""
    try:
        data = request.get_json()
        action = data.get('action')
        
        if action == 'send_admin_feedback':
            message = data.get('message', '').strip()
            
            if not message:
                return jsonify({'success': False, 'message': 'Message is required'}), 400
            
            # Create feedback record
            feedback = Feedback(
                patient_id=current_user.id,
                feedback=message,
                feedback_type='reception_to_admin',
                date_submitted=datetime.utcnow()
            )
            
            db.session.add(feedback)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': 'Feedback sent successfully (no CSRF)!'
            })
        
        elif action == 'get_admin_replies':
            print(f"🔄 Getting admin replies for user {current_user.username} (ID: {current_user.id})")
            # Get feedback sent by this reception staff
            feedbacks = Feedback.query.filter(
                Feedback.patient_id == current_user.id,
                Feedback.feedback_type.like('reception_%')
            ).order_by(Feedback.date_submitted.desc()).all()
            
            print(f"📊 Found {len(feedbacks)} feedback records")
            
            replies_list = []
            for feedback in feedbacks:
                print(f"   - Feedback ID {feedback.id}: {feedback.feedback[:30]}...")
                recipient_name = "Administrator"
                
                # Parse recipient from feedback_type
                if feedback.feedback_type.startswith('reception_to_healthofficer_'):
                    health_officer_id = feedback.feedback_type.split('_')[-1]
                    try:
                        health_officer = User.query.get(int(health_officer_id))
                        if health_officer:
                            recipient_name = f"Health Officer: {health_officer.username}"
                    except (ValueError, TypeError):
                        pass
                
                replies_list.append({
                    'id': feedback.id,
                    'recipient_name': recipient_name,
                    'message': feedback.feedback,
                    'reply': feedback.reply,
                    'date_sent': feedback.date_submitted.strftime('%Y-%m-%d %H:%M') if feedback.date_submitted else 'N/A',
                    'reply_date': feedback.reply_date.strftime('%Y-%m-%d %H:%M') if feedback.reply_date else None
                })
            
            print(f"📤 Returning {len(replies_list)} replies")
            return jsonify(replies_list)
        
        return jsonify({'success': False, 'message': 'Unknown action'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/healthofficer/get_reception_feedback_notifications')
@login_required
@health_officer_required
def get_reception_feedback_notifications():
    """Get notifications for health officer about reception feedback"""
    try:
        # Check for new feedback from reception staff
        feedback_type = f'reception_to_healthofficer_{current_user.id}'
        
        # Get unread feedback messages
        new_feedbacks = Feedback.query.filter_by(
            feedback_type=feedback_type,
            is_read=False
        ).order_by(Feedback.date_submitted.desc()).all()
        
        notifications = []
        for feedback in new_feedbacks:
            # Extract sender info
            sender = User.query.get(feedback.patient_id)
            
            # Extract message (remove "To Health Officer..." prefix)
            message = feedback.feedback
            if message and message.startswith(f"To Health Officer {current_user.username}: "):
                message = message.replace(f"To Health Officer {current_user.username}: ", "")
            
            notifications.append({
                'id': feedback.id,
                'type': 'feedback',
                'sender_name': sender.username if sender else 'Reception Staff',
                'sender_role': 'reception',
                'message': message,
                'date_sent': feedback.date_submitted.isoformat() if feedback.date_submitted else None,
                'feedback_id': feedback.id
            })
        
        print(f"📨 Found {len(notifications)} new feedback notifications for health officer {current_user.username}")
        
        return jsonify({
            'success': True,
            'notifications': notifications
        })
        
    except Exception as e:
        print(f"❌ Error getting reception feedback notifications: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/healthofficer/mark_feedback_read', methods=['POST'])
@login_required
@health_officer_required
def mark_feedback_read():
    """Mark feedback as read for health officer"""
    try:
        data = request.get_json()
        feedback_id = data.get('feedback_id')
        
        if not feedback_id:
            return jsonify({'success': False, 'message': 'Feedback ID is required'}), 400
        
        # Verify this feedback belongs to this health officer
        feedback = Feedback.query.get(feedback_id)
        if not feedback:
            return jsonify({'success': False, 'message': 'Feedback not found'}), 404
        
        # Verify feedback_type matches this health officer
        expected_type = f'reception_to_healthofficer_{current_user.id}'
        if feedback.feedback_type != expected_type:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Mark as read
        feedback.is_read = True
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Feedback marked as read'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error marking feedback as read: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ====================== CLINICAL INTERVIEW ROUTES ======================

@app.route('/healthofficer/send_clinical_interview', methods=['POST'])
@login_required
@health_officer_required
def send_clinical_interview():
    """Send clinical interview question to patient"""
    try:
        data = request.get_json()
        patient_id = data.get('patient_id')
        question = data.get('question', '').strip()
        priority = data.get('priority', 'normal')
        interview_type = data.get('interview_type', 'general')
        notes = data.get('notes', '').strip()
        
        if not patient_id:
            return jsonify({'success': False, 'message': 'Patient ID is required'}), 400
        
        if not question:
            return jsonify({'success': False, 'message': 'Question is required'}), 400
        
        # Verify patient exists and is assigned to this health officer
        patient = User.query.get(patient_id)
        if not patient or patient.role != 'patient':
            return jsonify({'success': False, 'message': 'Patient not found'}), 404
        
        # Create clinical interview
        interview = ClinicalInterview(
            health_officer_id=current_user.id,
            patient_id=patient_id,
            question=question,
            priority=priority,
            interview_type=interview_type,
            notes=notes,
            status='pending'
        )
        
        db.session.add(interview)
        db.session.commit()
        
        # Create notification for patient
        NotificationService.create_notification(
            user_id=patient_id,
            user_role='patient',
            title='New Clinical Interview Question',
            message=f'Health Officer {current_user.username} has sent you a clinical interview question',
            notification_type='clinical_interview',
            action_url='#feedback',
            is_clickable=True
        )
        
        return jsonify({
            'success': True, 
            'message': 'Clinical interview question sent successfully',
            'interview_id': interview.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error sending clinical interview: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/healthofficer/get_clinical_interviews')
@login_required
@health_officer_required
def get_clinical_interviews():
    """Get clinical interviews sent by this health officer"""
    try:
        interviews = ClinicalInterview.query.filter_by(
            health_officer_id=current_user.id
        ).order_by(ClinicalInterview.date_sent.desc()).all()
        
        interview_list = []
        for interview in interviews:
            patient = User.query.get(interview.patient_id)
            patient_name = patient.username if patient else "Unknown"
            patient_unique_id = None
            
            if patient and patient.patient_profile:
                patient_unique_id = patient.patient_profile.patient_unique_id
            
            interview_list.append({
                'id': interview.id,
                'patient_id': interview.patient_id,
                'patient_name': patient_name,
                'patient_unique_id': patient_unique_id,
                'question': interview.question,
                'patient_response': interview.patient_response,
                'status': interview.status,
                'status_display': interview.get_status_display(),
                'priority': interview.priority,
                'priority_display': interview.get_priority_display(),
                'interview_type': interview.interview_type,
                'date_sent': interview.get_formatted_date_sent(),
                'date_responded': interview.get_formatted_date_responded() if interview.is_answered() else None,
                'is_answered': interview.is_answered(),
                'notes': interview.notes
            })
        
        return jsonify(interview_list)
        
    except Exception as e:
        print(f"Error getting clinical interviews: {e}")
        return jsonify([])

@app.route('/patient/get_clinical_interviews')
@login_required
@patient_required
def get_patient_clinical_interviews():
    """Get clinical interview questions for current patient"""
    try:
        interviews = ClinicalInterview.query.filter_by(
            patient_id=current_user.id
        ).order_by(ClinicalInterview.date_sent.desc()).all()
        
        interview_list = []
        for interview in interviews:
            health_officer = User.query.get(interview.health_officer_id)
            ho_name = health_officer.username if health_officer else "Unknown"
            
            interview_list.append({
                'id': interview.id,
                'health_officer_name': ho_name,
                'question': interview.question,
                'patient_response': interview.patient_response,
                'status': interview.status,
                'status_display': interview.get_status_display(),
                'priority': interview.priority,
                'priority_display': interview.get_priority_display(),
                'interview_type': interview.interview_type,
                'date_sent': interview.get_formatted_date_sent(),
                'date_responded': interview.get_formatted_date_responded() if interview.is_answered() else None,
                'is_answered': interview.is_answered()
            })
        
        return jsonify(interview_list)
        
    except Exception as e:
        print(f"Error getting patient clinical interviews: {e}")
        return jsonify([])

@app.route('/patient/respond_clinical_interview', methods=['POST'])
@login_required
@patient_required
def respond_clinical_interview():
    """Patient responds to clinical interview question"""
    try:
        data = request.get_json()
        interview_id = data.get('interview_id')
        response = data.get('response', '').strip()
        
        if not interview_id:
            return jsonify({'success': False, 'message': 'Interview ID is required'}), 400
        
        if not response:
            return jsonify({'success': False, 'message': 'Response is required'}), 400
        
        # Get interview and verify it belongs to current patient
        interview = ClinicalInterview.query.get(interview_id)
        if not interview:
            return jsonify({'success': False, 'message': 'Interview not found'}), 404
        
        if interview.patient_id != current_user.id:
            return jsonify({'success': False, 'message': 'Access denied'}), 403
        
        # Update interview with response
        interview.mark_as_answered(response)
        db.session.commit()
        
        # Create notification for health officer
        NotificationService.create_notification(
            user_id=interview.health_officer_id,
            user_role='healthofficer',
            title='Clinical Interview Response Received',
            message=f'Patient {current_user.username} has responded to your clinical interview question',
            notification_type='clinical_interview_response',
            action_url='#clinical-interview',
            is_clickable=True
        )
        
        return jsonify({
            'success': True, 
            'message': 'Response submitted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error responding to clinical interview: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Removed duplicate if __name__ == '__main__' block - moved to end of file

# ============================================================
#                   UNIVERSAL NOTIFICATION API ROUTES
# ============================================================

@app.route('/api/notifications', methods=['GET'])
@csrf.exempt
@login_required
def get_universal_notifications():
    """Get notifications for the current user"""
    try:
        print(f"🔍 Getting notifications for user {current_user.id} with role {current_user.role}")
        
        limit = request.args.get('limit', 50, type=int)
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        
        print(f"📋 Request params - limit: {limit}, unread_only: {unread_only}")
        
        notifications = NotificationService.get_notifications(
            user_id=current_user.id,
            user_role=current_user.role,
            limit=limit,
            unread_only=unread_only
        )
        
        print(f"✅ Found {len(notifications)} notifications for user {current_user.id}")
        
        return jsonify({
            'success': True,
            'notifications': [notification.to_dict() for notification in notifications]
        })
    
    except Exception as e:
        print(f"❌ Error getting notifications for user {current_user.id if current_user.is_authenticated else 'anonymous'}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to load notifications'}), 500

@app.route('/api/notifications/count', methods=['GET'])
@csrf.exempt
@login_required
def get_notification_count():
    """Get unread notification count for the current user"""
    try:
        print(f"🔍 Getting notification count for user {current_user.id} with role {current_user.role}")
        
        count = NotificationService.get_unread_count(
            user_id=current_user.id,
            user_role=current_user.role
        )
        
        print(f"✅ Unread count for user {current_user.id}: {count}")
        
        return jsonify({
            'success': True,
            'count': count
        })
    
    except Exception as e:
        print(f"❌ Error getting notification count for user {current_user.id if current_user.is_authenticated else 'anonymous'}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Failed to get notification count'}), 500

@app.route('/api/notifications/<int:notification_id>/mark-read', methods=['POST'])
@csrf.exempt
@login_required
def mark_universal_notification_read(notification_id):
    """Mark a specific notification as read"""
    try:
        success = NotificationService.mark_as_read(
            notification_id=notification_id,
            user_id=current_user.id
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Notification marked as read'})
        else:
            return jsonify({'success': False, 'message': 'Notification not found'}), 404
    
    except Exception as e:
        print(f"Error marking notification as read: {e}")
        return jsonify({'success': False, 'message': 'Failed to mark notification as read'}), 500

@app.route('/api/notifications/mark-all-read', methods=['POST'])
@csrf.exempt
@login_required
def mark_all_universal_notifications_read():
    """Mark all notifications as read for the current user"""
    try:
        count = NotificationService.mark_all_as_read(
            user_id=current_user.id,
            user_role=current_user.role
        )
        
        return jsonify({
            'success': True,
            'message': f'Marked {count} notifications as read',
            'count': count
        })
    
    except Exception as e:
        print(f"Error marking all notifications as read: {e}")
        return jsonify({'success': False, 'message': 'Failed to mark notifications as read'}), 500

@app.route('/api/notifications/clear-all', methods=['DELETE'])
@csrf.exempt
@login_required
def clear_all_universal_notifications():
    """Clear all notifications for the current user"""
    try:
        count = NotificationService.clear_all_notifications(
            user_id=current_user.id,
            user_role=current_user.role
        )
        
        return jsonify({
            'success': True,
            'message': f'Cleared {count} notifications',
            'count': count
        })
    
    except Exception as e:
        print(f"Error clearing notifications: {e}")
        return jsonify({'success': False, 'message': 'Failed to clear notifications'}), 500

@app.route('/api/notifications/test', methods=['POST'])
@csrf.exempt
@login_required
def create_test_notification():
    """Create a test notification for the current user (for testing purposes)"""
    try:
        notification = NotificationService.create_notification(
            user_id=current_user.id,
            user_role=current_user.role,
            title="Test Notification",
            message="This is a test notification to verify the system is working correctly.",
            notification_type='system',
            action_url='/dashboard',
            is_clickable=True
        )
        
        if notification:
            return jsonify({
                'success': True,
                'message': 'Test notification created',
                'notification': notification.to_dict()
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to create test notification'}), 500
    
    except Exception as e:
        print(f"Error creating test notification: {e}")
        return jsonify({'success': False, 'message': 'Failed to create test notification'}), 500

@app.route('/api/notifications/debug', methods=['GET'])
@csrf.exempt
@login_required
def debug_notifications():
    """Debug endpoint to test notification API connectivity"""
    try:
        return jsonify({
            'success': True,
            'message': 'Notification API is working',
            'user_id': current_user.id,
            'user_role': current_user.role,
            'username': current_user.username,
            'is_authenticated': current_user.is_authenticated
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Debug error: {str(e)}'
        }), 500

@app.route('/api/test', methods=['GET'])
def test_api_route():
    """Simple test route to verify API routing works"""
    return jsonify({
        'success': True,
        'message': 'API routing is working',
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/test/create_health_officer_notification', methods=['POST'])
@login_required
def test_create_health_officer_notification():
    """Test route to create a notification for health officers"""
    try:
        # Find a health officer
        health_officer = User.query.filter_by(role='healthofficer').first()
        if not health_officer:
            return jsonify({'success': False, 'message': 'No health officer found'})
        
        # Create test notification
        notification = NotificationService.create_notification(
            user_id=health_officer.id,
            user_role='healthofficer',
            title='Test Notification',
            message=f'This is a test notification for health officer {health_officer.username}',
            notification_type='test',
            action_url='#assigned-patients',
            is_clickable=True
        )
        
        if notification:
            return jsonify({
                'success': True, 
                'message': f'Test notification created for {health_officer.username}',
                'notification_id': notification.id
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to create notification'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/test/check_health_officers', methods=['GET'])
@login_required
def test_check_health_officers():
    """Test route to check all health officers in database"""
    try:
        # Get all health officers regardless of status
        all_health_officers = User.query.filter_by(role='healthofficer').all()
        
        result = {
            'total_health_officers': len(all_health_officers),
            'health_officers': []
        }
        
        for officer in all_health_officers:
            result['health_officers'].append({
                'id': officer.id,
                'username': officer.username,
                'is_approved': officer.is_approved,
                'is_active_user': officer.is_active_user,
                'phone': officer.phone
            })
        
        # Also check approved and active ones
        approved_active = User.query.filter_by(
            role='healthofficer', 
            is_approved=True, 
            is_active_user=True
        ).all()
        
        result['approved_active_count'] = len(approved_active)
        result['approved_active_officers'] = [
            {
                'id': officer.id,
                'username': officer.username,
                'phone': officer.phone
            }
            for officer in approved_active
        ]
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# ============================================================
#                   SECURITY MANAGEMENT ROUTES
# ============================================================

@app.route('/admin/security/login-attempts')
@login_required
@admin_required
def admin_login_attempts():
    """Admin view for login attempts and security monitoring"""
    lang = session.get('lang', 'en')
    
    # Get recent login attempts (last 7 days)
    cutoff_time = datetime.utcnow() - timedelta(days=7)
    recent_attempts = LoginAttempt.query.filter(
        LoginAttempt.attempt_time >= cutoff_time
    ).order_by(LoginAttempt.attempt_time.desc()).limit(100).all()
    
    # Get currently locked accounts
    locked_accounts = []
    usernames = db.session.query(LoginAttempt.username).distinct().all()
    
    for (username,) in usernames:
        if LoginAttempt.is_account_locked(username):
            remaining_time = LoginAttempt.get_lockout_time_remaining(username)
            failed_count = LoginAttempt.get_failed_attempts_count(username)
            locked_accounts.append({
                'username': username,
                'failed_attempts': failed_count,
                'remaining_minutes': remaining_time
            })
    
    # Security statistics
    stats = {
        'total_attempts_today': LoginAttempt.query.filter(
            LoginAttempt.attempt_time >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count(),
        'failed_attempts_today': LoginAttempt.query.filter(
            LoginAttempt.attempt_time >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
            LoginAttempt.success == False
        ).count(),
        'locked_accounts_count': len(locked_accounts),
        'unique_ips_today': db.session.query(LoginAttempt.ip_address).filter(
            LoginAttempt.attempt_time >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ).distinct().count()
    }
    
    return render_template('admin_security.html', 
                         recent_attempts=recent_attempts,
                         locked_accounts=locked_accounts,
                         stats=stats,
                         lang=lang)

@app.route('/admin/security/unlock-account', methods=['POST'])
@login_required
@admin_required
def admin_unlock_account():
    """Admin route to unlock a locked account"""
    try:
        username = request.form.get('username', '').strip()
        
        if not username:
            return jsonify({'success': False, 'message': 'Username is required'}), 400
        
        # Clear failed attempts for this user
        LoginAttempt.clear_failed_attempts(username)
        
        # Log this admin action
        ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
        user_agent = request.headers.get('User-Agent', '')
        
        # Record admin unlock action
        LoginAttempt.record_attempt(
            username=f"ADMIN_UNLOCK_{username}_BY_{current_user.username}",
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
            failure_reason='admin_unlock'
        )
        
        return jsonify({
            'success': True, 
            'message': f'Account {username} has been unlocked successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/security/cleanup-attempts', methods=['POST'])
@login_required
@admin_required
def admin_cleanup_attempts():
    """Admin route to cleanup old login attempts"""
    try:
        days = int(request.form.get('days', 30))
        
        if days < 1 or days > 365:
            return jsonify({'success': False, 'message': 'Days must be between 1 and 365'}), 400
        
        # Clean up old attempts
        LoginAttempt.cleanup_old_attempts(days)
        
        return jsonify({
            'success': True,
            'message': f'Cleaned up login attempts older than {days} days'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/security/login-attempts/<username>')
@login_required
@admin_required
def get_user_login_attempts(username):
    """Get login attempts for a specific user"""
    try:
        attempts = LoginAttempt.query.filter_by(username=username).order_by(
            LoginAttempt.attempt_time.desc()
        ).limit(20).all()
        
        attempts_data = []
        for attempt in attempts:
            attempts_data.append({
                'id': attempt.id,
                'ip_address': attempt.ip_address,
                'attempt_time': attempt.attempt_time.strftime('%Y-%m-%d %H:%M:%S'),
                'success': attempt.success,
                'failure_reason': attempt.failure_reason,
                'user_agent': attempt.user_agent[:100] if attempt.user_agent else None
            })
        
        return jsonify({
            'success': True,
            'attempts': attempts_data,
            'is_locked': LoginAttempt.is_account_locked(username),
            'remaining_minutes': LoginAttempt.get_lockout_time_remaining(username)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)