import os
import shutil
import subprocess
import time

def clone_repository(repo_url, branch='main'):
    repo_name = os.path.basename(repo_url).replace('.git', '')
    upload_dir = os.path.join('upload', repo_name)
    
    def remove_directory_with_retry(path, max_retries=3, delay=1):
        """Remove directory with retry mechanism for Windows file locks"""
        for attempt in range(max_retries):
            try:
                if os.path.exists(path):
                    print(f"Attempting to remove directory '{path}' (attempt {attempt + 1})")
                    # First, ensure we have write permissions on all files
                    for root, dirs, files in os.walk(path):
                        for dir in dirs:
                            try:
                                os.chmod(os.path.join(root, dir), 0o777)
                            except Exception as e:
                                print(f"Warning: Could not change permissions for directory {dir}: {e}")
                        for file in files:
                            try:
                                os.chmod(os.path.join(root, file), 0o777)
                            except Exception as e:
                                print(f"Warning: Could not change permissions for file {file}: {e}")
                    
                    # Then remove the directory
                    shutil.rmtree(path, ignore_errors=True)
                    
                    # Verify removal
                    if not os.path.exists(path):
                        print(f"Successfully removed directory '{path}'")
                        return True
                    
                time.sleep(delay)
            except Exception as e:
                print(f"Error removing directory (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
                else:
                    raise Exception(f"Failed to remove directory after {max_retries} attempts: {e}")
        return False

    def ensure_directory_empty(path):
        """Ensure the directory is empty and ready for cloning"""
        try:
            # Create parent directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Remove existing directory if it exists
            if os.path.exists(path):
                remove_directory_with_retry(path)
            
            # Create fresh empty directory
            os.makedirs(path, exist_ok=True)
            print(f"Created fresh directory at '{path}'")
            return True
        except Exception as e:
            print(f"Error preparing directory: {e}")
            return False

    def execute_git_command(command, error_message):
        """Execute a git command with proper error handling"""
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"{error_message}: {e}")
            print(f"Command output: {e.output if hasattr(e, 'output') else 'No output'}")
            raise

    try:
        # Ensure we start with a clean directory
        if not ensure_directory_empty(upload_dir):
            raise Exception("Failed to prepare directory for cloning")

        # Attempt to clone the repository with the specified branch
        print(f"Attempting to clone branch '{branch}'")
        try:
            execute_git_command(
                ["git", "clone", "--branch", branch, "--single-branch", repo_url, upload_dir],
                f"Failed to clone branch '{branch}'"
            )
            print(f"Successfully cloned repository to {upload_dir} with branch '{branch}'")
            return upload_dir
            
        except subprocess.CalledProcessError:
            print(f"Branch '{branch}' not found or failed to clone. Detecting available branches...")
            
            # Get list of available branches
            result = execute_git_command(
                ["git", "ls-remote", "--heads", repo_url],
                "Failed to list remote branches"
            )
            
            branches = [line.split('/')[-1] for line in result.stdout.strip().split('\n')]
            print(f"Available branches: {branches}")
            
            # Try each available branch
            for fallback_branch in branches:
                try:
                    # Ensure directory is clean before trying new branch
                    ensure_directory_empty(upload_dir)
                    
                    print(f"Attempting to clone branch '{fallback_branch}'")
                    execute_git_command(
                        ["git", "clone", "--branch", fallback_branch, "--single-branch", repo_url, upload_dir],
                        f"Failed to clone branch '{fallback_branch}'"
                    )
                    print(f"Successfully cloned branch '{fallback_branch}'")
                    return upload_dir
                    
                except subprocess.CalledProcessError as e:
                    print(f"Failed to clone branch '{fallback_branch}': {e}")
            
            raise Exception("Failed to clone any branch.")
            
    except Exception as e:
        print(f"Fatal error during clone operation: {e}")
        # Clean up failed clone attempt
        if os.path.exists(upload_dir):
            try:
                remove_directory_with_retry(upload_dir)
            except Exception as cleanup_error:
                print(f"Warning: Failed to clean up directory after error: {cleanup_error}")
        return None
