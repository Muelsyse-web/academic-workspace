"""Bound request bytes before the multipart parser can spool them to disk."""
from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse


class RequestLimits:
    def __init__(self, app, max_bytes=None):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        maximum = self.max_bytes if self.max_bytes is not None else (4*1024**3+33*1024**2 if scope['path']=='/api/v1/restore' else 256*1024**2)
        headers = dict(scope['headers'])
        try:
            declared = int(headers.get(b'content-length',b'0'))
        except ValueError:
            return await JSONResponse({'detail':'Invalid content length'},400)(scope,receive,send)
        if declared > maximum:
            return await JSONResponse({'detail':'Request exceeds upload limit; import smaller batches'},413)(scope,receive,send)
        received = 0
        exceeded = False
        replaced = False
        async def bounded_receive():
            nonlocal received, exceeded
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body',b''))
                if received > maximum:
                    exceeded = True
                    raise MultiPartException('Request body budget exceeded')
            return message
        async def bounded_send(message):
            nonlocal replaced
            if exceeded:
                if not replaced and message['type'] == 'http.response.start':
                    replaced = True
                    await JSONResponse({'detail':'Batch exceeds request size limit; import smaller batches'},413)(scope,receive,send)
                return
            await send(message)
        await self.app(scope,bounded_receive,bounded_send)
