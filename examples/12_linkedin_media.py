"""LinkedIn media — upload an image and publish a post with it attached.

Demonstrates the media surface added to the LinkedIn connector: upload a local
image (Images API: initialize → PUT → asset URN), then publish a post that
references it. Same BYOK token as 10_linkedin_publish.py (self-serve
``w_member_social`` scope). The post is deleted at the end so it doesn't linger.

The same pattern works for documents (``linkedin_upload_document`` → PDF/PPT/DOC)
and video (``linkedin_upload_video`` → MP4).

Prerequisites:
    pip install "toolsconnector[linkedin]"
    export TC_LINKEDIN_CREDENTIALS='your-oauth-access-token'   # openid profile email w_member_social
    export TC_LINKEDIN_IMAGE='/path/to/local/image.png'        # JPG, PNG, or GIF
"""

import json
import os

from toolsconnector.serve import ToolKit

TOKEN = os.environ.get("TC_LINKEDIN_CREDENTIALS", "")
IMAGE = os.environ.get("TC_LINKEDIN_IMAGE", "")
if not TOKEN or not IMAGE:
    raise SystemExit("set TC_LINKEDIN_CREDENTIALS and TC_LINKEDIN_IMAGE first")

kit = ToolKit(connectors=["linkedin"], credentials={"linkedin": TOKEN})


def call(tool_name: str, args: dict):
    raw = kit.execute(tool_name, args)
    return json.loads(raw) if raw else {}


# 1. Identity → the author URN we post as.
author = f"urn:li:person:{call('linkedin_get_profile', {})['sub']}"
print(f"Authenticated as: {author}")

# 2. Upload the image. Returns the asset URN (urn:li:image:...).
image_urn = call("linkedin_upload_image", {"owner": author, "file_path": IMAGE})
print(f"Uploaded: {image_urn}")

# 3. Publish a post with the image attached (CONNECTIONS-only, auto-deleted below).
post = call("linkedin_create_media_post", {
    "author": author,
    "commentary": "Image post via ToolsConnector — please ignore.",
    "media_urn": image_urn,
    "alt_text": "an example image",
    "visibility": "CONNECTIONS",
})
print(f"Posted: {post['id']}")

# 4. Clean up.
call("linkedin_delete_post", {"urn": post["id"]})
print(f"Deleted: {post['id']}")
