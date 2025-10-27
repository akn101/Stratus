#!/usr/bin/env python3
"""
FreeAgent OAuth Token Refresh Script

This script helps you refresh your FreeAgent OAuth access token using the refresh token.
Run this when your FreeAgent access token expires.

Usage:
    poetry run python scripts/refresh_freeagent_token.py
"""

import os
import sys
import requests
from dotenv import load_dotenv, set_key
from pathlib import Path

# Load environment variables
load_dotenv()

def refresh_freeagent_token():
    """Refresh FreeAgent OAuth access token using refresh token."""

    # Get credentials from environment
    client_id = os.getenv('FREEAGENT_CLIENT_ID')
    client_secret = os.getenv('FREEAGENT_CLIENT_SECRET')
    refresh_token = os.getenv('FREEAGENT_REFRESH_TOKEN')

    if not all([client_id, client_secret, refresh_token]):
        print("❌ Error: Missing FreeAgent credentials in .env file")
        print("\nRequired environment variables:")
        print("  - FREEAGENT_CLIENT_ID")
        print("  - FREEAGENT_CLIENT_SECRET")
        print("  - FREEAGENT_REFRESH_TOKEN")
        sys.exit(1)

    print("🔄 Refreshing FreeAgent OAuth token...")
    print(f"   Client ID: {client_id[:10]}...")
    print(f"   Refresh Token: {refresh_token[:10]}...")

    # Make token refresh request
    try:
        response = requests.post(
            "https://api.freeagent.com/v2/token_endpoint",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )

        response.raise_for_status()
        token_data = response.json()

        # Extract new tokens
        new_access_token = token_data.get('access_token')
        new_refresh_token = token_data.get('refresh_token')

        if not new_access_token:
            print("❌ Error: No access token in response")
            print(f"Response: {token_data}")
            sys.exit(1)

        print("\n✅ Successfully refreshed tokens!")
        print(f"   New Access Token: {new_access_token[:20]}...")
        if new_refresh_token:
            print(f"   New Refresh Token: {new_refresh_token[:20]}...")

        # Update .env file
        env_path = Path('.env')
        if env_path.exists():
            print("\n📝 Updating .env file...")
            set_key(env_path, 'FREEAGENT_ACCESS_TOKEN', new_access_token)
            if new_refresh_token:
                set_key(env_path, 'FREEAGENT_REFRESH_TOKEN', new_refresh_token)
            print("✅ .env file updated successfully")
        else:
            print("\n⚠️  Warning: .env file not found, please update manually:")
            print(f"   FREEAGENT_ACCESS_TOKEN={new_access_token}")
            if new_refresh_token:
                print(f"   FREEAGENT_REFRESH_TOKEN={new_refresh_token}")

        # Test the new token
        print("\n🧪 Testing new token...")
        test_response = requests.get(
            "https://api.freeagent.com/v2/company",
            headers={
                "Authorization": f"Bearer {new_access_token}",
                "User-Agent": "Stratus-ERP/1.0"
            }
        )

        if test_response.status_code == 200:
            company_data = test_response.json()
            company_name = company_data.get('company', {}).get('name', 'Unknown')
            print(f"✅ Token is valid! Connected to: {company_name}")
        else:
            print(f"⚠️  Warning: Token test failed with status {test_response.status_code}")

        print("\n🎉 Done! You can now run FreeAgent ETL jobs.")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error refreshing token: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Status Code: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 70)
    print("FreeAgent OAuth Token Refresh")
    print("=" * 70)
    refresh_freeagent_token()
