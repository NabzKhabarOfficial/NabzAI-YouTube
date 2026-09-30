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

# Six-shot rhythm: establish → introduce → breathe → reveal → reaction → resolve.
# Only four shots carry dialogue; the silent beats give the film visual breathing room
# without adding extra TTS cost.
DIALOGUE_SCENES = (0, 1, 3, 4)


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
        f"SHOT 1 — Establish {location}. Begin with a wide environmental view, then make a slow physical dolly toward the two characters as they notice {prop}. Keep both actors naturally grounded in the same space.",
        f"SHOT 2 — Stay in the same location and continue the action. Move into a medium two-shot with a gentle lateral camera move. One character reaches toward {prop} while the other watches, creating a clear visual continuation from the previous shot.",
        f"SHOT 3 — A quiet visual beat. Cut to a close detail of {prop} in the characters' hands, then rack focus toward their faces. Use subtle hand movement, breathing and eye movement; no dialogue is required.",
        f"SHOT 4 — Return to a medium close-up of both characters. The man places {prop} between them and explains why it matters. Use a restrained push-in while the woman reacts naturally, preserving the exact identity and wardrobe.",
        f"SHOT 5 — Emotional reaction. Hold a close two-shot, then make a slow arc around the pair as they finally understand what {prop} means. Their expressions change subtly rather than becoming exaggerated.",
        f"SHOT 6 — Resolution. Pull back into a wider composition as both characters share a quiet, hopeful look and the physical action settles. End on a clean cinematic image that could naturally cut to black.",
    ]
    scenes = []
    dialogue_iter = iter(dialogue)
    for i, action in enumerate(actions):
        line_pair = [next(dialogue_iter)] if i in DIALOGUE_SCENES else []
        prompt = (
            "Photorealistic live-action cinematic short film. Use the supplied character reference as the identity anchor. "
            "The exact same fictional adult man and woman must remain the same people in every shot: identical faces, hair, age, body proportions and wardrobe. "
            "Do not introduce any additional people or change the location, time of day, wardrobe or facial identity. "
            + action + " "
            f"Maintain strict location continuity: all six shots must stay in the exact same {location}, with the same time of day, weather, background architecture and practical lighting. "
            "Never replace the setting with a studio, generic backdrop or different location. "
            "Maintain continuity with the previous shot and create physically plausible movement rather than a static slideshow. "
            "Natural human acting, realistic skin pores, believable hands and eyes, subtle breathing and blinking, "
            "physically plausible lighting and motion, 35mm or 50mm lens, shallow depth of field, restrained film color grade, "
            "realistic environmental detail and continuous live-action cinematography. "
            "No cartoon, anime, CGI look, plastic skin, wax face, duplicate person, identity drift, different hairstyle, "
            "different clothing, extra limbs, malformed hands, text, subtitles, watermark or logo."
        )
        scenes.append({
            "id": i + 1,
            "seconds": 4.0,
            "dialogue": line_pair,
            "prompt": prompt,
        })
    return {
        "title": title,
        "logline": logline,
        "language": "en-US",
        "characters": characters,
        "dialogue": dialogue,
        "scenes": scenes,
        "slot": index,
    }
