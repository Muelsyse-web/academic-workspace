"""Exclude restore from in-flight HTTP work, including validation before DB writes."""
import threading
from starlette.responses import JSONResponse


class RequestActivity:
    def __init__(self,app):
        self.app=app
        self.lock=threading.Lock()
        self.active=0
        self.restoring=False

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not scope['path'].startswith('/api/') or scope['path']=='/api/v1/health':
            return await self.app(scope,receive,send)
        restore=scope['path']=='/api/v1/restore' and scope['method']=='POST'
        with self.lock:
            denied=self.restoring or (restore and self.active>0)
            if not denied:
                if restore:self.restoring=True
                else:self.active+=1
        if denied:
            return await JSONResponse({'detail':'Library is busy. Wait for current requests or restore to finish, then retry.'},409)(scope,receive,send)
        try:
            # This covers response streaming and BackgroundTask completion too.
            await self.app(scope,receive,send)
        finally:
            with self.lock:
                if restore:self.restoring=False
                else:self.active-=1
