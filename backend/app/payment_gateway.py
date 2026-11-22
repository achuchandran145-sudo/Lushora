"""Razorpay integration helpers. Secrets are read only from server environment."""
import os, json, hmac, hashlib, base64
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

def razorpay_configured():
    return bool(os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))

def create_order(amount_inr:int,receipt:str,notes:dict|None=None):
    if not razorpay_configured(): raise RuntimeError("Razorpay credentials are not configured")
    key=os.environ["RAZORPAY_KEY_ID"];secret=os.environ["RAZORPAY_KEY_SECRET"]
    body={"amount":int(amount_inr)*100,"currency":"INR","receipt":receipt,"notes":notes or {}}
    req=Request("https://api.razorpay.com/v1/orders",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":"Basic "+base64.b64encode((key+":"+secret).encode()).decode()},method="POST")
    try:
        with urlopen(req,timeout=20) as response:return json.loads(response.read().decode())
    except HTTPError as exc:
        detail=exc.read().decode(errors="replace")[:500]
        raise RuntimeError("Razorpay order creation failed: "+detail)
    except URLError as exc:
        raise RuntimeError("Razorpay order creation failed: "+str(exc.reason))

def verify_checkout_signature(order_id:str,payment_id:str,signature:str):
    secret=os.getenv("RAZORPAY_KEY_SECRET","")
    if not secret:return False
    expected=hmac.new(secret.encode(),(order_id+"|"+payment_id).encode(),hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,signature or "")

def verify_webhook_signature(raw_body:bytes,signature:str):
    secret=os.getenv("RAZORPAY_WEBHOOK_SECRET","")
    if not secret:return False
    expected=hmac.new(secret.encode(),raw_body,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,signature or "")


def create_refund(gateway_payment_id:str,amount_inr:int,receipt:str,notes:dict|None=None):
    if not razorpay_configured():raise RuntimeError("Razorpay credentials are not configured")
    key=os.environ["RAZORPAY_KEY_ID"];secret=os.environ["RAZORPAY_KEY_SECRET"]
    body={"amount":int(amount_inr)*100,"notes":notes or {},"receipt":receipt}
    req=Request("https://api.razorpay.com/v1/payments/"+gateway_payment_id+"/refund",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":"Basic "+base64.b64encode((key+":"+secret).encode()).decode()},method="POST")
    try:
        with urlopen(req,timeout=20) as response:return json.loads(response.read().decode())
    except HTTPError as exc:raise RuntimeError("Razorpay refund failed: "+exc.read().decode(errors="replace")[:500])
    except URLError as exc:raise RuntimeError("Razorpay refund failed: "+str(exc.reason))
