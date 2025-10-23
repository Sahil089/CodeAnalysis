from datetime import datetime
import os
import shutil
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from utils.analysis import  scan_directory
from utils.git_utils import clone_repository
from firebase_service import authenticate, revoke_user_tokens,  get_reports, save_report, verify_google_token, get_or_create_user, db, update_user_company, get_report_by_id
from pathlib import Path

app = Flask(__name__)
CORS(app)


# Configure Flask to ignore the temp directory for reloading


def convert_paths_to_strings(data):
    """Recursively convert all Path objects to strings in a nested structure."""
    if isinstance(data, dict):
        return {k: convert_paths_to_strings(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_paths_to_strings(item) for item in data]
    elif isinstance(data, Path):
        return str(data)
    else:
        return data

@app.route('/login', methods=['POST'])
def login():
    id_token = request.json.get('id_token')
    
    if not id_token:
        return jsonify({"error": "ID token is required"}), 400
    
    try:
        decoded_token = verify_google_token(id_token)
        user_data, is_new_user = get_or_create_user(decoded_token)
        return jsonify({
            "message": "Login successful",
            "user": user_data,
            "is_new_user": is_new_user,
            "user_exists": not is_new_user
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 401

@app.route('/update_company', methods=['POST'])
@authenticate
def update_company():
    company = request.json.get('company')
    
    if not company:
        return jsonify({"error": "Company name is required"}), 400
    
    try:
        update_user_company(g.user_id, company)
        return jsonify({"message": "Company name updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/scan', methods=['POST'])
@authenticate
def scan_repository():
    """API endpoint to scan a GitHub repository and save results to the database."""
    data = request.get_json()
    
    if not data or 'repo_url' not in data:
        return jsonify({'error': 'Repository URL is required'}), 400

    repo_url = data['repo_url']
    
    try:
        # Clone the repository
        repo_path = clone_repository(repo_url)
        print(f"Cloned repository path: {repo_path}")  # Debugging output

        # Perform the scan
        results = scan_directory(repo_path)

        # Convert Path objects in scan results to strings for Firestore compatibility
        results = convert_paths_to_strings(results)
        
        # Generate the report structure
        report = {
            'repository': repo_url,
            'scan_results': results
        }

        # Ensure g.user_id exists, return error if not
        if not hasattr(g, 'user_id'):
            return jsonify({'error': 'User ID not found; authentication required'}), 403

        # Save the report to the database
        report_id = save_report(g.user_id, report)
        
        # Cleanup: delete the cloned repository
        shutil.rmtree(repo_path, ignore_errors=True)

        # Include the report ID in the response
        return jsonify({
            'repository': repo_url,
            'scan_results': results,
            'report_id': report_id
        }), 200

    except Exception as e:
        print(f"Error during repository scan: {e}")
        return jsonify({'error': 'An error occurred during the scan process'}), 500


@app.route('/get_reports', methods=['GET'])
@authenticate
def get_user_reports():
    try:
        # Retrieve all reports for the authenticated user
        reports = get_reports(g.user_id)
        # Construct a JSON response with the report IDs and URLs
        return jsonify({
            "reports": [
                {"id": report["id"], "repo_url": report["data"].get("repository", "Unknown URL")}
                for report in reports
            ]
        }), 200
    except Exception as e:
        print(f"Error retrieving reports for user {g.user_id}: {e}")
        return jsonify({"error": "Failed to retrieve reports"}), 500


@app.route('/get_report/<report_id>', methods=['GET'])
@authenticate
def get_specific_report(report_id):
    try:
        # Retrieve a specific report by report_id for the authenticated user
        report = get_report_by_id(g.user_id, report_id)
        if report:
            return jsonify({"report": report}), 200
        else:
            return jsonify({"error": "Report not found"}), 404
    except Exception as e:
        print(f"Error retrieving report {report_id} for user {g.user_id}: {e}")
        return jsonify({"error": "Failed to retrieve the specific report"}), 500


@app.route('/logout', methods=['POST'])
@authenticate
def logout():
    try:
        # Get the user ID from the global context (set by authenticate decorator)
        user_id = g.user_id
       
        # Revoke all refresh tokens for the user
        revoke_success = revoke_user_tokens(user_id)
       
        # Log the logout event in Firestore (optional)
        try:
            db.collection('users').document(user_id).collection('auth_events').add({
                'type': 'logout',
                'timestamp': datetime.utcnow(),
                'success': revoke_success
            })
        except Exception as e:
            # Don't fail the logout if logging fails
            print(f"Failed to log logout event: {e}")
       
        return jsonify({
            "message": "Logout successful",
            "tokens_revoked": revoke_success
        }), 200
       
    except Exception as e:
        return jsonify({
            "error": f"Logout failed: {str(e)}"
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)