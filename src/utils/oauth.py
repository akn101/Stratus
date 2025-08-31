"""
OAuth utilities for API integrations that require OAuth flow.

Provides OAuth token management, refresh logic, and authorization URL generation.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urljoin

import requests
from requests.exceptions import HTTPError, RequestException

logger = logging.getLogger(__name__)


class OAuthTokenError(Exception):
    """Error with OAuth token operations."""
    pass


class OAuthConfig:
    """OAuth configuration for an API integration."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        authorization_base_url: str,
        token_url: str,
        scope: str | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.authorization_base_url = authorization_base_url
        self.token_url = token_url
        self.scope = scope


class OAuthToken:
    """OAuth token with automatic refresh capabilities."""
    
    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: datetime | None = None,
        token_type: str = "Bearer",
        scope: str | None = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.token_type = token_type
        self.scope = scope
        
    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 5min buffer)."""
        if not self.expires_at:
            return False
        return datetime.now(UTC) >= (self.expires_at - timedelta(minutes=5))
    
    @property
    def authorization_header(self) -> str:
        """Get authorization header value."""
        return f"{self.token_type} {self.access_token}"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert token to dictionary for storage."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "token_type": self.token_type,
            "scope": self.scope,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthToken":
        """Create token from dictionary."""
        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])
            
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope"),
        )


class OAuthManager:
    """OAuth manager for handling token lifecycle."""
    
    def __init__(self, config: OAuthConfig):
        self.config = config
        self._token: OAuthToken | None = None
    
    def get_authorization_url(self, state: str | None = None) -> str:
        """Generate authorization URL for OAuth flow."""
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
        }
        
        if self.config.scope:
            params["scope"] = self.config.scope
        if state:
            params["state"] = state
            
        return f"{self.config.authorization_base_url}?{urlencode(params)}"
    
    def exchange_code_for_token(self, code: str) -> OAuthToken:
        """Exchange authorization code for access token."""
        data = {
            "redirect_uri": self.config.redirect_uri,
            "code": code,
            "grant_type": "authorization_code",
            # Some providers accept/require client credentials in body as well
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        
        # FreeAgent uses HTTP Basic Auth with client_id:client_secret
        auth = (self.config.client_id, self.config.client_secret)
        
        try:
            # Debug logging for exchange_code_for_token
            print(f"Debug: POST {self.config.token_url}")
            print(f"Debug: Auth username (client_id): {auth[0]}")
            print(f"Debug: Auth password length: {len(auth[1])}")
            print(f"Debug: POST data: {data}")
            
            response = requests.post(
                self.config.token_url,
                data=data,
                auth=auth,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()
            
            expires_at = None
            if "expires_in" in token_data:
                expires_at = datetime.now(UTC) + timedelta(seconds=token_data["expires_in"])
            
            token = OAuthToken(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_at=expires_at,
                token_type=token_data.get("token_type", "Bearer"),
                scope=token_data.get("scope"),
            )
            
            self._token = token
            logger.info("Successfully exchanged authorization code for access token")
            return token
            
        except (HTTPError, RequestException, KeyError) as e:
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = f" - Response: {e.response.text}"
                except:
                    pass
            logger.error(f"Failed to exchange code for token: {e}{error_detail}")
            raise OAuthTokenError(f"Token exchange failed: {e}{error_detail}") from e
    
    def refresh_token(self, token: OAuthToken) -> OAuthToken:
        """Refresh an expired access token."""
        if not token.refresh_token:
            raise OAuthTokenError("No refresh token available")
        
        data = {
            "refresh_token": token.refresh_token,
            "grant_type": "refresh_token",
            # Mirror client credentials in body as well
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        
        # FreeAgent uses HTTP Basic Auth with client_id:client_secret
        auth = (self.config.client_id, self.config.client_secret)
        
        try:
            response = requests.post(
                self.config.token_url,
                data=data,
                auth=auth,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()
            
            expires_at = None
            if "expires_in" in token_data:
                expires_at = datetime.now(UTC) + timedelta(seconds=token_data["expires_in"])
            
            new_token = OAuthToken(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token", token.refresh_token),
                expires_at=expires_at,
                token_type=token_data.get("token_type", "Bearer"),
                scope=token_data.get("scope"),
            )
            
            self._token = new_token
            logger.info("Successfully refreshed access token")
            return new_token
            
        except (HTTPError, RequestException, KeyError) as e:
            logger.error(f"Failed to refresh token: {e}")
            raise OAuthTokenError(f"Token refresh failed: {e}") from e
    
    def get_valid_token(self, token: OAuthToken) -> OAuthToken:
        """Get a valid token, refreshing if necessary."""
        if not token.is_expired:
            return token
        
        if not token.refresh_token:
            raise OAuthTokenError("Token expired and no refresh token available")
        
        logger.info("Token expired, refreshing...")
        return self.refresh_token(token)


# FreeAgent OAuth configuration
FREEAGENT_OAUTH_CONFIG = OAuthConfig(
    authorization_base_url="https://api.freeagent.com/v2/approve_app",
    token_url="https://api.freeagent.com/v2/token_endpoint",
    client_id="",  # Will be set from environment
    client_secret="",  # Will be set from environment  
    redirect_uri="",  # Will be set from environment
    scope=None,  # FreeAgent doesn't use scopes
)
