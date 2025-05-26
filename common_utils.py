
from urllib.request import Request
from config import API_SECRET

def verify_signature(signature: str,request: Request) -> bool:
    # 具体校验逻辑待实现
    return signature == API_SECRET
