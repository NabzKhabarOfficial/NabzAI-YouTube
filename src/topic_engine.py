import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load_topics(): return json.loads((ROOT/'content/topics.json').read_text(encoding='utf-8'))
def load_state(): return json.loads((ROOT/'content/published.json').read_text(encoding='utf-8'))
def choose_topic():
    used=set(load_state().get('published',[]))|set(load_state().get('reserved',[]))
    for topic in load_topics():
        if topic['id'] not in used: return topic
    raise RuntimeError('No unused topics remain.')
