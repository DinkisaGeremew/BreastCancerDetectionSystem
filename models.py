from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime, timedelta
import uuid
from enum import Enum

db = SQLAlchemy()
bcrypt = Bcrypt()

# ============================================================
#                       ENUMS FOR TYPE SAFETY
# ============================================================
class UserRole(str, Enum):
    PATIENT = 'patient'
    DOCTOR = 'doctor'
    XRAY_SPECIALIST = 'xrayspecialist'
    ADMIN = 'admin'
    RECEPTION = 'reception'

class PredictionStatus(str, Enum):
    PENDING = 'pending'
    AI_ANALYZED = 'ai_analyzed'
    DOCTOR_REVIEWED = 'doctor_reviewed'
    COMPLETED = 'completed'

class AppointmentStatus(str, Enum):
    SCHEDULED = 'scheduled'
    CONFIRMED = 'confirmed'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'

# ============================================================
#                   MIXIN FOR COMMON USER FIELDS
# ============================================================
class UserMixin_Base:
    """Mixin for common user authentication fields"""
    
    def set_password(self, password: str):
        """Hashes and sets the user's password."""
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters long")
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Verifies a plaintext password against the hashed one."""
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def password(self):
        raise AttributeError("Password is write-only. Use set_password() instead.")
    
    def update_last_login(self):
        """Update last login timestamp"""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.id)
    
    @property
    def is_active(self):
        """Required by Flask-Login"""
        return self.is_active_user
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False


# ============================================================
#                   ADMIN MODEL (PROFILE TABLE)
# ============================================================
class Admin(db.Model):
    """Admin profile - references user table"""
    __tablename__ = 'admin'
    
    # Primary key and foreign key to user
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    
    # Admin-specific fields
    email = db.Column(db.String(120), nullable=True, index=True)
    admin_level = db.Column(db.String(50), default='standard')  # standard, super_admin
    department = db.Column(db.String(100), nullable=True)
    permissions = db.Column(db.Text, nullable=True)  # JSON string of permissions
    can_approve_users = db.Column(db.Boolean, default=True)
    can_manage_system = db.Column(db.Boolean, default=True)
    can_view_reports = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Note: Relationships are handled through the User model
    
    # Properties that delegate to user
    @property
    def username(self):
        return self.user.username if self.user else None
    
    @property
    def phone(self):
        return self.user.phone if self.user else None
    
    @property
    def is_approved(self):
        return self.user.is_approved if self.user else False
    
    @property
    def is_active_user(self):
        return self.user.is_active_user if self.user else False
    
    @property
    def date_created(self):
        return self.user.date_created if self.user else None
    
    @property
    def last_login(self):
        return self.user.last_login if self.user else None
    
    @property
    def role(self):
        """Return role for compatibility"""
        return 'admin'
    
    def has_permission(self, permission):
        """Check if admin has specific permission"""
        if self.admin_level == 'super_admin':
            return True
        return True
    
    def can_login(self):
        """Check if admin can log in"""
        return self.user and self.user.can_login()
    
    def get_unread_notification_count(self):
        """Get count of unread notifications"""
        return Notification.query.filter_by(admin_id=self.user_id, is_read=False).count()
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.user_id)
    
    @property
    def is_active(self):
        """Required by Flask-Login"""
        return self.user.is_active_user if self.user else False
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False
    
    def __repr__(self):
        return f"<Admin {self.username} | Level: {self.admin_level}>"


# ============================================================
#                   BASE USER MODEL (CURRENT STRUCTURE)
# ============================================================
class User(db.Model, UserMixin_Base):
    """Base user table - current database structure"""
    __tablename__ = 'user'
    
    # Authentication fields
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    is_approved = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    date_created = db.Column(db.DateTime, server_default=db.func.now())
    last_login = db.Column(db.DateTime, nullable=True)
    profile_picture = db.Column(db.String(255), nullable=True, default='default_avatar.png')
    
    # Relationships to role-specific tables (fixed foreign key specifications)
    admin_profile = db.relationship('Admin', backref='user', uselist=False, 
                                   primaryjoin='User.id == Admin.user_id')
    doctor_profile = db.relationship('Doctor', backref='user', uselist=False,
                                    primaryjoin='User.id == Doctor.user_id')
    patient_profile = db.relationship('Patient', backref='user', uselist=False,
                                     primaryjoin='User.id == Patient.user_id')
    xray_specialist_profile = db.relationship('XraySpecialist', backref='user', uselist=False,
                                             primaryjoin='User.id == XraySpecialist.user_id')
    reception_profile = db.relationship('Reception', backref='user', uselist=False,
                                       primaryjoin='User.id == Reception.user_id')
    
    @property
    def is_admin(self):
        return self.role == 'admin'
    
    @property
    def is_doctor(self):
        return self.role == 'doctor'
    
    @property
    def is_patient(self):
        return self.role == 'patient'
    
    @property
    def is_xray_specialist(self):
        return self.role == 'xrayspecialist'
    
    @property
    def is_reception(self):
        return self.role == 'reception'
    
    def can_login(self):
        """Check if user can log in based on role"""
        if self.role == 'admin':
            return self.is_active_user
        elif self.role in ['doctor', 'xrayspecialist']:
            return self.is_active_user and self.is_approved
        else:  # patient
            return self.is_active_user
    
    def __repr__(self):
        return f"<User {self.username} | {self.role}>"


# ============================================================
#                   DOCTOR MODEL (PROFILE TABLE)
# ============================================================
class Doctor(db.Model):
    """Doctor profile - references user table"""
    __tablename__ = 'doctor'
    
    # Primary key and foreign key to user
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    
    # Doctor-specific fields
    email = db.Column(db.String(120), nullable=True, index=True)
    specialization = db.Column(db.String(100), nullable=True)
    license_number = db.Column(db.String(100), unique=True, nullable=True, index=True)
    years_of_experience = db.Column(db.Integer, nullable=True)
    education = db.Column(db.Text, nullable=True)
    hospital_affiliation = db.Column(db.String(200), nullable=True)
    consultation_fee = db.Column(db.Float, nullable=True)
    available_days = db.Column(db.String(200), nullable=True)  # JSON string
    available_hours = db.Column(db.String(200), nullable=True)  # JSON string
    bio = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, default=0.0)
    total_patients_treated = db.Column(db.Integer, default=0)
    total_validations = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Note: Relationships are handled through the User model
    
    # Properties that delegate to user
    @property
    def username(self):
        return self.user.username if self.user else None
    
    @property
    def phone(self):
        return self.user.phone if self.user else None
    
    @property
    def is_approved(self):
        return self.user.is_approved if self.user else False
    
    @property
    def is_active_user(self):
        return self.user.is_active_user if self.user else False
    
    @property
    def date_created(self):
        return self.user.date_created if self.user else None
    
    @property
    def last_login(self):
        return self.user.last_login if self.user else None
    
    @property
    def role(self):
        """Return role for compatibility"""
        return 'doctor'
    
    def can_login(self):
        """Check if doctor can log in"""
        return self.user and self.user.can_login()
    
    def update_statistics(self):
        """Update doctor statistics"""
        from sqlalchemy import func
        self.total_validations = Prediction.query.filter_by(doctor_id=self.user_id).count()
        self.total_patients_treated = db.session.query(func.count(func.distinct(Prediction.patient_id))).filter(
            Prediction.doctor_id == self.user_id
        ).scalar()
        db.session.commit()
    
    def get_unread_notification_count(self):
        """Get count of unread notifications"""
        return DoctorNotification.query.filter_by(doctor_id=self.user_id, is_read=False).count()
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.user_id)
    
    @property
    def is_active(self):
        """Required by Flask-Login"""
        return self.user.is_active_user if self.user else False
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False
    
    def __repr__(self):
        return f"<Doctor {self.username} | {self.specialization}>"


# ============================================================
#                   PATIENT MODEL (PROFILE TABLE)
# ============================================================
class Patient(db.Model):
    """Patient profile - references user table"""
    __tablename__ = 'patient'
    
    # Primary key and foreign key to user
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    
    # Unique patient identifier for medical records
    patient_unique_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    
    # Patient-specific fields
    email = db.Column(db.String(120), nullable=True, index=True)
    age = db.Column(db.Integer, nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    blood_type = db.Column(db.String(10), nullable=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    emergency_contact_name = db.Column(db.String(150), nullable=True)
    emergency_contact_phone = db.Column(db.String(20), nullable=True)
    emergency_contact_relation = db.Column(db.String(50), nullable=True)
    medical_history = db.Column(db.Text, nullable=True)
    allergies = db.Column(db.Text, nullable=True)
    current_medications = db.Column(db.Text, nullable=True)
    family_history = db.Column(db.Text, nullable=True)
    insurance_provider = db.Column(db.String(200), nullable=True)
    insurance_number = db.Column(db.String(100), nullable=True)
    total_predictions = db.Column(db.Integer, default=0)
    total_appointments = db.Column(db.Integer, default=0)
    # Note: X-ray assignments are handled through the appointment table
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Note: Relationships are handled through the User model
    
    # Properties that delegate to user
    @property
    def username(self):
        return self.user.username if self.user else None
    
    @property
    def phone(self):
        return self.user.phone if self.user else None
    
    @property
    def is_approved(self):
        return self.user.is_approved if self.user else False
    
    @property
    def is_active_user(self):
        return self.user.is_active_user if self.user else False
    
    @property
    def date_created(self):
        return self.user.date_created if self.user else None
    
    @property
    def last_login(self):
        return self.user.last_login if self.user else None
    
    @property
    def role(self):
        """Return role for compatibility"""
        return 'patient'
    
    def can_login(self):
        """Check if patient can log in"""
        return self.user and self.user.can_login()
    
    def get_age(self):
        """Calculate patient age"""
        if self.date_of_birth:
            today = datetime.today().date()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None
    
    def update_statistics(self):
        """Update patient statistics"""
        self.total_predictions = Prediction.query.filter_by(patient_id=self.user_id).count()
        self.total_appointments = Appointment.query.filter_by(patient_id=self.user_id).count()
        db.session.commit()
    
    def get_user_statistics(self):
        """Get patient statistics"""
        return {
            'total_predictions': Prediction.query.filter_by(patient_id=self.user_id).count(),
            'pending_predictions': Prediction.query.filter_by(
                patient_id=self.user_id, 
                doctor_validation=None
            ).count()
        }
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.user_id)
    
    @property
    def is_active(self):
        """Required by Flask-Login"""
        return self.user.is_active_user if self.user else False
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False
    
    def __repr__(self):
        return f"<Patient {self.username} | {self.gender}>"


# ============================================================
#                   XRAY SPECIALIST MODEL (PROFILE TABLE)
# ============================================================
class XraySpecialist(db.Model):
    """X-ray Specialist profile - references user table"""
    __tablename__ = 'xray_specialist'
    
    # Primary key and foreign key to user
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    
    # X-ray Specialist-specific fields
    email = db.Column(db.String(120), nullable=True, index=True)
    certification_number = db.Column(db.String(100), unique=True, nullable=True, index=True)
    certification_date = db.Column(db.Date, nullable=True)
    specialization = db.Column(db.String(100), nullable=True)  # Mammography, General Radiology, etc.
    years_of_experience = db.Column(db.Integer, nullable=True)
    education = db.Column(db.Text, nullable=True)
    hospital_affiliation = db.Column(db.String(200), nullable=True)
    equipment_expertise = db.Column(db.Text, nullable=True)  # Types of X-ray machines
    shift_schedule = db.Column(db.String(200), nullable=True)  # JSON string
    bio = db.Column(db.Text, nullable=True)
    total_xrays_processed = db.Column(db.Integer, default=0)
    total_patients_scanned = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Note: Relationships are handled through the User model
    
    # Properties that delegate to user
    @property
    def username(self):
        return self.user.username if self.user else None
    
    @property
    def phone(self):
        return self.user.phone if self.user else None
    
    @property
    def is_approved(self):
        return self.user.is_approved if self.user else False
    
    @property
    def is_active_user(self):
        return self.user.is_active_user if self.user else False
    
    @property
    def date_created(self):
        return self.user.date_created if self.user else None
    
    @property
    def last_login(self):
        return self.user.last_login if self.user else None
    
    @property
    def role(self):
        """Return role for compatibility"""
        return 'xrayspecialist'
    
    def can_login(self):
        """Check if X-ray specialist can log in"""
        return self.user and self.user.can_login()
    
    def update_statistics(self):
        """Update X-ray specialist statistics"""
        from sqlalchemy import func
        self.total_xrays_processed = Prediction.query.filter_by(sent_by=self.user_id).count()
        self.total_patients_scanned = db.session.query(func.count(func.distinct(Prediction.patient_id))).filter(
            Prediction.sent_by == self.user_id
        ).scalar()
        db.session.commit()
    
    def get_unread_notification_count(self):
        """Get count of unread notifications"""
        return XraySpecialistNotification.query.filter_by(xray_specialist_id=self.user_id, is_read=False).count()
    
    def get_user_statistics(self):
        """Get X-ray specialist statistics"""
        return {
            'xrays_sent': Prediction.query.filter_by(sent_by=self.user_id).count()
        }
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.user_id)
    
    @property
    def is_active(self):
        """Required by Flask-Login"""
        return self.user.is_active_user if self.user else False
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False
    
    def __repr__(self):
        return f"<XraySpecialist {self.username} | {self.specialization}>"


# ============================================================
#                   RECEPTION MODEL (PROFILE TABLE)
# ============================================================
class Reception(db.Model):
    """Reception profile - references user table"""
    __tablename__ = 'reception'
    
    # Primary key and foreign key to user
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    
    # Reception-specific fields
    email = db.Column(db.String(120), nullable=True, index=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=True, index=True)
    department = db.Column(db.String(100), nullable=True, default='Reception')
    shift_schedule = db.Column(db.String(200), nullable=True)  # JSON string for shifts
    years_of_experience = db.Column(db.Integer, nullable=True)
    languages_spoken = db.Column(db.Text, nullable=True)  # JSON string for languages
    can_register_patients = db.Column(db.Boolean, default=True)
    can_schedule_appointments = db.Column(db.Boolean, default=True)
    can_modify_patient_info = db.Column(db.Boolean, default=True)
    total_patients_registered = db.Column(db.Integer, default=0)
    total_appointments_scheduled = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Note: Relationships are handled through the User model
    
    # Properties that delegate to user
    @property
    def username(self):
        return self.user.username if self.user else None
    
    @property
    def phone(self):
        return self.user.phone if self.user else None
    
    @property
    def is_approved(self):
        return self.user.is_approved if self.user else False
    
    @property
    def is_active_user(self):
        return self.user.is_active_user if self.user else False
    
    @property
    def date_created(self):
        return self.user.date_created if self.user else None
    
    @property
    def last_login(self):
        return self.user.last_login if self.user else None
    
    @property
    def role(self):
        """Return role for compatibility"""
        return 'reception'
    
    def can_login(self):
        """Check if reception can log in"""
        return self.user and self.user.can_login()
    
    def update_statistics(self):
        """Update reception statistics"""
        # Count patients registered by this reception
        from sqlalchemy import func
        self.total_patients_registered = Patient.query.join(User).filter(
            User.date_created >= self.created_at
        ).count()  # This is a simplified count, could be enhanced with tracking
        
        # Count appointments scheduled by this reception
        self.total_appointments_scheduled = Appointment.query.filter_by(
            # We'll add created_by field to Appointment model
        ).count()
        
        db.session.commit()
    
    def get_user_statistics(self):
        """Get reception statistics"""
        return {
            'patients_registered': self.total_patients_registered,
            'appointments_scheduled': self.total_appointments_scheduled
        }
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.user_id)
    
    @property
    def is_active(self):
        """Required by Flask-Login"""
        return self.user.is_active_user if self.user else False
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False
    
    def __repr__(self):
        return f"<Reception {self.username} | {self.department}>"


# ============================================================
#                   HEALTH OFFICER MODEL (PROFILE TABLE)
# ============================================================
class HealthOfficer(db.Model):
    """Health Officer profile - references user table"""
    __tablename__ = 'health_officer'
    
    # Primary key and foreign key to user
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True, index=True)
    
    # Health Officer-specific fields
    email = db.Column(db.String(120), nullable=True, index=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=True, index=True)
    department = db.Column(db.String(100), nullable=True, default='Health Services')
    specialization = db.Column(db.String(200), nullable=True)
    years_of_experience = db.Column(db.Integer, nullable=True)
    certification_level = db.Column(db.String(100), nullable=True)
    languages_spoken = db.Column(db.Text, nullable=True)  # JSON string for languages
    can_conduct_screenings = db.Column(db.Boolean, default=True)
    can_provide_health_education = db.Column(db.Boolean, default=True)
    can_assist_doctors = db.Column(db.Boolean, default=True)
    total_screenings_conducted = db.Column(db.Integer, default=0)
    total_patients_assisted = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Properties that delegate to user
    @property
    def username(self):
        return self.user.username if self.user else None
    
    @property
    def phone(self):
        return self.user.phone if self.user else None
    
    @property
    def is_approved(self):
        return self.user.is_approved if self.user else False
    
    @property
    def is_active_user(self):
        return self.user.is_active_user if self.user else False
    
    @property
    def date_created(self):
        return self.user.date_created if self.user else None
    
    @property
    def last_login(self):
        return self.user.last_login if self.user else None
    
    @property
    def role(self):
        """Return role for compatibility"""
        return 'healthofficer'
    
    def can_login(self):
        """Check if health officer can log in"""
        return self.user and self.user.can_login()
    
    def update_statistics(self):
        """Update health officer statistics"""
        # This can be enhanced with actual tracking
        db.session.commit()
    
    def get_user_statistics(self):
        """Get health officer statistics"""
        return {
            'screenings_conducted': self.total_screenings_conducted,
            'patients_assisted': self.total_patients_assisted
        }
    
    def get_id(self):
        """Required by Flask-Login"""
        return str(self.user_id)
    
    @property
    def is_active(self):
        """Required by Flask-Login"""
        return self.user.is_active_user if self.user else False
    
    @property
    def is_authenticated(self):
        """Required by Flask-Login"""
        return True
    
    @property
    def is_anonymous(self):
        """Required by Flask-Login"""
        return False
    
    def __repr__(self):
        return f"<HealthOfficer {self.username} | {self.department}>"


# ============================================================
#                   CLINICAL INTERVIEW MODEL
# ============================================================
class ClinicalInterview(db.Model):
    """Clinical Interview model for health officer to patient communication"""
    __tablename__ = 'clinical_interview'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Who is involved
    health_officer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    
    # Interview details
    question = db.Column(db.Text, nullable=False)
    patient_response = db.Column(db.Text, nullable=True)
    
    # Status tracking
    status = db.Column(db.String(20), default='pending')  # 'pending', 'answered', 'closed'
    priority = db.Column(db.String(20), default='normal')  # 'low', 'normal', 'high', 'urgent'
    
    # Timestamps
    date_sent = db.Column(db.DateTime, default=datetime.utcnow)
    date_responded = db.Column(db.DateTime, nullable=True)
    
    # Additional fields
    interview_type = db.Column(db.String(50), default='general')  # 'general', 'pre_screening', 'follow_up'
    notes = db.Column(db.Text, nullable=True)  # Health officer's private notes
    
    # Relationships
    health_officer = db.relationship('User', foreign_keys=[health_officer_id], backref='sent_interviews')
    patient = db.relationship('User', foreign_keys=[patient_id], backref='received_interviews')
    
    def is_answered(self):
        """Check if patient has responded"""
        return bool(self.patient_response and self.patient_response.strip())
    
    def get_status_display(self):
        """Get human-readable status"""
        status_map = {
            'pending': 'Awaiting Response',
            'answered': 'Answered',
            'closed': 'Closed'
        }
        return status_map.get(self.status, self.status.title())
    
    def get_priority_display(self):
        """Get human-readable priority"""
        priority_map = {
            'low': 'Low',
            'normal': 'Normal', 
            'high': 'High',
            'urgent': 'Urgent'
        }
        return priority_map.get(self.priority, self.priority.title())
    
    def get_formatted_date_sent(self):
        """Get formatted date sent"""
        return self.date_sent.strftime('%Y-%m-%d %H:%M') if self.date_sent else "N/A"
    
    def get_formatted_date_responded(self):
        """Get formatted date responded"""
        return self.date_responded.strftime('%Y-%m-%d %H:%M') if self.date_responded else "N/A"
    
    def mark_as_answered(self, response):
        """Mark interview as answered with patient response"""
        self.patient_response = response
        self.status = 'answered'
        self.date_responded = datetime.utcnow()
    
    def __repr__(self):
        return f"<ClinicalInterview {self.id} | HO: {self.health_officer.username if self.health_officer else 'N/A'} -> Patient: {self.patient.username if self.patient else 'N/A'}>"


# ============================================================
#                       PREDICTION MODEL
# ============================================================
class Prediction(db.Model):
    __tablename__ = 'prediction'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    sent_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)

    # Patient identification fields
    patient_unique_id = db.Column(db.String(20), nullable=True, index=True)  # For X-ray specialist workflow
    patient_name_provided = db.Column(db.String(150), nullable=True)  # Name provided by X-ray specialist
    
    image_filename = db.Column(db.String(255), nullable=True)
    ai_result = db.Column(db.String(50), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)
    doctor_validation = db.Column(db.String(50), nullable=True)  # 'malignant', 'benign', etc.
    doctor_notes = db.Column(db.Text, nullable=True)
    doctor_recommendation = db.Column(db.Text, nullable=True)
    sent_by_patient_only = db.Column(db.Boolean, default=False)
    sent_by_xray_specialist = db.Column(db.Boolean, default=False)
    date_uploaded = db.Column(db.DateTime, server_default=db.func.now())
    last_updated = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    # Relationships to User table
    patient = db.relationship('User', foreign_keys=[patient_id], backref='patient_predictions')
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref='doctor_predictions')
    sent_by_user = db.relationship('User', foreign_keys=[sent_by], backref='sent_predictions')
    
    # Relationship to Feedbacks
    feedbacks = db.relationship(
        'Feedback',
        backref='prediction',
        lazy=True,
        cascade='all, delete-orphan'
    )

    # -------------------- Utility Methods --------------------
    def get_validation_status(self):
        """Get the validation status"""
        if self.doctor_validation:
            return self.doctor_validation.capitalize()
        elif self.ai_result:
            return f"AI: {self.ai_result.capitalize()}"
        else:
            return "Pending"
    
    def has_doctor_feedback(self):
        """Check if doctor has provided feedback"""
        return bool(self.doctor_validation or self.doctor_notes or self.doctor_recommendation)
    
    def is_pending(self):
        """Check if prediction is pending doctor review"""
        return not self.doctor_validation and not self.ai_result
    
    def get_file_url(self):
        """Get the file URL for the uploaded image"""
        if self.image_filename:
            return f"/uploads/{self.image_filename}"
        return None

    def get_patient_name(self):
        """Get patient name"""
        return self.patient.username if self.patient else "Unknown"

    def get_doctor_name(self):
        """Get doctor name if assigned"""
        return self.doctor.username if self.doctor else "Not assigned"

    def create_doctor_notification(self):
        """Create notification for doctor when patient sends X-ray"""
        if self.doctor_id and self.sent_by_patient_only and self.patient:
            notification = DoctorNotification(
                doctor_id=self.doctor_id,
                patient_id=self.patient_id,
                patient_name=self.patient.username,
                xray_filename=self.image_filename,
                message=f"Patient {self.patient.username} has sent you a new X-ray for analysis",
                is_read=False
            )
            db.session.add(notification)
            db.session.commit()
            return True
        return False

    def __repr__(self):
        return f"<Prediction {self.id} | Patient {self.patient_id} | AI: {self.ai_result}>"


# ============================================================
#                       FEEDBACK MODEL - UPDATED
# ============================================================
class Feedback(db.Model):
    __tablename__ = 'feedback'

    id = db.Column(db.Integer, primary_key=True)
    
    # Who sent the feedback (can be patient, doctor, xray specialist, or health officer)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    xray_specialist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    health_officer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    
    # Feedback details
    prediction_id = db.Column(db.Integer, db.ForeignKey('prediction.id'), nullable=True, index=True)
    feedback = db.Column(db.Text, nullable=False)
    feedback_type = db.Column(db.String(50), default='general')  # 'general', 'technical', 'medical', 'system'
    
    # Admin reply
    reply = db.Column(db.Text, nullable=True)
    reply_date = db.Column(db.DateTime, nullable=True)
    
    # Doctor reply (for X-ray specialist feedback)
    doctor_reply = db.Column(db.Text, nullable=True)
    
    # Timestamps
    date_submitted = db.Column(db.DateTime, server_default=db.func.now())
    is_read = db.Column(db.Boolean, default=False)
    
    # Relationships
    patient = db.relationship('User', foreign_keys=[patient_id])
    doctor = db.relationship('User', foreign_keys=[doctor_id])
    xray_specialist = db.relationship('User', foreign_keys=[xray_specialist_id])
    health_officer = db.relationship('User', foreign_keys=[health_officer_id])

    # -------------------- Utility Methods --------------------
    def has_reply(self):
        """Check if feedback has an admin reply"""
        return bool(self.reply and self.reply.strip())
    
    def is_from_patient(self):
        """Check if feedback is from a patient"""
        return self.patient_id is not None
    
    def is_from_doctor(self):
        """Check if feedback is from a doctor"""
        return self.doctor_id is not None
    
    def is_from_xray_specialist(self):
        """Check if feedback is from an xray specialist"""
        return self.xray_specialist_id is not None
    
    def is_from_health_officer(self):
        """Check if feedback is from a health officer"""
        return self.health_officer_id is not None
    
    def get_sender_name(self):
        """Get the name of the feedback sender"""
        if self.patient_id and self.patient:
            return self.patient.username
        elif self.doctor_id and self.doctor:
            return f"Dr. {self.doctor.username}"
        elif self.xray_specialist_id and self.xray_specialist:
            return f"X-ray Specialist {self.xray_specialist.username}"
        elif self.health_officer_id and self.health_officer:
            return f"Health Officer {self.health_officer.username}"
        return "Unknown"
    
    def get_sender_role(self):
        """Get the role of the feedback sender"""
        if self.patient_id:
            return "patient"
        elif self.doctor_id:
            return "doctor"
        elif self.xray_specialist_id:
            return "xrayspecialist"
        elif self.health_officer_id:
            return "healthofficer"
        return "unknown"
    
    def get_formatted_date(self):
        """Get formatted date string"""
        return self.date_submitted.strftime('%Y-%m-%d %H:%M') if self.date_submitted else "N/A"
    
    def get_reply_date_formatted(self):
        """Get formatted reply date string"""
        return self.reply_date.strftime('%Y-%m-%d %H:%M') if self.reply_date else "N/A"
    
    def get_feedback_preview(self, length=100):
        """Get a preview of the feedback text"""
        if not self.feedback:
            return ""
        if len(self.feedback) <= length:
            return self.feedback
        return self.feedback[:length] + "..."

    def set_reply(self, reply_text):
        """Set reply and update reply date"""
        self.reply = reply_text
        self.reply_date = datetime.utcnow()
        db.session.commit()
        
        # Create notification for the feedback sender
        self.create_reply_notification()

    def create_admin_notification(self):
        """Create notifications for all admins when feedback is submitted"""
        try:
            # Get all admin users
            admins = Admin.query.all()
            sender_name = self.get_sender_name()
            sender_role = self.get_sender_role()
            
            # Create appropriate title based on sender role
            if sender_role == 'xrayspecialist':
                title = "New X-ray Specialist Feedback Received"
            elif sender_role == 'doctor':
                title = "New Doctor Feedback Received"
            else:
                title = "New Patient Feedback Received"
            
            for admin in admins:
                notification = Notification(
                    admin_id=admin.id,
                    title=title,
                    message=f"{sender_name} submitted feedback: {self.get_feedback_preview(80)}",
                    type='feedback',
                    related_feedback_id=self.id
                )
                db.session.add(notification)
            
            db.session.commit()
            return True
        except Exception as e:
            print(f"Error creating feedback notification: {e}")
            db.session.rollback()
            return False

    def create_reply_notification(self):
        """Create notification for the feedback sender when admin replies"""
        try:
            print(f"🔔 create_reply_notification called for feedback ID {self.id}")
            print(f"   patient_id: {self.patient_id}, doctor_id: {self.doctor_id}, xray_specialist_id: {self.xray_specialist_id}")
            print(f"   feedback_type: {self.feedback_type}")
            
            if self.patient_id and not self.doctor_id:
                # Check if this is reception feedback or patient feedback
                sender = User.query.get(self.patient_id)
                if sender:
                    if self.feedback_type and self.feedback_type.startswith('reception_'):
                        # This is reception staff feedback - create universal notification
                        print(f"📧 Creating notification for reception staff {sender.username}")
                        
                        # Check if notification already exists to prevent duplicates
                        existing_notification = UniversalNotification.query.filter_by(
                            user_id=self.patient_id,
                            user_role='reception',
                            notification_type='admin_reply',
                            message=f"Admin has replied to your feedback: {self.reply[:100] if self.reply else ''}{'...' if self.reply and len(self.reply) > 100 else ''}"
                        ).first()
                        
                        if not existing_notification:
                            universal_notification = UniversalNotification(
                                user_id=self.patient_id,
                                user_role='reception',
                                title="Admin Reply to Your Feedback",
                                message=f"Admin has replied to your feedback: {self.reply[:100] if self.reply else ''}{'...' if self.reply and len(self.reply) > 100 else ''}",
                                notification_type='admin_reply',
                                action_url='#feedback',
                                is_clickable=True
                            )
                            db.session.add(universal_notification)
                            print(f"✅ Created universal notification for reception staff {sender.username}")
                        else:
                            print(f"⚠️ Notification already exists for reception staff {sender.username}, skipping duplicate")
                    else:
                        # Regular patient feedback
                        print(f"📧 Patient {sender.username} received reply to their feedback")
                    
            elif self.doctor_id:
                # Create doctor notification - for doctor-to-admin feedback
                print(f"🔍 Attempting to create doctor notification...")
                doctor = User.query.get(self.doctor_id)
                if doctor:
                    print(f"✅ Found doctor: {doctor.username} (ID: {doctor.id})")
                    
                    # Create legacy doctor notification
                    notification = DoctorNotification(
                        doctor_id=doctor.id,
                        patient_id=None,  # This is admin reply, not patient-related
                        patient_name="Admin",
                        xray_filename="admin_reply",
                        message=f"Admin replied to your feedback: {self.reply[:100] if self.reply else ''}{'...' if self.reply and len(self.reply) > 100 else ''}",
                        is_read=False,
                        notification_type='admin_reply'
                    )
                    db.session.add(notification)
                    print(f"✅ Created legacy notification for doctor {doctor.username} about admin reply")
                    
                    # Also create universal notification for doctor (check for duplicates)
                    existing_universal = UniversalNotification.query.filter_by(
                        user_id=self.doctor_id,
                        user_role='doctor',
                        notification_type='admin_reply',
                        message=f"Admin has replied to your feedback: {self.reply[:100] if self.reply else ''}{'...' if self.reply and len(self.reply) > 100 else ''}"
                    ).first()
                    
                    if not existing_universal:
                        universal_notification = UniversalNotification(
                            user_id=self.doctor_id,
                            user_role='doctor',
                            title="Admin Reply to Your Feedback",
                            message=f"Admin has replied to your feedback: {self.reply[:100] if self.reply else ''}{'...' if self.reply and len(self.reply) > 100 else ''}",
                            notification_type='admin_reply',
                            action_url='#feedback',
                            is_clickable=True
                        )
                        db.session.add(universal_notification)
                        print(f"✅ Created universal notification for doctor {doctor.username} about admin reply")
                    else:
                        print(f"⚠️ Universal notification already exists for doctor {doctor.username}, skipping duplicate")
                else:
                    print(f"❌ Doctor not found with ID: {self.doctor_id}")
                    # Don't commit here - let the parent route handle the commit
            
            elif self.health_officer_id:
                # Create health officer notification for admin reply
                health_officer = User.query.get(self.health_officer_id)
                if health_officer and health_officer.role == 'healthofficer':
                    print(f"📧 Creating notification for health officer {health_officer.username}")
                    
                    # Create universal notification for health officer (check for duplicates)
                    existing_universal = UniversalNotification.query.filter_by(
                        user_id=self.health_officer_id,
                        user_role='healthofficer',
                        notification_type='admin_reply',
                        message=f"Admin has replied to your feedback: {self.reply[:100] if self.reply else ''}{'...' if self.reply and len(self.reply) > 100 else ''}"
                    ).first()
                    
                    if not existing_universal:
                        universal_notification = UniversalNotification(
                            user_id=self.health_officer_id,
                            user_role='healthofficer',
                            title="Admin Reply to Your Feedback",
                            message=f"Admin has replied to your feedback: {self.reply[:100] if self.reply else ''}{'...' if self.reply and len(self.reply) > 100 else ''}",
                            notification_type='admin_reply',
                            action_url='#send-to-admin',  # Navigate to admin communication section
                            is_clickable=True
                        )
                        db.session.add(universal_notification)
                        print(f"✅ Created universal notification for health officer {health_officer.username}")
                    else:
                        print(f"⚠️ Universal notification already exists for health officer {health_officer.username}, skipping duplicate")
                    
            elif self.xray_specialist_id:
                # Create xray specialist notification (legacy)
                xray_specialist_user = User.query.get(self.xray_specialist_id)
                if xray_specialist_user and xray_specialist_user.role == 'xrayspecialist':
                    notification = XraySpecialistNotification(
                        xray_specialist_id=self.xray_specialist_id,
                        patient_id=None,
                        patient_name="System Admin",
                        xray_filename="feedback_reply",
                        message=f"Admin has replied to your feedback: {self.get_feedback_preview(50)}",
                        is_read=False,
                        notification_type='feedback_reply'
                    )
                    db.session.add(notification)
                    print(f"Created legacy notification for X-ray specialist {xray_specialist_user.username}")
                    
                    # Also create universal notification (check for duplicates)
                    existing_universal = UniversalNotification.query.filter_by(
                        user_id=self.xray_specialist_id,
                        user_role='xrayspecialist',
                        notification_type='feedback_reply',
                        message=f"Admin has replied to your feedback: {self.get_feedback_preview(50)}"
                    ).first()
                    
                    if not existing_universal:
                        universal_notification = UniversalNotification(
                            user_id=self.xray_specialist_id,
                            user_role='xrayspecialist',
                            title="Admin Reply",
                            message=f"Admin has replied to your feedback: {self.get_feedback_preview(50)}",
                            notification_type='feedback_reply',
                            action_url='#feedback',
                            is_clickable=True
                        )
                        db.session.add(universal_notification)
                        print(f"Created universal notification for X-ray specialist {xray_specialist_user.username}")
                    else:
                        print(f"⚠️ Universal notification already exists for X-ray specialist {xray_specialist_user.username}, skipping duplicate")
                    # Don't commit here - let the parent route handle the commit
            else:
                print(f"⚠️ No notification created - no valid recipient found")
            
            return True
        except Exception as e:
            print(f"❌ Error creating reply notification: {e}")
            import traceback
            traceback.print_exc()
            return False

    def mark_as_read(self):
        """Mark feedback as read"""
        self.is_read = True
        db.session.commit()

    def to_dict(self):
        """Convert feedback to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'doctor_id': self.doctor_id,
            'xray_specialist_id': self.xray_specialist_id,
            'sender_name': self.get_sender_name(),
            'sender_role': self.get_sender_role(),
            'feedback': self.feedback,
            'feedback_type': self.feedback_type,
            'reply': self.reply,
            'date_submitted': self.date_submitted.isoformat() if self.date_submitted else None,
            'reply_date': self.reply_date.isoformat() if self.reply_date else None,
            'is_read': self.is_read,
            'has_reply': self.has_reply(),
            'formatted_date': self.get_formatted_date(),
            'formatted_reply_date': self.get_reply_date_formatted()
        }

    def __repr__(self):
        if self.patient_id:
            sender_info = f"Patient {self.patient_id}"
        elif self.doctor_id:
            sender_info = f"Doctor {self.doctor_id}"
        elif self.xray_specialist_id:
            sender_info = f"X-ray Specialist {self.xray_specialist_id}"
        else:
            sender_info = "Unknown"
        return f"<Feedback {self.id} | {sender_info} | Type: {self.feedback_type}>"


