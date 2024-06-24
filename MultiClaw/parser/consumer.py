import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def send_progress(self, event):
        print('SENDING PROGRESS DUNNO HOW')
        await self.send(text_data=json.dumps({
            'progress': event['progress']
        }))