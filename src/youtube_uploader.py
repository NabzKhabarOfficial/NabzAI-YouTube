import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
SCOPES=['https://www.googleapis.com/auth/youtube.upload']
def upload_video(video_path,title,description,tags,token_json,privacy_status='private',category_id='27'):
    data=json.loads(token_json) if isinstance(token_json,str) else token_json
    creds=Credentials.from_authorized_user_info(data,SCOPES)
    youtube=build('youtube','v3',credentials=creds,cache_discovery=False)
    body={'snippet':{'title':title[:100],'description':description[:5000],'tags':tags[:500],'categoryId':category_id},'status':{'privacyStatus':privacy_status,'selfDeclaredMadeForKids':False}}
    req=youtube.videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(str(video_path),mimetype='video/mp4',resumable=True))
    response=None
    while response is None:
        _,response=req.next_chunk()
    if not response or not response.get('id'): raise RuntimeError('YouTube upload returned no video id.')
    return response['id']