# ============================================================
#                   DOCTOR NOTIFICATION MODEL
# ============================================================
class DoctorNotification(db.Model):
    __tablename__ = 'doctor_notification'

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)  # Made nullable for admin replies
    patient_name = db.Column(db.String(100), nullable=False)
    xray_filename = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow())
    notification_type = db.Column(db.String(50), default='xray')  # 'xray', 'feedback_reply', 'system'
    
    # Relationships
    patient = db.relationship('User', foreign_keys=[patient_id])

    # -------------------- Utility Methods --------------------
    def get_formatted_time(self):
        """Get formatted time string"""
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        db.session.commit()

    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'doctor_id': self.doctor_id,
            'patient_id': self.patient_id,
            'patient_name': self.patient_name,
            'xray_filename': self.xray_filename,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'notification_type': self.notification_type,
            'formatted_time': self.get_formatted_time()
        }

    def __repr__(self):
        return f"<DoctorNotification {self.id} | Doctor {self.doctor_id} | Patient {self.patient_name} | Type: {self.notification_type}>"


# ============================================================
#               XRAY SPECIALIST NOTIFICATION MODEL
# ============================================================
class XraySpecialistNotification(db.Model):
    __tablename__ = 'xray_specialist_notification'

    id = db.Column(db.Integer, primary_key=True)
    xray_specialist_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    patient_name = db.Column(db.String(100), nullable=False)
    xray_filename = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow())
    notification_type = db.Column(db.String(50), default='xray')  # 'xray', 'feedback_reply', 'system'
    
    # Relationships
    patient = db.relationship('User', foreign_keys=[patient_id])

    # -------------------- Utility Methods --------------------
    def get_formatted_time(self):
        """Get formatted time string"""
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        db.session.commit()

    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'xray_specialist_id': self.xray_specialist_id,
            'patient_id': self.patient_id,
            'patient_name': self.patient_name,
            'xray_filename': self.xray_filename,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'notification_type': self.notification_type,
            'formatted_time': self.get_formatted_time()
        }

    def __repr__(self):
        return f"<XraySpecialistNotification {self.id} | X-ray Specialist {self.xray_specialist_id} | Patient {self.patient_name} | Type: {self.notification_type}>"


