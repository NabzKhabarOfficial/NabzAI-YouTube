from __future__ import annotations

import os
from datetime import datetime, timezone

STORIES = [
    ("The Last Train Home", "A missed train leads a tired traveler to an unexpected reunion.", "rainy train platform", "an old photograph"),
    ("The Empty Chair", "A stranger sits in the chair someone has kept empty for years.", "quiet cafe at closing time", "a faded photograph"),
    ("The Blue Umbrella", "Two strangers share an umbrella and discover they are looking for the same person.", "busy street during a storm", "a handwritten address"),
    ("The Unsent Message", "A phone found on a park bench contains one message that changes two lives.", "city park before dawn", "an unsent voice message"),
    ("The Locked Room", "A daughter returns home and finds a room her family never allowed her to enter.", "old family house at sunset", "a wooden key"),
    ("The Photograph", "A photographer recognizes a face in an old picture taken decades earlier.", "small photography studio", "a black-and-white photograph"),
    ("The Night Driver", "A taxi driver makes one final trip and realizes his passenger knows his past.", "quiet city road at midnight", "a worn letter"),
    ("The Red Scarf", "A forgotten scarf leads two people back to the moment they first met.", "winter bus stop", "a red wool scarf"),
    ("The Lighthouse", "Two siblings return to a lighthouse after years apart to fulfill their mother's final wish.", "coastal lighthouse at dusk", "an old compass"),
    ("The Last Cup", "A cafe owner prepares one final cup for a customer who has not returned in twenty years.", "small cafe before sunrise", "a handwritten recipe"),
]

DIALOGUES = [
    [("woman", "I did not expect you here."), ("man", "Neither did I."), ("woman", "Then why did you come?"), ("man", "Because this could not wait any longer.")],
    [("woman", "That was always his chair."), ("man", "Then maybe someone should sit beside you."), ("woman", "You do not know what happened."), ("man", "Tell me.")],
    [("man", "You are looking for someone."), ("woman", "How did you know?"), ("man", "Because I have been looking too."), ("woman", "Then we should talk.")],
    [("woman", "You found the phone."), ("man", "It was still ringing."), ("woman", "Did you hear the message?"), ("man", "Only the part that said my name.")],
    [("man", "Why is this room locked?"), ("woman", "Because some memories are not ready."), ("man", "What is behind the door?"), ("woman", "The truth we avoided.")],
    [("woman", "Where did you get that photograph?"), ("man", "I took it a long time ago."), ("woman", "Then you knew my family."), ("man", "I knew more than I ever told you.")],
    [("man", "Where should I take you?"), ("woman", "You already know."), ("man", "I have not been there in years."), ("woman", "Neither have I.")],
    [("woman", "You kept it."), ("man", "I could never throw it away."), ("woman", "I thought you forgot."), ("man", "I remembered every winter.")],
    [("man", "Why did she leave the compass here?"), ("woman", "So we would know where to look."), ("man", "Look for what?"), ("woman", "The place she wanted us to forgive.")],
    [("woman", "You still remember the recipe."), ("man", "I remember who taught me."), ("woman", "Then make one more cup."), ("man", "For both of us.")],
]


def _slot() -> int:
    raw = os.getenv("NABZ_STORY_SLOT", "")
    if raw.isdigit():
        return int(raw) % len(STORIES)
    now = datetime.now(timezone.utc)
    return ((now.timetuple().tm_yday * 12) + now.hour // 2) % len(STORIES)


def load_story(slot: int | None = None) -> dict:
    index = _slot() if slot is None else slot % len(STORIES)
    title, logline, location, prop = STORIES[index]
    dialogue = DIALOGUES[index]
    characters = {
        "man": "Fictional adult man in his early 30s, short dark hair, natural light stubble, charcoal coat, realistic human face and proportions.",
        "woman": "Fictional adult woman in her late 20s, shoulder-length dark brown hair, beige sweater, expressive natural eyes, realistic human face and proportions.",
    }
    actions = [
        f"Establish {location}. The two characters approach while carrying or noticing {prop}.",
        f"The woman notices {prop} and reacts with restrained emotion while the man watches quietly.",
        f"The man places {prop} between them and explains why he brought it. The woman hesitates before responding.",
        f"Both characters finally face the truth connected to {prop} and share a quiet, hopeful look as the scene ends.",
    ]
    scenes = []
    for i, (speaker, line) in enumerate(dialogue, 1):
        scenes.append({
            "id": i,
            "seconds": 3.5,
            "dialogue": [(speaker, line)],
            "prompt": (
                "Photorealistic live-action cinematic short film. Same fictional adult man and woman from the character bible, "
                "exact identities, faces, hair and wardrobe across every scene. " + actions[i - 1] + " "
                "Natural human acting, realistic skin texture, believable hands and eyes, subtle breathing and blinking, "
                "physically plausible lighting and movement, 35mm or 50mm lens, shallow depth of field, restrained film color grade. "
                "No cartoon, no anime, no CGI look, no plastic skin, no duplicate people, no text, no subtitles, no watermark."
            ),
        })
    return {"title": title, "logline": logline, "language": "en-US", "characters": characters, "dialogue": dialogue, "scenes": scenes, "slot": index}
