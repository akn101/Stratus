# OAuth Setup Guide for Stratus ERP

This guide will walk you through setting up and refreshing OAuth tokens for FreeAgent.

---

## FreeAgent OAuth Token Refresh

Your FreeAgent access token has expired. Follow these steps to refresh it:

### Step 1: Verify Your Credentials

Check that your `.env` file contains these variables:
```bash
FREEAGENT_CLIENT_ID=0cyBcYKxCX9DuMgxcLP1xA
FREEAGENT_CLIENT_SECRET=0xE0ptXFuT0BudLQMpTKAA
FREEAGENT_REFRESH_TOKEN=1Ju_hAuFu1YbhLaCqQi06AMGIG_nzAxUeSRftK-ql
```

### Step 2: Run the Token Refresh Script

```bash
export PATH="$HOME/.local/bin:$PATH"
poetry run python scripts/refresh_freeagent_token.py
```

The script will:
1. ✅ Use your refresh token to get a new access token
2. ✅ Automatically update your `.env` file
3. ✅ Test the new token to make sure it works
4. ✅ Show you the company name it's connected to

### Step 3: Test FreeAgent Jobs

After refreshing, test that FreeAgent jobs work:

```bash
# Test contacts sync
poetry run python -m src.jobs.freeagent_contacts

# Test invoices sync
poetry run python -m src.jobs.freeagent_invoices

# Test categories sync
poetry run python -m src.jobs.freeagent_categories
```

### Expected Output

```
🔄 Refreshing FreeAgent OAuth token...
   Client ID: 0cyBcYKxCX...
   Refresh Token: 1Ju_hAuFu1...

✅ Successfully refreshed tokens!
   New Access Token: 1ACCIHDYkfy3e4uqX8...
   New Refresh Token: 1Ju_hAuFu1YbhLa...

📝 Updating .env file...
✅ .env file updated successfully

🧪 Testing new token...
✅ Token is valid! Connected to: Your Company Name

🎉 Done! You can now run FreeAgent ETL jobs.
```

---

## What if the Refresh Token is Also Expired?

If you get an error like "Invalid refresh token", you'll need to re-authorize:

### Option A: Use the OAuth Flow Script (Recommended)

We can create a simple OAuth flow script that will:
1. Open your browser to FreeAgent
2. You authorize the app
3. It captures the new tokens automatically

### Option B: Manual OAuth Flow

1. **Go to FreeAgent OAuth URL** (I'll generate this for you):
   ```
   https://api.freeagent.com/v2/approve_app?client_id=0cyBcYKxCX9DuMgxcLP1xA&response_type=code&redirect_uri=http://localhost:8000/auth/freeagent/callback
   ```

2. **Authorize the app** - Click "Authorize" in FreeAgent

3. **Copy the authorization code** from the redirect URL:
   ```
   http://localhost:8000/auth/freeagent/callback?code=AUTHORIZATION_CODE_HERE
   ```

4. **Exchange code for tokens** - Run this curl command:
   ```bash
   curl -X POST https://api.freeagent.com/v2/token_endpoint \
     -d "grant_type=authorization_code" \
     -d "code=AUTHORIZATION_CODE_HERE" \
     -d "client_id=0cyBcYKxCX9DuMgxcLP1xA" \
     -d "client_secret=0xE0ptXFuT0BudLQMpTKAA" \
     -d "redirect_uri=http://localhost:8000/auth/freeagent/callback"
   ```

5. **Update .env file** with the new tokens from the response

---

## Automatic Token Refresh (Future Enhancement)

For production, you should implement automatic token refresh in the FreeAgent adapter:

```python
# Add to src/adapters/freeagent.py

class FreeAgentClient:
    def _refresh_token_if_needed(self):
        """Automatically refresh token if it's expired."""
        # Check if token is expired (store expiry time)
        if self.token_expires_at and datetime.now() > self.token_expires_at:
            self._refresh_access_token()

    def _refresh_access_token(self):
        """Refresh the OAuth access token."""
        response = requests.post(
            "https://api.freeagent.com/v2/token_endpoint",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
        )
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data['access_token']

        # Update refresh token if provided
        if 'refresh_token' in token_data:
            self.refresh_token = token_data['refresh_token']

        # Calculate expiry time (tokens typically last 2 hours)
        expires_in = token_data.get('expires_in', 7200)  # Default 2 hours
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)

        logger.info("Successfully refreshed FreeAgent access token")
```

---

## Token Expiration Schedule

- **Access Token**: Expires after **2 hours** of inactivity
- **Refresh Token**: Expires after **6 months** of inactivity
- **Recommendation**: Run jobs at least once per day to keep tokens fresh

---

## Troubleshooting

### Error: "Invalid client credentials"
- Check that `FREEAGENT_CLIENT_ID` and `FREEAGENT_CLIENT_SECRET` are correct
- Verify they match your app in https://dev.freeagent.com/

### Error: "Invalid refresh token"
- Your refresh token has expired (unused for 6 months)
- Follow the "Manual OAuth Flow" steps above to re-authorize

### Error: "Redirect URI mismatch"
- Make sure your FreeAgent app settings have `http://localhost:8000/auth/freeagent/callback` as a valid redirect URI
- Update it at https://dev.freeagent.com/

### Success but jobs still fail
- Restart any running jobs/processes to pick up the new token
- Make sure `.env` file was updated correctly
- Check that `FREEAGENT_ACCESS_TOKEN` in `.env` matches what the script printed

---

## Quick Reference Commands

```bash
# Refresh FreeAgent token
poetry run python scripts/refresh_freeagent_token.py

# Test FreeAgent connection
poetry run python -m src.jobs.freeagent_categories

# View current token (first 20 chars)
grep FREEAGENT_ACCESS_TOKEN .env | cut -c-50

# Check token expiry (manual test)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.freeagent.com/v2/company
```

---

## Next Steps After Token Refresh

1. ✅ Verify all FreeAgent jobs work
2. ✅ Schedule regular job runs (at least daily) to prevent token expiry
3. ✅ Consider implementing automatic refresh in adapter
4. ✅ Set up monitoring to alert on authentication failures
5. ✅ Document token refresh in runbooks

---

Need help? Check the [FreeAgent API documentation](https://dev.freeagent.com/docs/quick_start) or reach out to the team.