# ============================================================
#                   ADMIN NOTIFICATION MODEL
# ============================================================
class Notification(db.Model):
    __tablename__ = 'notification'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='general')  # 'feedback', 'user_approval', 'system'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow())
    
    # Additional fields for specific notification types
    related_user_id = db.Column(db.Integer, nullable=True)  # Generic ID, no FK since user could be any role
    related_feedback_id = db.Column(db.Integer, db.ForeignKey('feedback.id'), nullable=True)
    
    # Relationships
    related_feedback = db.relationship('Feedback', foreign_keys=[related_feedback_id])

    # -------------------- Utility Methods --------------------
    def get_formatted_time(self):
        """Get formatted time string"""
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        db.session.commit()
    
    def get_notification_icon(self):
        """Get appropriate icon for notification type"""
        icons = {
            'feedback': 'fas fa-comment-medical',
            'user_approval': 'fas fa-user-check',
            'system': 'fas fa-cog',
            'general': 'fas fa-bell'
        }
        return icons.get(self.type, 'fas fa-bell')

    def to_dict(self):
        """Convert notification to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'icon': self.get_notification_icon(),
            'formatted_time': self.get_formatted_time()
        }

    def __repr__(self):
        return f"<Notification {self.id} | Admin {self.admin_id} | Type: {self.type}>"


# ============================================================
#                   UNIVERSAL NOTIFICATION MODEL
# ============================================================
class UniversalNotification(db.Model):
    __tablename__ = 'universal_notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    user_role = db.Column(db.String(20), nullable=False, index=True)  # reception, healthofficer, xrayspecialist, doctor, admin, patient
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False, default='general')  # feedback, appointment, validation, system, general
    is_read = db.Column(db.Boolean, default=False, index=True)
    is_clickable = db.Column(db.Boolean, default=True)
    action_url = db.Column(db.String(500), nullable=True)  # URL to navigate when clicked
    action_data = db.Column(db.Text, nullable=True)  # JSON string for additional data
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref='universal_notifications')
    
    # Indexes for performance
    __table_args__ = (
        db.Index('idx_user_notifications', 'user_id', 'user_role', 'created_at'),
        db.Index('idx_unread_notifications', 'user_id', 'is_read', 'created_at'),
    )

    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
            db.session.commit()

    def get_formatted_time(self):
        """Get formatted time string"""
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

    def get_notification_icon(self):
        """Get appropriate icon for notification type"""
        icons = {
            'feedback': 'fas fa-comment-medical',
            'appointment': 'fas fa-calendar-check',
            'validation': 'fas fa-check-circle',
            'system': 'fas fa-cog',
            'general': 'fas fa-bell',
            'user_approval': 'fas fa-user-check',
            'xray_result': 'fas fa-x-ray'
        }
        return icons.get(self.notification_type, 'fas fa-bell')

    def to_dict(self):
        """Convert notification to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'notification_type': self.notification_type,
            'is_read': self.is_read,
            'is_clickable': self.is_clickable,
            'action_url': self.action_url,
            'action_data': self.action_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'icon': self.get_notification_icon(),
            'formatted_time': self.get_formatted_time()
        }

    def __repr__(self):
        return f"<UniversalNotification {self.id} | User {self.user_id} ({self.user_role}) | Type: {self.notification_type}>"


