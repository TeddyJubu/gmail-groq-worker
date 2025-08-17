#!/usr/bin/env python3
"""
Gmail OAuth Setup Script

This script helps you generate the token.json file needed for cloud deployment.
Run this locally before deploying to the cloud.
"""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def setup_gmail_auth():
    """Generate token.json file for Gmail API access."""
    print("=== Gmail OAuth Setup ===")
    print("This will open your browser to authorize Gmail access.")
    print("Make sure you have client_secret.json in the current directory.\n")
    
    if not os.path.exists("client_secret.json"):
        print("ERROR: client_secret.json not found!")
        print("Please download it from Google Cloud Console:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Enable Gmail API")
        print("3. Create OAuth 2.0 credentials")
        print("4. Download as client_secret.json")
        return False
    
    creds = None
    
    # Check if token already exists and is valid
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if creds and creds.valid:
            print("✓ Valid token.json already exists!")
            return True
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
                print("Starting fresh OAuth flow...")
                creds = None
        
        if not creds:
            print("Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())
        print("✓ token.json created successfully!")
    
    print("\nSetup complete! You can now:")
    print("1. Upload token.json to your cloud service")
    print("2. Set your GROQ_API_KEY environment variable")
    print("3. Deploy your application")
    
    return True

if __name__ == "__main__":
    setup_gmail_auth()
