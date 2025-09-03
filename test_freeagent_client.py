#!/usr/bin/env python3
"""Test FreeAgent client directly."""

import os
import sys
sys.path.append('src')
from dotenv import load_dotenv

# Load environment
load_dotenv()

from src.adapters.freeagent import create_freeagent_client
from src.jobs.freeagent_contacts import transform_contact, run_freeagent_contacts_etl

def main():
    token = os.getenv('FREEAGENT_ACCESS_TOKEN')
    if not token:
        print("No FreeAgent token found")
        return
        
    print(f'Testing with token: {token[:10]}...')
    
    try:
        print("Creating FreeAgent client...")
        client = create_freeagent_client(access_token=token)
        print("Client created successfully")
        
        print("Testing contacts API call...")
        contacts = client.get_contacts()
        print(f'Retrieved {len(contacts)} contacts')
        
        if contacts:
            print("Sample contact structure:")
            contact = contacts[0]
            print(f"Contact type: {type(contact)}")
            if isinstance(contact, dict):
                print(f"Sample keys: {list(contact.keys())[:5]}")
            else:
                print(f"Contact is not a dict: {contact}")
                
            print("Testing transform_contact...")
            transformed = transform_contact(contact)
            print(f"Transformed successfully: {type(transformed)}")
            
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()