# ============================================================
#                   LEGACY MODELS REMOVED
# ============================================================
# PatientProfile and DoctorProfile models have been removed
# All functionality is now in the main Patient and Doctor models


# ============================================================
#                   PATIENT-DOCTOR ASSIGNMENT MODEL
# ============================================================
class PatientDoctorAssignment(db.Model):
    __tablename__ = 'patient_doctor_assignment'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Admin who made the assignment
    
    assigned_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    patient = db.relationship('User', foreign_keys=[patient_id], backref='doctor_assignments')
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref='patient_assignments')
    admin = db.relationship('User', foreign_keys=[assigned_by])
    
    # Unique constraint to prevent duplicate assignments
    __table_args__ = (db.UniqueConstraint('patient_id', 'doctor_id', name='unique_patient_doctor'),)
    
    def __repr__(self):
        return f"<PatientDoctorAssignment {self.id} | Patient {self.patient_id} | Doctor {self.doctor_id}>"


# ============================================================
#                   VERIFICATION CODE MODEL
# ============================================================
class VerificationCode(db.Model):
    """Model for storing email verification codes for password reset"""
    __tablename__ = 'verification_code'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    
    def is_valid(self):
        """Check if the verification code is still valid"""
        return not self.is_used and datetime.utcnow() < self.expires_at
    
    def mark_as_used(self):
        """Mark the verification code as used"""
        self.is_used = True
        db.session.commit()
    
    @staticmethod
    def cleanup_expired():
        """Remove expired verification codes"""
        expired_codes = VerificationCode.query.filter(
            VerificationCode.expires_at < datetime.utcnow()
        ).all()
        for code in expired_codes:
            db.session.delete(code)
        db.session.commit()
        return len(expired_codes)
    
    def __repr__(self):
        return f"<VerificationCode {self.id} | Email: {self.email} | Valid: {self.is_valid()}>"


# ============================================================
#                   APPOINTMENT MODEL (NEW)
# ============================================================
class Appointment(db.Model):
    __tablename__ = 'appointment'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)  # Made nullable for mammography appointments
    prediction_id = db.Column(db.Integer, db.ForeignKey('prediction.id'), nullable=True)
    
    # Reception tracking
    created_by_reception = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)  # Reception who created appointment
    
    appointment_date = db.Column(db.DateTime, nullable=False)
    appointment_time = db.Column(db.Time, nullable=True)  # Specific time slot
    appointment_type = db.Column(db.String(50), default='mammography')  # mammography, consultation, follow-up, emergency
    status = db.Column(db.String(50), default='scheduled')  # scheduled, confirmed, completed, cancelled, no-show
    priority = db.Column(db.String(20), default='normal')  # urgent, high, normal, low
    reason = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Patient information at time of appointment (for historical tracking)
    patient_name_at_appointment = db.Column(db.String(150), nullable=True)
    patient_phone_at_appointment = db.Column(db.String(20), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = db.relationship('User', foreign_keys=[patient_id], backref='patient_appointments')
    doctor = db.relationship('User', foreign_keys=[doctor_id], backref='doctor_appointments')
    reception_creator = db.relationship('User', foreign_keys=[created_by_reception])
    prediction = db.relationship('Prediction', backref='appointments')
    
    def get_formatted_date(self):
        """Get formatted appointment date"""
        if self.appointment_date:
            return self.appointment_date.strftime('%Y-%m-%d')
        return "Not set"
    
    def get_formatted_time(self):
        """Get formatted appointment time"""
        if self.appointment_time:
            return self.appointment_time.strftime('%H:%M')
        elif self.appointment_date:
            return self.appointment_date.strftime('%H:%M')
        return "Not set"
    
    def get_status_color(self):
        """Get color for appointment status"""
        colors = {
            'scheduled': '#007bff',
            'confirmed': '#28a745',
            'completed': '#6c757d',
            'cancelled': '#dc3545',
            'no-show': '#fd7e14'
        }
        return colors.get(self.status, '#6c757d')
    
    def can_be_modified(self):
        """Check if appointment can still be modified"""
        return self.status in ['scheduled', 'confirmed']
    
    def __repr__(self):
        return f"<Appointment {self.id} | Patient {self.patient_id} | Type: {self.appointment_type}>"


# ============================================================
#                   MEDICAL REPORT MODEL (NEW)
# ============================================================
class MedicalReport(db.Model):
    __tablename__ = 'medical_report'
    
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    prediction_id = db.Column(db.Integer, db.ForeignKey('prediction.id'), nullable=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=True)
    
    report_title = db.Column(db.String(200), nullable=False)
    diagnosis = db.Column(db.Text, nullable=False)
    symptoms = db.Column(db.Text, nullable=True)
    treatment_plan = db.Column(db.Text, nullable=True)
    prescriptions = db.Column(db.Text, nullable=True)
    follow_up_required = db.Column(db.Boolean, default=False)
    follow_up_date = db.Column(db.DateTime, nullable=True)
    additional_notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = db.relationship('User', foreign_keys=[patient_id])
    doctor = db.relationship('User', foreign_keys=[doctor_id])
    prediction = db.relationship('Prediction', backref='medical_reports')
    appointment = db.relationship('Appointment', backref='medical_reports')
    
    def __repr__(self):
        return f"<MedicalReport {self.id} | {self.report_title}>"


# ============================================================
#                   AUDIT LOG MODEL (NEW)
# ============================================================
class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True)  # Generic ID, no FK since user could be any role
    action = db.Column(db.String(100), nullable=False)  # login, logout, create, update, delete
    entity_type = db.Column(db.String(50), nullable=True)  # user, prediction, feedback, etc.
    entity_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # No relationship - user_id is generic and could reference any role table
    
    def __repr__(self):
        return f"<AuditLog {self.id} | {self.action} | User {self.user_id}>"


