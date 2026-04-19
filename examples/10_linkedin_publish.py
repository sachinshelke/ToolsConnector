"""LinkedIn publish — round-trip post → read → react → delete.

This example demonstrates the LinkedIn connector against a real LinkedIn
account. It posts a clearly-labelled test update to your network feed
(visibility=CONNECTIONS, not PUBLIC), reads it back, adds a LIKE, and
deletes it.

Prerequisites:
    pip install "toolsconnector[linkedin]"
    export TC_LINKEDIN_CREDENTIALS='your-oauth-access-token'

How to get the token:
    ToolsConnector is BYOK (bring-your-own-key). Get a LinkedIn OAuth 2.0
    access token from your own application's auth flow, your secrets
    manager, or — for one-off testing — any OAuth client tool. The token
    needs scopes: `openid profile email w_member_social`.

    See https://www.linkedin.com/developers/apps for LinkedIn's
    developer portal.
"""

import os

from toolsconnector.serve import ToolKit

TOKEN = os.environ.get("TC_LINKEDIN_CREDENTIALS", "")
if not TOKEN:
    raise SystemExit("set TC_LINKEDIN_CREDENTIALS env var first")

kit = ToolKit(connectors=["linkedin"], credentials={"linkedin": TOKEN})

# 1. Identity — get the URN we need to post as.
profile = kit.execute("linkedin_get_profile", {})
author_urn = f"urn:li:person:{profile['sub']}"
print(f"Authenticated as: {profile['name']} ({author_urn})")

# 2. Publish a test post (CONNECTIONS visibility — only your network sees it).
post = kit.execute("linkedin_create_post", {
    "author": author_urn,
    "commentary": "Test post from ToolsConnector — please ignore.",
    "visibility": "CONNECTIONS",
})
post_urn = post["id"]
print(f"Posted: {post_urn}")
print(f"View:   https://www.linkedin.com/feed/update/{post_urn}/")

# 3. Add a LIKE reaction.
kit.execute("linkedin_react_to_post", {
    "post_urn": post_urn,
    "actor": author_urn,
    "reaction_type": "LIKE",
})
print("Reacted: LIKE")

# 4. Clean up — delete the test post.
kit.execute("linkedin_delete_post", {"urn": post_urn})
print(f"Deleted: {post_urn}")
