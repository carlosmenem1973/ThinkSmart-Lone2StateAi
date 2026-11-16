import msal, httpx
from app.core.config import settings

SCOPES=["User.Read","Mail.Read"]

def msal_app():
    if not settings.microsoft_client_id or not settings.microsoft_client_secret:
        raise RuntimeError("Configure Microsoft Entra app credentials")
    return msal.ConfidentialClientApplication(settings.microsoft_client_id,
        authority=f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}",
        client_credential=settings.microsoft_client_secret)

def auth_url(state: str):
    return msal_app().get_authorization_request_url(SCOPES, state=state, redirect_uri=settings.microsoft_redirect_uri)

def exchange_code(code: str):
    return msal_app().acquire_token_by_authorization_code(code, scopes=SCOPES, redirect_uri=settings.microsoft_redirect_uri)

async def list_recent_messages(access_token: str, top: int=25):
    headers={"Authorization":f"Bearer {access_token}"}
    params={"$top":min(top,100),"$select":"id,subject,from,receivedDateTime,bodyPreview","$orderby":"receivedDateTime desc"}
    async with httpx.AsyncClient(timeout=30) as client:
        r=await client.get("https://graph.microsoft.com/v1.0/me/messages",headers=headers,params=params)
        r.raise_for_status(); return r.json().get("value",[])