# ============================================================
#                   SYSTEM SETTINGS MODEL (NEW)
# ============================================================
class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    setting_value = db.Column(db.Text, nullable=True)
    setting_type = db.Column(db.String(50), default='string')  # string, integer, boolean, json
    description = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, default=False)  # Can non-admins see this?
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def get_value(self):
        """Get typed value based on setting_type"""
        if self.setting_type == 'integer':
            return int(self.setting_value) if self.setting_value else 0
        elif self.setting_type == 'boolean':
            return self.setting_value.lower() in ['true', '1', 'yes'] if self.setting_value else False
        elif self.setting_type == 'json':
            import json
            return json.loads(self.setting_value) if self.setting_value else {}
        return self.setting_value
    
    def __repr__(self):
        return f"<SystemSettings {self.setting_key}>"


# ============================================================
#                   MESSAGE MODEL (NEW)
# ============================================================
class Message(db.Model):
    __tablename__ = 'message'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, nullable=False, index=True)  # Generic ID, no FK since user could be any role
    receiver_id = db.Column(db.Integer, nullable=False, index=True)  # Generic ID, no FK since user could be any role
    subject = db.Column(db.String(200), nullable=True)
    message_body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    parent_message_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)  # For threading
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # No relationships - sender_id and receiver_id are generic and could reference any role table
    replies = db.relationship('Message', backref=db.backref('parent_message', remote_side=[id]))
    
    def mark_as_read(self):
        """Mark message as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
            db.session.commit()
    
    def __repr__(self):
        return f"<Message {self.id} | From {self.sender_id} To {self.receiver_id}>"


# ============================================================
#                   FILE ATTACHMENT MODEL (NEW)
# ============================================================
class FileAttachment(db.Model):
    __tablename__ = 'file_attachment'
    
    id = db.Column(db.Integer, primary_key=True)
    uploaded_by = db.Column(db.Integer, nullable=False, index=True)  # Generic ID, no FK since user could be any role
    prediction_id = db.Column(db.Integer, db.ForeignKey('prediction.id'), nullable=True)
    medical_report_id = db.Column(db.Integer, db.ForeignKey('medical_report.id'), nullable=True)
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50), nullable=True)  # image, pdf, document
    file_size = db.Column(db.Integer, nullable=True)  # in bytes
    mime_type = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    # No uploader relationship - uploaded_by is generic and could reference any role table
    prediction = db.relationship('Prediction', backref='attachments')
    medical_report = db.relationship('MedicalReport', backref='attachments')
    
    def get_file_size_formatted(self):
        """Get formatted file size"""
        if not self.file_size:
            return "Unknown"
        
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def __repr__(self):
        return f"<FileAttachment {self.id} | {self.original_filename}>"


# ============================================================
#                   SESSION LOG MODEL (NEW)
# ============================================================
class SessionLog(db.Model):
    __tablename__ = 'session_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)  # Generic ID, no FK since user could be any role
    session_token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # No relationship - user_id is generic and could reference any role table
    
    def end_session(self):
        """End the session"""
        self.is_active = False
        self.logout_time = datetime.utcnow()
        db.session.commit()
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
        db.session.commit()
    

# ============================================================
#                   LOGIN ATTEMPT MODEL (SECURITY)
# ============================================================
class LoginAttempt(db.Model):
    __tablename__ = 'login_attempt'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, index=True)
    ip_address = db.Column(db.String(50), nullable=False, index=True)
    user_agent = db.Column(db.String(200), nullable=True)
    attempt_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    success = db.Column(db.Boolean, default=False, nullable=False)
    failure_reason = db.Column(db.String(100), nullable=True)  # 'invalid_password', 'user_not_found', 'account_locked'
    
    def __repr__(self):
        return f"<LoginAttempt {self.username} | {self.ip_address} | {'Success' if self.success else 'Failed'}>"

    @staticmethod
    def record_attempt(username, ip_address, user_agent, success, failure_reason=None):
        """Record a login attempt"""
        attempt = LoginAttempt(
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            failure_reason=failure_reason
        )
        db.session.add(attempt)
        db.session.commit()
        return attempt

    @staticmethod
    def get_failed_attempts_count(username, minutes=30):
        """Get count of failed attempts for a username in the last X minutes"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        return LoginAttempt.query.filter(
            LoginAttempt.username == username,
            LoginAttempt.success == False,
            LoginAttempt.attempt_time >= cutoff_time
        ).count()

    @staticmethod
    def is_account_locked(username, max_attempts=5, lockout_minutes=30):
        """Check if account is locked due to too many failed attempts"""
        failed_count = LoginAttempt.get_failed_attempts_count(username, lockout_minutes)
        return failed_count >= max_attempts

    @staticmethod
    def get_lockout_time_remaining(username, max_attempts=5, lockout_minutes=30):
        """Get remaining lockout time in minutes"""
        if not LoginAttempt.is_account_locked(username, max_attempts, lockout_minutes):
            return 0
        
        cutoff_time = datetime.utcnow() - timedelta(minutes=lockout_minutes)
        oldest_failed_attempt = LoginAttempt.query.filter(
            LoginAttempt.username == username,
            LoginAttempt.success == False,
            LoginAttempt.attempt_time >= cutoff_time
        ).order_by(LoginAttempt.attempt_time.asc()).first()
        
        if oldest_failed_attempt:
            unlock_time = oldest_failed_attempt.attempt_time + timedelta(minutes=lockout_minutes)
            remaining = unlock_time - datetime.utcnow()
            return max(0, int(remaining.total_seconds() / 60))
        return 0

    @staticmethod
    def clear_failed_attempts(username):
        """Clear failed attempts after successful login"""
        LoginAttempt.query.filter(
            LoginAttempt.username == username,
            LoginAttempt.success == False
        ).delete()
        db.session.commit()

    @staticmethod
    def cleanup_old_attempts(days=30):
        """Clean up old login attempts (for maintenance)"""
        cutoff_time = datetime.utcnow() - timedelta(days=days)
        LoginAttempt.query.filter(
            LoginAttempt.attempt_time < cutoff_time
        ).delete()
        db.session.commit()

    def __repr__(self):
        return f"<SessionLog {self.id} | User {self.user_id} | Active: {self.is_active}>"


# ============================================================
#                   UNIVERSAL USER LOOKUP FUNCTIONS
# ============================================================
def get_user_by_username(username):
    """Get user from the user table by username"""
    return User.query.filter_by(username=username).first()


def get_user_by_phone(phone):
    """Get user from the user table by phone"""
    return User.query.filter_by(phone=phone).first()


def get_user_by_id_and_role(user_id, role):
    """Get user by ID and role"""
    user = User.query.get(user_id)
    if user and user.role == role:
        return user
    return None


def get_patient_by_unique_id(patient_unique_id):
    """Get patient by unique patient ID"""
    patient = Patient.query.filter_by(patient_unique_id=patient_unique_id).first()
    return patient


def get_all_users():
    """Get all users from all role tables"""
    users = []
    users.extend(Admin.query.all())
    users.extend(Doctor.query.all())
    users.extend(Patient.query.all())
    users.extend(XraySpecialist.query.all())
    return users


# ============================================================
#                       HELPER FUNCTIONS - UPDATED
# ============================================================


# ============================================================
#                       HELPER FUNCTIONS - UPDATED
# ============================================================
def create_default_admin(db, username="admin", phone="+251912345678", password="admin123"):
    """Create a default admin user if none exists"""
    user_exists = User.query.filter_by(username=username).first()
    if not user_exists:
        # Create admin user using the helper function
        admin_user = create_admin_user(
            username=username,
            phone=phone,
            password=password,
            admin_level='super_admin',
            department='System Administration',
            can_approve_users=True,
            can_manage_system=True,
            can_view_reports=True
        )
        
        print(f"✅ Default admin user created: {username}")
        return admin_user
    return None


def get_user_statistics():
    """Get user statistics for admin dashboard"""
    from sqlalchemy import func
    
    stats = {
        'total_patients': User.query.filter_by(role='patient').count(),
        'total_doctors': User.query.filter_by(role='doctor').count(),
        'total_xray_specialists': User.query.filter_by(role='xrayspecialist').count(),
        'total_admins': User.query.filter_by(role='admin').count(),
        'pending_approvals': User.query.filter_by(role='doctor', is_approved=False).count() + User.query.filter_by(role='xrayspecialist', is_approved=False).count(),
        'total_users': User.query.count(),
        'total_predictions': Prediction.query.count(),
        'total_feedbacks': Feedback.query.count(),
        'doctor_feedbacks': Feedback.query.filter(Feedback.doctor_id.isnot(None)).count(),
        'patient_feedbacks': Feedback.query.filter(Feedback.patient_id.isnot(None)).count(),
        'xray_specialist_feedbacks': Feedback.query.filter(Feedback.xray_specialist_id.isnot(None)).count(),
        'pending_validations': Prediction.query.filter(
            Prediction.doctor_validation.is_(None)
        ).count(),
        'total_appointments': Appointment.query.count(),
        'total_medical_reports': MedicalReport.query.count(),
        'total_messages': Message.query.count(),
        'total_file_attachments': FileAttachment.query.count(),
        'active_sessions': SessionLog.query.filter_by(is_active=True).count()
    }
    
    return stats


def get_recent_activity(limit=10):
    """Get recent system activity"""
    recent_predictions = Prediction.query.order_by(Prediction.date_uploaded.desc()).limit(limit).all()
    recent_feedbacks = Feedback.query.order_by(Feedback.date_submitted.desc()).limit(limit).all()
    recent_users = User.query.order_by(User.date_created.desc()).limit(limit).all()
    
    return {
        'recent_predictions': recent_predictions,
        'recent_feedbacks': recent_feedbacks,
        'recent_users': recent_users
    }


def create_feedback_notification(patient_name, message, feedback_id=None):
    """Create notifications for all admins when patient feedback is submitted"""
    try:
        # Get all admin users
        admins = User.query.filter_by(role='admin').all()
        
        for admin in admins:
            notification = Notification(
                admin_id=admin.id,
                title="New Patient Feedback Received",
                message=f"Patient {patient_name} submitted feedback: {message[:100]}..." if len(message) > 100 else f"Patient {patient_name} submitted feedback: {message}",
                type='feedback',
                related_feedback_id=feedback_id
            )
            db.session.add(notification)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating feedback notification: {e}")
        db.session.rollback()
        return False


def create_doctor_feedback_notification(doctor_name, message, feedback_id=None):
    """Create legacy notifications for all admins when doctor submits feedback - DEPRECATED: Use NotificationService instead"""
    try:
        # Only create legacy notifications for backward compatibility
        # Universal notifications should be created using NotificationService directly
        title = "New Doctor Feedback Received"
        notification_message = f"Dr. {doctor_name} submitted feedback: {message[:100]}{'...' if len(message) > 100 else ''}"
        
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            notification = Notification(
                admin_id=admin.id,
                title=title,
                message=notification_message,
                type='feedback',
                related_feedback_id=feedback_id
            )
            db.session.add(notification)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating doctor feedback notification: {e}")
        db.session.rollback()
        return False


