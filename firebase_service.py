from functools import wraps
from flask import request, jsonify, g
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.auth.exceptions import GoogleAuthError

# Initialize Firebase Admin SDK
cred = credentials.Certificate('./utils/cred.json')  # Replace with your Firebase Admin SDK path
firebase_admin.initialize_app(cred)
db = firestore.client()

  # or the relevant base exception


def verify_google_token(id_token):
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except GoogleAuthError as e:  
        raise ValueError(f"Invalid ID token: {e}")


def get_or_create_user(decoded_token):
    user_id = decoded_token['uid']
    user_doc = db.collection('users').document(user_id).get()
    
    if user_doc.exists:
        return user_doc.to_dict(), False
    else:
        user_data = {
            'name': decoded_token.get('name'),
            'email': decoded_token.get('email'),
            'company': '',
        }
        db.collection('users').document(user_id).set(user_data)
        return user_data, True

def authenticate(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get the Authorization header
        id_token = request.headers.get('Authorization')
        
        if not id_token:
            return jsonify({"error": "Authorization token is missing"}), 401
        
        try:
            # Check if the token starts with "Bearer " and extract it
            if id_token.startswith("Bearer "):
                id_token = id_token.split("Bearer ")[1]
            
            # Verify the Google token using a custom function
            decoded_token = verify_google_token(id_token)  # Ensure this function is defined elsewhere
            user_id = decoded_token.get('uid')
            
            if not user_id:
                return jsonify({"error": "Invalid token: 'uid' not found"}), 401
            
            # Get or create the user based on the decoded token
            user_data, is_new_user = get_or_create_user(decoded_token)
            
            # Store relevant data in the global `g` object for further processing
            g.user_id = user_id
            g.user_data = user_data
            g.is_new_user = is_new_user
            
            # Continue to the actual route
            return f(*args, **kwargs)
        
        except GoogleAuthError as e:
            return jsonify({"error": f"Invalid token: {str(e)}"}), 401
        
        except Exception as e:
            return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
    
    return decorated_function
    
def save_report(user_id: str, report: dict) -> str:
    """
    Save a report to the Firestore database for a specific user.
    Returns the unique report ID.
    """
    try:
        reports_ref = db.collection('users').document(user_id).collection('reports')
        new_report_ref = reports_ref.document()
        new_report_ref.set(report)
        return new_report_ref.id
    except Exception as e:
        print(f"Error saving report: {e}")
        raise RuntimeError("Failed to save report.")

def get_reports(user_id: str) -> list:
    """
    Retrieve all reports for a specific user.
    Returns a list of report IDs and repository URLs.
    """
    try:
        # Reference to the user's reports in Firestore
       # Reference to the user's reports in Firestore
        reports_ref = db.collection('users').document(user_id).collection('reports')
    
        # Fetching all reports (stream() is used to retrieve documents lazily)
        docs = reports_ref.get()
    
        sorted_docs = sorted(docs, key=lambda doc: doc.create_time, reverse=True)
    
        # Returning reports in the expected format
        return [{"id": doc.id, "data": doc.to_dict()} for doc in sorted_docs]
    except Exception as e:
        print(f"Error retrieving reports: {e}")
        raise RuntimeError("Failed to retrieve reports.")

def get_report_by_id(user_id: str, report_id: str) -> dict:
    """
    Retrieve a specific report by ID for a given user.
    Returns the report data if found, or None if not found.
    """
    try:
        report_ref = db.collection('users').document(user_id).collection('reports').document(report_id)
        doc = report_ref.get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        print(f"Error retrieving report with ID {report_id}: {e}")
        raise RuntimeError("Failed to retrieve the specific report.")
    
def update_user_company(user_id, company):
    user_ref = db.collection('users').document(user_id)
    user_ref.update({"company": company})

def revoke_user_tokens(user_id):
    """
    Revokes all refresh tokens for a user
    Returns True if successful, False otherwise
    """
    try:
        auth.revoke_refresh_tokens(user_id)
        return True
    except Exception:
        return False