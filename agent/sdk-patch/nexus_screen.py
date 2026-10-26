"""Images from the desktop commands (screen/bin: the H Company desk CLI that Holo4 is trained on).

`screenshot`, `zoom` and `show` print a line `@@attach <image>`; in their harness that line becomes
an image of the tool result, two per call at most. The OpenHands terminal returns text only, so
the model would have seen the path and no picture. The first two images of a command are added to
its observation, as file_editor view adds one: the event keeps them after /tmp/screenshots is
gone, and every later request sends the same bytes, so the prompt cache still matches.

Scaled to at most 1920 px wide and stored as JPEG 85, the defaults of the H Company desktop driver;
the coordinates are 0-1000 of the screen (COORDINATE_SYSTEM in launcher/run.sh), so the scale does
not move them.
"""

import base64
import io
import re

ATTACH = re.compile(r"^@@attach (.+?)\s*$", re.M)
MAX_IMAGES = 2
MAX_WIDTH = 1920


def data_url(path):
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        if image.width > MAX_WIDTH:
            height = round(image.height * MAX_WIDTH / image.width)
            image = image.resize((MAX_WIDTH, height), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def attach(observation):
    from openhands.sdk.llm import ImageContent, TextContent

    added = []
    for path in ATTACH.findall(observation.text)[:MAX_IMAGES]:
        try:
            added.append(ImageContent(image_urls=[data_url(path)]))
        except Exception as error:
            added.append(TextContent(text=f"\n[image {path} not attached: {error}]"))
    if not added:
        return observation
    return observation.model_copy(update={"content": [*observation.content, *added]})


def patch_executor(module):
    call = module.TerminalExecutor.__call__

    def __call__(self, action, conversation=None):
        return attach(call(self, action, conversation))

    module.TerminalExecutor.__call__ = __call__


def patch_observation(module):
    from openhands.sdk.llm import ImageContent

    text_only = module.TerminalObservation.to_llm_content.fget

    def to_llm_content(self):
        content = list(text_only(self))
        content.extend(item for item in self.content if isinstance(item, ImageContent))
        return content

    module.TerminalObservation.to_llm_content = property(to_llm_content)