def create_xray_specialist_feedback_notification(specialist_name, message, feedback_id=None):
    """Create legacy notifications for all admins when xray specialist submits feedback - DEPRECATED: Use NotificationService instead"""
    try:
        # Only create legacy notifications for backward compatibility
        # Universal notifications should be created using NotificationService directly
        title = "New X-ray Specialist Feedback Received"
        notification_message = f"X-ray Specialist {specialist_name} submitted feedback: {message[:100]}{'...' if len(message) > 100 else ''}"
        
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            notification = Notification(
                admin_id=admin.id,
                title=title,
                message=notification_message,
                type='feedback',
                related_feedback_id=feedback_id
            )
            db.session.add(notification)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating xray specialist feedback notification: {e}")
        db.session.rollback()
        return False


def create_xray_to_doctor_feedback_notification(xray_specialist_name, doctor_id, message, feedback_id=None):
    """Create notification for doctor when X-ray specialist sends feedback"""
    try:
        # Get the specific doctor
        doctor = User.query.filter_by(id=doctor_id, role='doctor').first()
        
        if doctor:
            # Create universal notification for the doctor
            NotificationService.create_notification(
                user_id=doctor_id,
                user_role='doctor',
                title="New Feedback from X-ray Specialist",
                message=f"X-ray Specialist {xray_specialist_name} sent you feedback: {message[:100]}..." if len(message) > 100 else f"X-ray Specialist {xray_specialist_name} sent you feedback: {message}",
                notification_type='xray_feedback',
                action_url='#feedback',
                is_clickable=True
            )
            
            # Also create legacy doctor notification for backward compatibility
            notification = DoctorNotification(
                doctor_id=doctor_id,
                patient_id=None,
                patient_name=f"X-ray Specialist {xray_specialist_name}",
                xray_filename="N/A",
                message=f"Feedback from X-ray Specialist {xray_specialist_name}: {message[:100]}..." if len(message) > 100 else f"Feedback from X-ray Specialist {xray_specialist_name}: {message}",
                is_read=False,
                notification_type='xray_feedback'
            )
            db.session.add(notification)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating X-ray to doctor feedback notification: {e}")
        db.session.rollback()
        return False


def create_user_approval_notification(username, role):
    """Create notification for admin about user approval"""
    try:
        # Get all admin users
        admins = User.query.filter_by(role='admin').all()
        
        for admin in admins:
            notification = Notification(
                admin_id=admin.id,
                title="User Approval Required",
                message=f"New {role} registration: {username} needs approval",
                type='user_approval'
            )
            db.session.add(notification)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating user approval notification: {e}")
        db.session.rollback()
        return False


def get_admin_notifications(admin_id, limit=20, unread_only=False):
    """Get notifications for admin dashboard"""
    query = Notification.query.filter_by(admin_id=admin_id)
    
    if unread_only:
        query = query.filter_by(is_read=False)
    
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


def mark_all_admin_notifications_read(admin_id):
    """Mark all notifications as read for an admin"""
    try:
        Notification.query.filter_by(admin_id=admin_id, is_read=False).update({'is_read': True})
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error marking notifications as read: {e}")
        db.session.rollback()
        return False


def create_system_notification(admin_id, title, message, notification_type='system'):
    """Create a system notification for admin"""
    try:
        notification = Notification(
            admin_id=admin_id,
            title=title,
            message=message,
            type=notification_type
        )
        db.session.add(notification)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Error creating system notification: {e}")
        db.session.rollback()
        return False


def get_patient_feedbacks(patient_id=None):
    """Get patient feedbacks with optional filtering"""
    query = Feedback.query.filter(Feedback.patient_id.isnot(None))
    
    if patient_id:
        query = query.filter_by(patient_id=patient_id)
    
    return query.order_by(Feedback.date_submitted.desc()).all()


def get_doctor_feedbacks(doctor_id=None):
    """Get doctor feedbacks with optional filtering"""
    query = Feedback.query.filter(Feedback.doctor_id.isnot(None))
    
    if doctor_id:
        query = query.filter_by(doctor_id=doctor_id)
    
    return query.order_by(Feedback.date_submitted.desc()).all()


def get_xray_specialist_feedbacks(xray_specialist_id=None):
    """Get xray specialist feedbacks with optional filtering"""
    query = Feedback.query.filter(Feedback.xray_specialist_id.isnot(None))
    
    if xray_specialist_id:
        query = query.filter_by(xray_specialist_id=xray_specialist_id)
    
    return query.order_by(Feedback.date_submitted.desc()).all()


def get_all_feedbacks():
    """Get all feedbacks from patients, doctors, and xray specialists"""
    return Feedback.query.order_by(Feedback.date_submitted.desc()).all()


def get_doctor_pending_validations(doctor_id):
    """Get pending validations for a doctor"""
    return Prediction.query.filter(
        Prediction.doctor_id == doctor_id,
        Prediction.doctor_validation.is_(None)
    ).order_by(Prediction.date_uploaded.desc()).all()


def get_patient_predictions(patient_id):
    """Get all predictions for a patient"""
    return Prediction.query.filter_by(patient_id=patient_id).order_by(Prediction.date_uploaded.desc()).all()


def search_users(query, role=None):
    """Search users by username or phone across all role tables"""
    from sqlalchemy import or_
    
    results = []
    
    if not role or role == 'admin':
        admins = Admin.query.filter(
            or_(
                Admin.username.ilike(f"%{query}%"),
                Admin.phone.ilike(f"%{query}%")
            )
        ).all()
        results.extend(admins)
    
    if not role or role == 'doctor':
        doctors = Doctor.query.filter(
            or_(
                Doctor.username.ilike(f"%{query}%"),
                Doctor.phone.ilike(f"%{query}%")
            )
        ).all()
        results.extend(doctors)
    
    if not role or role == 'patient':
        patients = Patient.query.filter(
            or_(
                Patient.username.ilike(f"%{query}%"),
                Patient.phone.ilike(f"%{query}%")
            )
        ).all()
        results.extend(patients)
    
    if not role or role == 'xrayspecialist':
        specialists = XraySpecialist.query.filter(
            or_(
                XraySpecialist.username.ilike(f"%{query}%"),
                XraySpecialist.phone.ilike(f"%{query}%")
            )
        ).all()
        results.extend(specialists)
    
    return results


def cleanup_old_notifications(days=30):
    """Clean up notifications older than specified days"""
    from datetime import timedelta
    from sqlalchemy import func
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    try:
        # Delete old notifications
        old_notifications = Notification.query.filter(
            Notification.created_at < cutoff_date
        ).delete()
        
        old_doctor_notifications = DoctorNotification.query.filter(
            DoctorNotification.created_at < cutoff_date
        ).delete()
        
        old_xray_notifications = XraySpecialistNotification.query.filter(
            XraySpecialistNotification.created_at < cutoff_date
        ).delete()
        
        db.session.commit()
        print(f"Cleaned up {old_notifications} admin notifications, {old_doctor_notifications} doctor notifications, and {old_xray_notifications} xray specialist notifications older than {days} days")
        return True
    except Exception as e:
        print(f"Error cleaning up old notifications: {e}")
        db.session.rollback()
        return False


def initialize_database(db):
    """Initialize database with default data"""
    try:
        # Create all tables
        db.create_all()
        
        # Create default admin
        create_default_admin(db)
        
        print("✅ Database initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False


def create_admin_user(username, phone, password, **kwargs):
    """Create a new admin user"""
    try:
        # Create user record
        user = User(username=username, phone=phone, role='admin')
        user.set_password(password)
        user.is_approved = True
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create admin profile
        admin_profile = Admin(user_id=user.id, **kwargs)
        db.session.add(admin_profile)
        db.session.commit()
        return user
    except Exception as e:
        print(f"Error creating admin user: {e}")
        db.session.rollback()
        return None


def create_doctor_user(username, phone, password, email=None, **kwargs):
    """Create a new doctor user"""
    try:
        # Create user record
        user = User(username=username, phone=phone, role='doctor')
        user.set_password(password)
        user.is_approved = False  # Doctors need approval
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create doctor profile with email
        doctor_profile = Doctor(user_id=user.id, email=normalize_email(email) if email else None, **kwargs)
        db.session.add(doctor_profile)
        db.session.commit()
        return user
    except Exception as e:
        print(f"Error creating doctor user: {e}")
        db.session.rollback()
        return None


def generate_unique_patient_id():
    """Generate a unique patient ID in format PAT-YYYYMMDD-XXXX"""
    from datetime import datetime
    import random
    
    date_str = datetime.now().strftime('%Y%m%d')
    
    # Try to generate a unique ID
    for _ in range(100):  # Max 100 attempts
        random_num = random.randint(1000, 9999)
        patient_id = f"PAT-{date_str}-{random_num}"
        
        # Check if this ID already exists
        existing = Patient.query.filter_by(patient_unique_id=patient_id).first()
        if not existing:
            return patient_id
    
    # If we can't generate a unique ID, use timestamp
    timestamp = int(datetime.now().timestamp())
    return f"PAT-{date_str}-{timestamp % 10000}"


def create_patient_user(username, phone, password, email=None, **kwargs):
    """Create a new patient user"""
    try:
        # Create user record
        user = User(username=username, phone=phone, role='patient')
        user.set_password(password)
        user.is_approved = True  # Patients auto-approved
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Generate unique patient ID
        patient_unique_id = generate_unique_patient_id()
        
        # Create patient profile with email
        patient_profile = Patient(user_id=user.id, patient_unique_id=patient_unique_id, email=normalize_email(email) if email else None, **kwargs)
        db.session.add(patient_profile)
        db.session.commit()
        return user
    except Exception as e:
        print(f"Error creating patient user: {e}")
        db.session.rollback()
        return None


def create_xray_specialist_user(username, phone, password, email=None, **kwargs):
    """Create a new X-ray specialist user"""
    try:
        # Create user record
        user = User(username=username, phone=phone, role='xrayspecialist')
        user.set_password(password)
        user.is_approved = False  # X-ray specialists need approval
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create xray specialist profile with email
        specialist_profile = XraySpecialist(user_id=user.id, email=normalize_email(email) if email else None, **kwargs)
        db.session.add(specialist_profile)
        db.session.commit()
        return user
    except Exception as e:
        print(f"Error creating X-ray specialist user: {e}")
        db.session.rollback()
        return None


def create_reception_user(username, phone, password, email=None, **kwargs):
    """Create a new reception user"""
    try:
        # Create user record
        user = User(username=username, phone=phone, role='reception')
        user.set_password(password)
        user.is_approved = False  # Reception staff need approval
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create reception profile with email
        reception_profile = Reception(user_id=user.id, email=normalize_email(email) if email else None, **kwargs)
        db.session.add(reception_profile)
        db.session.commit()
        return user
    except Exception as e:
        print(f"Error creating reception user: {e}")
        db.session.rollback()
        return None


def create_health_officer_user(username, phone, password, email=None, **kwargs):
    """Create a new health officer user"""
    try:
        # Create user record
        user = User(username=username, phone=phone, role='healthofficer')
        user.set_password(password)
        user.is_approved = False  # Health officers need approval
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # Create health officer profile with email
        health_officer_profile = HealthOfficer(user_id=user.id, email=normalize_email(email) if email else None, **kwargs)
        db.session.add(health_officer_profile)
        db.session.commit()
        return user
    except Exception as e:
        print(f"Error creating health officer user: {e}")
        db.session.rollback()
        return None


# Legacy profile creation functions removed - use create_patient_user and create_doctor_user instead


# ============================================================
#                   PATIENT-DOCTOR ASSIGNMENT FUNCTIONS
# ============================================================
def assign_patient_to_doctor(patient_id, doctor_id, assigned_by_admin_id, notes=None):
    """Assign a patient to a doctor"""
    try:
        # Check if assignment already exists
        existing = PatientDoctorAssignment.query.filter_by(
            patient_id=patient_id, 
            doctor_id=doctor_id, 
            is_active=True
        ).first()
        
        if existing:
            return existing
        
        assignment = PatientDoctorAssignment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            assigned_by=assigned_by_admin_id,
            notes=notes
        )
        db.session.add(assignment)
        db.session.commit()
        return assignment
    except Exception as e:
        print(f"Error assigning patient to doctor: {e}")
        db.session.rollback()
        return None

