from pydantic import BaseModel
from typing import Optional


class StreamControlRequest(BaseModel):
    address: Optional[str] = None
    port: Optional[int] = None
