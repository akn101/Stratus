#!/usr/bin/env python3
"""
FreeAgent OAuth Setup Helper

This script helps you set up OAuth authentication for FreeAgent integration.
It will generate the authorization URL and help you exchange the authorization code for tokens.

Usage:
    python scripts/freeagent_oauth_setup.py

Prerequisites:
    1. Create a FreeAgent OAuth app at https://dev.freeagent.com/
    2. Set FREEAGENT_CLIENT_ID and FREEAGENT_CLIENT_SECRET in your .env file
"""

import os
import sys
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from urllib.parse import urlparse, parse_qs

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.oauth import OAuthConfig, OAuthManager
from src.config.loader import load_dotenv

def main():
    """Main OAuth setup flow."""
    print("FreeAgent OAuth Setup Helper")
    print("=" * 40)
    
    # Load environment variables
    load_dotenv()
    
    # Get OAuth credentials
    client_id = os.getenv("FREEAGENT_CLIENT_ID")
    client_secret = os.getenv("FREEAGENT_CLIENT_SECRET") 
    redirect_uri = os.getenv("FREEAGENT_REDIRECT_URI", "http://localhost:8000/auth/freeagent/callback")
    
    if not client_id or not client_secret:
        print("❌ Error: FREEAGENT_CLIENT_ID and FREEAGENT_CLIENT_SECRET must be set in .env file")
        print("\nTo set these up:")
        print("1. Go to https://dev.freeagent.com/")
        print("2. Create a new OAuth application")
        print("3. Set the redirect URI to:", redirect_uri)
        print("4. Add the following to your .env file:")
        print(f"   FREEAGENT_CLIENT_ID=your_client_id")
        print(f"   FREEAGENT_CLIENT_SECRET=your_client_secret")
        print(f"   FREEAGENT_REDIRECT_URI={redirect_uri}")
        return 1
    
    # Create OAuth manager
    config = OAuthConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        authorization_base_url="https://api.freeagent.com/v2/approve_app",
        token_url="https://api.freeagent.com/v2/token_endpoint",
    )
    
    oauth_manager = OAuthManager(config)
    
    print(f"✅ OAuth configured successfully")
    print(f"Client ID: {client_id}")
    print(f"Redirect URI: {redirect_uri}")
    print()
    
    # Optional: start a local callback server if redirect_uri points to localhost
    received_code: dict[str, str | None] = {"code": None, "error": None}

    def start_local_server():
        parsed = urlparse(redirect_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8000
        path = parsed.path or "/auth/freeagent/callback"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A003
                # Quiet the default HTTPServer logging
                return

            def do_GET(self):  # noqa: N802
                if self.path.startswith(path):
                    qs = parse_qs(urlparse(self.path).query)
                    received_code["code"] = (qs.get("code", [None])[0])
                    received_code["error"] = (qs.get("error", [None])[0])
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h3>FreeAgent authorization received.</h3>\n"
                        b"<p>You may now return to the terminal.</p></body></html>"
                    )
                else:
                    self.send_response(404)
                    self.end_headers()

        # Bind to all interfaces for robustness (supports 127.0.0.1 and localhost)
        server = HTTPServer(("", port), Handler)
        # Poll the server until we receive a valid callback or time out
        import time as _t
        deadline = _t.time() + 180  # up to 3 minutes
        try:
            while _t.time() < deadline and not (received_code["code"] or received_code["error"]):
                try:
                    server.timeout = 1.0
                    server.handle_request()
                except Exception:
                    # Ignore transient connection resets / partial requests
                    continue
        finally:
            try:
                server.server_close()
            except Exception:
                pass

    should_listen = redirect_uri.startswith("http://localhost") or redirect_uri.startswith("http://127.0.0.1")
    listener_thread: Thread | None = None
    if should_listen:
        print(f"Starting local callback server for redirect URI: {redirect_uri}")
        listener_thread = Thread(target=start_local_server, daemon=True)
        listener_thread.start()

    # Step 1: Generate authorization URL
    state = "stratus-erp-setup"
    auth_url = oauth_manager.get_authorization_url(state)
    
    print("Step 1: Authorize the application")
    print("-" * 35)
    print("Open this URL in your browser to authorize the application:")
    print()
    print(auth_url)
    print()
    # Try to open the user's default browser automatically
    try:
        if webbrowser.open(auth_url, new=2):  # new=2 → open in a new tab, if possible
            print("(Opened the authorization URL in your default browser)")
        else:
            print("(If it didn’t open automatically, copy the URL above into your browser)")
    except Exception as e:
        print(f"(Couldn’t open the browser automatically: {e}. Copy the URL above into your browser.)")
    print()
    print("After authorization, you'll be redirected to your redirect URI with a 'code' parameter.")
    print("Copy the authorization code from the URL.")
    print()
    
    # Step 2: Exchange code for token
    auth_code = None
    if should_listen:
        print("Waiting for authorization redirect ...")
        # Poll for a short time (e.g., 120 seconds)
        import time as _time

        for _ in range(240):  # ~120 seconds at 0.5s
            if received_code["code"] or received_code["error"]:
                break
            _time.sleep(0.5)
        if received_code["error"]:
            print(f"❌ Authorization error: {received_code['error']}")
            return 1
        auth_code = (received_code["code"] or "").strip()
        if not auth_code:
            print("❌ Timed out waiting for authorization. You can re-run and paste the code manually.")
    if not auth_code:
        auth_code = input("Enter the authorization code: ").strip()
    
    if not auth_code:
        print("❌ No authorization code provided")
        return 1
    
    try:
        print("Exchanging authorization code for access token...")
        print(f"Debug: Using Client ID: {client_id}")
        print(f"Debug: Client Secret length: {len(client_secret)} chars")
        print(f"Debug: Redirect URI: {redirect_uri}")
        print(f"Debug: Authorization code length: {len(auth_code)} chars")
        token = oauth_manager.exchange_code_for_token(auth_code)
        
        print("✅ Success! OAuth tokens obtained")
        print()
        
        # Auto-update .env file
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            env_content = env_file.read_text()
            
            # Update access token
            if "FREEAGENT_ACCESS_TOKEN=" in env_content:
                import re
                env_content = re.sub(
                    r'FREEAGENT_ACCESS_TOKEN=.*',
                    f'FREEAGENT_ACCESS_TOKEN={token.access_token}',
                    env_content
                )
            else:
                env_content += f"\nFREEAGENT_ACCESS_TOKEN={token.access_token}\n"
            
            # Update refresh token if available
            if token.refresh_token:
                if "FREEAGENT_REFRESH_TOKEN=" in env_content:
                    env_content = re.sub(
                        r'FREEAGENT_REFRESH_TOKEN=.*',
                        f'FREEAGENT_REFRESH_TOKEN={token.refresh_token}',
                        env_content
                    )
                else:
                    env_content += f"FREEAGENT_REFRESH_TOKEN={token.refresh_token}\n"
            
            # Write back to .env
            env_file.write_text(env_content)
            print("✅ Automatically updated .env file with OAuth tokens")
        else:
            print("⚠️  .env file not found, please add these manually:")
            print(f"FREEAGENT_ACCESS_TOKEN={token.access_token}")
            if token.refresh_token:
                print(f"FREEAGENT_REFRESH_TOKEN={token.refresh_token}")
        
        print()
        print("🚀 Your FreeAgent integration is now configured!")
        print("You can now run: make run")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error exchanging code for token: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