def get_patient_assigned_doctor(patient_id):
    """Get the doctor assigned to a patient"""
    assignment = PatientDoctorAssignment.query.filter_by(
        patient_id=patient_id, 
        is_active=True
    ).first()
    return assignment.doctor if assignment else None

def get_doctor_assigned_patients(doctor_id):
    """Get all patients assigned to a doctor"""
    assignments = PatientDoctorAssignment.query.filter_by(
        doctor_id=doctor_id, 
        is_active=True
    ).all()
    return [assignment.patient for assignment in assignments]

def remove_patient_doctor_assignment(patient_id, doctor_id):
    """Remove/deactivate a patient-doctor assignment"""
    try:
        assignment = PatientDoctorAssignment.query.filter_by(
            patient_id=patient_id, 
            doctor_id=doctor_id, 
            is_active=True
        ).first()
        
        if assignment:
            assignment.is_active = False
            db.session.commit()
            return True
        return False
    except Exception as e:
        print(f"Error removing patient-doctor assignment: {e}")
        db.session.rollback()
        return False


def create_appointment(patient_id, appointment_date, created_by_reception=None, **kwargs):
    """Create an appointment (enhanced for reception use)"""
    try:
        # Get patient information for historical tracking
        patient = User.query.get(patient_id)
        
        appointment = Appointment(
            patient_id=patient_id,
            appointment_date=appointment_date,
            created_by_reception=created_by_reception,
            patient_name_at_appointment=patient.username if patient else None,
            patient_phone_at_appointment=patient.phone if patient else None,
            **kwargs
        )
        db.session.add(appointment)
        db.session.commit()
        return appointment
    except Exception as e:
        print(f"Error creating appointment: {e}")
        db.session.rollback()
        return None


def get_available_appointment_slots(date, appointment_type='mammography'):
    """Get available appointment slots for a given date"""
    try:
        # Define time slots (can be customized)
        time_slots = [
            '09:00', '09:30', '10:00', '10:30', '11:00', '11:30',
            '14:00', '14:30', '15:00', '15:30', '16:00', '16:30'
        ]
        
        # Get existing appointments for the date
        existing_appointments = Appointment.query.filter(
            db.func.date(Appointment.appointment_date) == date,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).all()
        
        # Get booked time slots
        booked_slots = []
        for apt in existing_appointments:
            if apt.appointment_time:
                booked_slots.append(apt.appointment_time.strftime('%H:%M'))
            elif apt.appointment_date:
                booked_slots.append(apt.appointment_date.strftime('%H:%M'))
        
        # Return available slots
        available_slots = [slot for slot in time_slots if slot not in booked_slots]
        return available_slots
        
    except Exception as e:
        print(f"Error getting available slots: {e}")
        return []


def register_patient_by_reception(patient_data, reception_user_id):
    """Register a new patient through reception"""
    try:
        # Create patient user
        patient_user = create_patient_user(
            username=patient_data['username'],
            phone=patient_data['phone'],
            password=patient_data.get('password', 'temp123'),  # Temporary password
            **patient_data.get('profile_data', {})
        )
        
        if patient_user:
            # Update reception statistics
            reception = Reception.query.filter_by(user_id=reception_user_id).first()
            if reception:
                reception.total_patients_registered += 1
                db.session.commit()
        
        return patient_user
    except Exception as e:
        print(f"Error registering patient: {e}")
        db.session.rollback()
        return None


def create_medical_report(patient_id, doctor_id, report_title, diagnosis, **kwargs):
    """Create a medical report"""
    try:
        report = MedicalReport(
            patient_id=patient_id,
            doctor_id=doctor_id,
            report_title=report_title,
            diagnosis=diagnosis,
            **kwargs
        )
        db.session.add(report)
        db.session.commit()
        return report
    except Exception as e:
        print(f"Error creating medical report: {e}")
        db.session.rollback()
        return None


def log_audit(user_id, action, entity_type=None, entity_id=None, description=None, ip_address=None, user_agent=None):
    """Create an audit log entry"""
    try:
        log = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(log)
        db.session.commit()
        return log
    except Exception as e:
        print(f"Error creating audit log: {e}")
        db.session.rollback()
        return None


def get_system_setting(key, default=None):
    """Get a system setting value"""
    setting = SystemSettings.query.filter_by(setting_key=key).first()
    if setting:
        return setting.get_value()
    return default


def set_system_setting(key, value, setting_type='string', description=None, is_public=False):
    """Set a system setting value"""
    try:
        setting = SystemSettings.query.filter_by(setting_key=key).first()
        if setting:
            setting.setting_value = str(value)
            setting.setting_type = setting_type
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSettings(
                setting_key=key,
                setting_value=str(value),
                setting_type=setting_type,
                description=description,
                is_public=is_public
            )
            db.session.add(setting)
        
        db.session.commit()
        return setting
    except Exception as e:
        print(f"Error setting system setting: {e}")
        db.session.rollback()
        return None


def send_message(sender_id, receiver_id, message_body, subject=None, parent_message_id=None):
    """Send a message between users"""
    try:
        message = Message(
            sender_id=sender_id,
            receiver_id=receiver_id,
            subject=subject,
            message_body=message_body,
            parent_message_id=parent_message_id
        )
        db.session.add(message)
        db.session.commit()
        return message
    except Exception as e:
        print(f"Error sending message: {e}")
        db.session.rollback()
        return None


def create_session_log(user_id, session_token, ip_address=None, user_agent=None):
    """Create a session log entry"""
    try:
        session_log = SessionLog(
            user_id=user_id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(session_log)
        db.session.commit()
        return session_log
    except Exception as e:
        print(f"Error creating session log: {e}")
        db.session.rollback()
        return None


def cleanup_inactive_sessions(hours=24):
    """Clean up inactive sessions older than specified hours"""
    from datetime import timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    
    try:
        inactive_sessions = SessionLog.query.filter(
            SessionLog.is_active == True,
            SessionLog.last_activity < cutoff_time
        ).all()
        
        for session in inactive_sessions:
            session.end_session()
        
        print(f"Cleaned up {len(inactive_sessions)} inactive sessions")
        return True
    except Exception as e:
        print(f"Error cleaning up inactive sessions: {e}")
        db.session.rollback()
        return False


def get_unread_messages_count(user_id):
    """Get count of unread messages for a user"""
    return Message.query.filter_by(receiver_id=user_id, is_read=False).count()


def get_upcoming_appointments(user_id, role='patient', limit=10):
    """Get upcoming appointments for a user"""
    from datetime import datetime
    
    if role == 'patient':
        appointments = Appointment.query.filter(
            Appointment.patient_id == user_id,
            Appointment.appointment_date >= datetime.utcnow(),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.appointment_date.asc()).limit(limit).all()
    elif role == 'doctor':
        appointments = Appointment.query.filter(
            Appointment.doctor_id == user_id,
            Appointment.appointment_date >= datetime.utcnow(),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.appointment_date.asc()).limit(limit).all()
    else:
        appointments = []
    
    return appointments


# Context processor to make functions available in templates
def utility_processor():
    """Make utility functions available in templates"""
    return {
        'get_user_statistics': get_user_statistics,
        'get_recent_activity': get_recent_activity,
        'get_system_setting': get_system_setting,
        'get_unread_messages_count': get_unread_messages_count,
    }

# ============================================================
#                   EMAIL VALIDATION UTILITIES
# ============================================================
import re
import random
import string
from datetime import timedelta

def validate_email_format(email):
    """Validate email format using regex"""
    if not email:
        return False
    
    # Email regex pattern that matches standard email formats
    pattern = r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email.strip()) is not None

def normalize_email(email):
    """Normalize email address to lowercase and strip whitespace"""
    if not email:
        return None
    return email.strip().lower()

def is_email_unique(email, exclude_user_id=None):
    """Check if email is unique across all user roles"""
    if not email:
        return True
    
    normalized_email = normalize_email(email)
    
    # Check in Patient model
    patient_query = Patient.query.filter(Patient.email.ilike(normalized_email))
    if exclude_user_id:
        patient_query = patient_query.filter(Patient.user_id != exclude_user_id)
    if patient_query.first():
        return False
    
    # Check in Doctor model
    doctor_query = Doctor.query.filter(Doctor.email.ilike(normalized_email))
    if exclude_user_id:
        doctor_query = doctor_query.filter(Doctor.user_id != exclude_user_id)
    if doctor_query.first():
        return False
    
    # Check in XraySpecialist model
    xray_query = XraySpecialist.query.filter(XraySpecialist.email.ilike(normalized_email))
    if exclude_user_id:
        xray_query = xray_query.filter(XraySpecialist.user_id != exclude_user_id)
    if xray_query.first():
        return False
    
    # Check in Reception model
    reception_query = Reception.query.filter(Reception.email.ilike(normalized_email))
    if exclude_user_id:
        reception_query = reception_query.filter(Reception.user_id != exclude_user_id)
    if reception_query.first():
        return False
    
    # Check in HealthOfficer model
    health_query = HealthOfficer.query.filter(HealthOfficer.email.ilike(normalized_email))
    if exclude_user_id:
        health_query = health_query.filter(HealthOfficer.user_id != exclude_user_id)
    if health_query.first():
        return False
    
    # Check in Admin model
    admin_query = Admin.query.filter(Admin.email.ilike(normalized_email))
    if exclude_user_id:
        admin_query = admin_query.filter(Admin.user_id != exclude_user_id)
    if admin_query.first():
        return False
    
    return True

def validate_email(email, exclude_user_id=None):
    """Comprehensive email validation"""
    if not email or email.strip() == '':
        return True, None  # Email is optional
    
    # Validate format
    if not validate_email_format(email):
        return False, "Invalid email format. Please enter a valid email address (e.g., user@example.com)"
    
    # Check uniqueness
    if not is_email_unique(email, exclude_user_id):
        return False, "This email address is already registered. Please use a different email."
    
    return True, None

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=6))

def create_verification_code(email):
    """Create a new verification code for email"""
    try:
        # Clean up any existing codes for this email
        VerificationCode.query.filter_by(email=normalize_email(email)).delete()
        
        # Generate new code
        code = generate_verification_code()
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        verification_code = VerificationCode(
            email=normalize_email(email),
            code=code,
            expires_at=expires_at
        )
        
        db.session.add(verification_code)
        db.session.commit()
        
        return code
    except Exception as e:
        print(f"Error creating verification code: {e}")
        db.session.rollback()
        return None

def validate_verification_code(email, code):
    """Validate a verification code"""
    try:
        verification_code = VerificationCode.query.filter_by(
            email=normalize_email(email),
            code=code,
            is_used=False
        ).first()
        
        if not verification_code:
            return False, "Invalid verification code"
        
        if not verification_code.is_valid():
            return False, "Verification code has expired. Please request a new one."
        
        # Mark as used
        verification_code.mark_as_used()
        
        return True, "Verification code is valid"
    except Exception as e:
        print(f"Error validating verification code: {e}")
        return False, "Error validating verification code"

def get_user_email(user_id, role):
    """Get user email based on user ID and role"""
    try:
        if role == 'patient':
            profile = Patient.query.filter_by(user_id=user_id).first()
        elif role == 'doctor':
            profile = Doctor.query.filter_by(user_id=user_id).first()
        elif role == 'xrayspecialist':
            profile = XraySpecialist.query.filter_by(user_id=user_id).first()
        elif role == 'reception':
            profile = Reception.query.filter_by(user_id=user_id).first()
        elif role == 'healthofficer':
            profile = HealthOfficer.query.filter_by(user_id=user_id).first()
        elif role == 'admin':
            profile = Admin.query.filter_by(user_id=user_id).first()
        else:
            return None
        
        return profile.email if profile else None
    except Exception as e:
        print(f"Error getting user email: {e}")
        return None


# ============================================================
#                   EMAIL NOTIFICATION SERVICE
# ============================================================
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def load_env_file():
    """Load environment variables from .env file"""
    try:
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key] = value
    except Exception as e:
        print(f"Error loading .env file: {e}")

def send_email(to_email, subject, body, is_html=False):
    """Send email using SMTP"""
    try:
        # Load environment variables from .env file
        load_env_file()
        
        # Email configuration - these should be set as environment variables
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        smtp_username = os.environ.get('SMTP_USERNAME', '')
        smtp_password = os.environ.get('SMTP_PASSWORD', '')
        
        if not smtp_username or not smtp_password or smtp_username == 'your-email@gmail.com':
            print("Email configuration not found or incomplete. Skipping email sending.")
            print("Please update SMTP_USERNAME in .env file with your actual Gmail address.")
            return False
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"BreastCancerDetectionSystem <{smtp_username}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body to email
        msg.attach(MIMEText(body, 'html' if is_html else 'plain'))
        
        # Create SMTP session
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Enable security
        server.login(smtp_username, smtp_password)
        
        # Send email
        text = msg.as_string()
        server.sendmail(smtp_username, to_email, text)
        server.quit()
        
        print(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")
        return False

def send_account_approval_email(user_id, role):
    """Send account approval notification email"""
    try:
        user = User.query.get(user_id)
        if not user:
            return False
        
        email = get_user_email(user_id, role)
        if not email:
            print(f"No email found for user {user.username}")
            return True  # Don't fail the approval process
        
        subject = "🎉 Account Approved - BreastCancerDetectionSystem"
        
        # Create professional HTML email template
        body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.8; color: #333; background-color: #f5f5f5; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #0078D4 0%, #0063B1 100%); color: white; padding: 40px 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 28px; font-weight: 700; }}
                .content {{ padding: 40px 30px; }}
                .greeting {{ font-size: 18px; margin-bottom: 20px; }}
                .message {{ font-size: 16px; margin-bottom: 30px; }}
                .account-details {{ background: #f8f9fa; padding: 25px; border-radius: 8px; margin: 25px 0; border-left: 4px solid #0078D4; }}
                .account-details h3 {{ margin: 0 0 15px 0; color: #0078D4; font-size: 18px; }}
                .detail-item {{ margin: 8px 0; font-size: 16px; }}
                .detail-label {{ font-weight: 600; color: #555; }}
                .next-steps {{ margin: 30px 0; }}
                .next-steps h3 {{ color: #0078D4; margin-bottom: 15px; }}
                .steps-list {{ padding-left: 20px; }}
                .steps-list li {{ margin: 8px 0; font-size: 16px; }}
                .security-note {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 20px; border-radius: 8px; margin: 25px 0; }}
                .security-note h3 {{ margin: 0 0 10px 0; color: #856404; }}
                .footer {{ text-align: center; padding: 20px; background: #f8f9fa; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to the Breast Cancer Detection System!</h1>
                </div>
                <div class="content">
                    <div class="greeting">Dear <strong>{user.username}</strong>,</div>
                    
                    <div class="message">Great news! Your account has been approved for the Breast Cancer Detection System.</div>
                    
                    <div class="account-details">
                        <h3>Account Approved</h3>
                        <div class="detail-item"><span class="detail-label">Username:</span> {user.username}</div>
                        <div class="detail-item"><span class="detail-label">Role:</span> {role.title().replace('Xrayspecialist', 'X-ray Specialist').replace('Healthofficer', 'Health Officer')}</div>
                        <div class="detail-item"><span class="detail-label">Approval Date:</span> {datetime.now().strftime('%B %d, %Y')}</div>
                    </div>
                    
                    <div class="next-steps">
                        <h3>Next Steps:</h3>
                        <ul class="steps-list">
                            <li>Log in to your account</li>
                            <li>Use your username and password to access the system</li>
                            <li>Start using our services based on your role</li>
                        </ul>
                    </div>
                    
                    <div class="security-note">
                        <h3>Security Reminder</h3>
                        <p>Never share your password with anyone.</p>
                    </div>
                </div>
                <div class="footer">
                    <p><strong>BreastCancerDetectionSystem Team</strong><br>
                    Advanced Medical Imaging & AI Diagnostics<br>
                    📧 Support: admin@breastcancerdetection.com</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return send_email(email, subject, body, is_html=True)
        
    except Exception as e:
        print(f"Error sending approval email: {e}")
        return False

def send_verification_code_email(email, code):
    """Send verification code for password reset"""
    try:
        subject = "🔐 Password Reset Code - BreastCancerDetectionSystem"
        
        body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #0078D4 0%, #0063B1 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .code-box {{ background: white; padding: 30px; text-align: center; border-radius: 8px; margin: 20px 0; border: 2px solid #0078D4; }}
                .code {{ font-size: 36px; font-weight: bold; color: #0078D4; letter-spacing: 8px; font-family: 'Courier New', monospace; }}
                .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏥 BreastCancerDetectionSystem</h1>
                    <h2>Password Reset Request</h2>
                </div>
                <div class="content">
                    <p>You have requested to reset your password for the Breast Cancer Detection System.</p>
                    
                    <div class="code-box">
                        <p>Your verification code is:</p>
                        <div class="code">{code}</div>
                        <p style="margin-top: 20px; color: #666;">Enter this code on the verification page</p>
                    </div>
                    
                    <div class="warning">
                        <p><strong>⏰ Important:</strong> This code will expire in <strong>15 minutes</strong> for security reasons.</p>
                    </div>
                    
                    <h3>🔒 Security Information:</h3>
                    <ul>
                        <li>This code can only be used once</li>
                        <li>Never share this code with anyone</li>
                        <li>If you didn't request this reset, please ignore this email</li>
                        <li>Your account remains secure</li>
                    </ul>
                    
                    <p>If you continue to have issues accessing your account, please contact our system administrator for assistance.</p>
                    
                    <div class="footer">
                        <p><strong>BreastCancerDetectionSystem Team</strong><br>
                        Advanced Medical Imaging & AI Diagnostics<br>
                        📧 Support: admin@breastcancerdetection.com<br>
                        🌐 System: <a href="http://localhost:5000">http://localhost:5000</a></p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return send_email(email, subject, body, is_html=True)
        
    except Exception as e:
        print(f"Error sending verification code email: {e}")
        return False


# ============================================================
#                   UNIVERSAL NOTIFICATION SERVICE
# ============================================================
class NotificationService:
    """Service class for managing universal notifications across all user roles"""
    
    @staticmethod
    def create_notification(user_id, user_role, title, message, notification_type='general', 
                          action_url=None, action_data=None, is_clickable=True):
        """Create a new notification for a user"""
        try:
            notification = UniversalNotification(
                user_id=user_id,
                user_role=user_role,
                title=title,
                message=message,
                notification_type=notification_type,
                action_url=action_url,
                action_data=action_data,
                is_clickable=is_clickable
            )
            db.session.add(notification)
            db.session.commit()
            return notification
        except Exception as e:
            print(f"Error creating notification: {e}")
            db.session.rollback()
            return None
    
    @staticmethod
    def create_notifications_for_role(role, title, message, notification_type='general', 
                                    action_url=None, action_data=None, is_clickable=True, exclude_user_ids=None):
        """Create notifications for all users of a specific role"""
        try:
            users = User.query.filter_by(role=role, is_active_user=True).all()
            if exclude_user_ids:
                users = [user for user in users if user.id not in exclude_user_ids]
            
            notifications = []
            for user in users:
                notification = NotificationService.create_notification(
                    user_id=user.id,
                    user_role=role,
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    action_url=action_url,
                    action_data=action_data,
                    is_clickable=is_clickable
                )
                if notification:
                    notifications.append(notification)
            
            return notifications
        except Exception as e:
            print(f"Error creating notifications for role {role}: {e}")
            return []
    
    @staticmethod
    def get_notifications(user_id, user_role, limit=50, unread_only=False):
        """Get notifications for a user"""
        try:
            query = UniversalNotification.query.filter_by(user_id=user_id, user_role=user_role)
            
            if unread_only:
                query = query.filter_by(is_read=False)
            
            notifications = query.order_by(UniversalNotification.created_at.desc()).limit(limit).all()
            return notifications
        except Exception as e:
            print(f"Error getting notifications for user {user_id}: {e}")
            return []
    
    @staticmethod
    def get_unread_count(user_id, user_role):
        """Get count of unread notifications for a user"""
        try:
            count = UniversalNotification.query.filter_by(
                user_id=user_id, 
                user_role=user_role, 
                is_read=False
            ).count()
            return count
        except Exception as e:
            print(f"Error getting unread count for user {user_id}: {e}")
            return 0
    
    @staticmethod
    def mark_as_read(notification_id, user_id):
        """Mark a specific notification as read"""
        try:
            notification = UniversalNotification.query.filter_by(
                id=notification_id, 
                user_id=user_id
            ).first()
            
            if notification:
                notification.mark_as_read()
                return True
            return False
        except Exception as e:
            print(f"Error marking notification {notification_id} as read: {e}")
            return False
    
    @staticmethod
    def mark_all_as_read(user_id, user_role):
        """Mark all notifications as read for a user"""
        try:
            notifications = UniversalNotification.query.filter_by(
                user_id=user_id, 
                user_role=user_role, 
                is_read=False
            ).all()
            
            for notification in notifications:
                notification.is_read = True
                notification.read_at = datetime.utcnow()
            
            db.session.commit()
            return len(notifications)
        except Exception as e:
            print(f"Error marking all notifications as read for user {user_id}: {e}")
            db.session.rollback()
            return 0
    
    @staticmethod
    def clear_all_notifications(user_id, user_role):
        """Clear all notifications for a user"""
        try:
            deleted_count = UniversalNotification.query.filter_by(
                user_id=user_id, 
                user_role=user_role
            ).delete()
            
            db.session.commit()
            return deleted_count
        except Exception as e:
            print(f"Error clearing notifications for user {user_id}: {e}")
            db.session.rollback()
            return 0
    
    @staticmethod
    def create_feedback_notification(sender_name, sender_role, message, recipient_roles=['admin']):
        """Create feedback notification for specified roles"""
        title = f"New Feedback from {sender_role.title()}"
        notification_message = f"{sender_name} sent feedback: {message[:100]}{'...' if len(message) > 100 else ''}"
        
        notifications = []
        for role in recipient_roles:
            role_notifications = NotificationService.create_notifications_for_role(
                role=role,
                title=title,
                message=notification_message,
                notification_type='feedback',
                action_url='/feedback',
                is_clickable=True
            )
            notifications.extend(role_notifications)
        
        return notifications
    
    @staticmethod
    def create_appointment_notification(patient_name, doctor_name, appointment_date, notification_type='appointment'):
        """Create appointment notification for patient and doctor"""
        notifications = []
        
        # Notify patient
        patient_title = "Appointment Scheduled"
        patient_message = f"Your appointment with Dr. {doctor_name} is scheduled for {appointment_date}"
        
        # Notify doctor
        doctor_title = "New Appointment"
        doctor_message = f"New appointment with {patient_name} scheduled for {appointment_date}"
        
        # Note: This would need patient_id and doctor_id to create actual notifications
        # This is a template for the notification creation
        
        return notifications
    
    @staticmethod
    def create_validation_notification(patient_name, doctor_name, xray_filename):
        """Create notification when doctor validates X-ray results"""
        title = "X-ray Validation Complete"
        message = f"Dr. {doctor_name} has validated your X-ray results for {xray_filename}"
        
        # Note: This would need patient_id to create actual notification
        # This is a template for the notification creation
        
        return []